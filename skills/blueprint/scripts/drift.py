#!/usr/bin/env python3
"""Code-side drift detection for blueprint specs. Git and the standard library only.

Each capability in .blueprint/blueprint.json lists `anchors`: globs for the code that
implements it. `stamp` records a hash of those files' contents; `check` reports every
capability whose files no longer match that hash, i.e. code that moved since its spec
was last synced. It never talks to the spec backend.

    drift.py check [--json] [CAPABILITY ...]   exit 1 if anything drifted
    drift.py stamp CAPABILITY ... | --all      record the current state as synced
    drift.py files CAPABILITY                  list the files a capability's anchors match
    drift.py unanchored [--since REF]          changed files no capability covers

Run from anywhere inside the repository.
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


def git(*args, check=True):
    out = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and out.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


ROOT = Path(git("rev-parse", "--show-toplevel").strip())
STATE = ROOT / ".blueprint" / "blueprint.json"


def load():
    if not STATE.exists():
        sys.exit(f"{STATE.relative_to(ROOT)} not found: run /blueprint-setup first")
    return json.loads(STATE.read_text())


def save(state):
    STATE.write_text(json.dumps(state, indent=2, sort_keys=False) + "\n")


def glob_re(pattern):
    """Translate a git-style glob (`**`, `*`, `?`) into an anchored regex."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    # A bare directory anchor ("src/auth" or "src/auth/") covers everything under it.
    return re.compile(out.rstrip("/") + "(?:/.*)?$")


def repo_files():
    """Tracked plus untracked-but-not-ignored files, so uncommitted work counts."""
    listed = git("ls-files", "-co", "--exclude-standard", "-z")
    return sorted(f for f in listed.split("\0") if f and (ROOT / f).is_file())


def matched(spec, files):
    includes = [glob_re(p) for p in spec.get("anchors", []) if not p.startswith("!")]
    excludes = [glob_re(p[1:]) for p in spec.get("anchors", []) if p.startswith("!")]
    return [
        f for f in files
        if any(r.match(f) for r in includes) and not any(r.match(f) for r in excludes)
        and not f.startswith(".blueprint/")
    ]


def content_hash(paths):
    h = hashlib.sha256()
    for p in paths:
        h.update(p.encode() + b"\0")
        h.update(hashlib.sha256((ROOT / p).read_bytes()).digest())
    return h.hexdigest()[:16]


def changed_since(ref, paths):
    """Files under `paths` that differ between `ref` and the working tree, plus new ones."""
    if not ref or subprocess.run(["git", "cat-file", "-e", f"{ref}^{{commit}}"],
                                 capture_output=True).returncode:
        return ["(synced commit unknown; read the anchored files directly)"]
    diff = set(git("diff", "--name-only", ref).split("\n"))
    diff |= set(git("ls-files", "-o", "--exclude-standard").split("\n"))
    return [f for f in sorted(diff - {""}) if matched({"anchors": paths}, [f])]


def cmd_check(args):
    as_json = "--json" in args
    names = [a for a in args if not a.startswith("--")]
    state, files = load(), repo_files()
    specs = state.get("specs", {})
    report = []
    for name in names or specs:
        spec = specs.get(name)
        if spec is None:
            sys.exit(f"unknown capability: {name}")
        paths = matched(spec, files)
        now = content_hash(paths)
        if not spec.get("anchors"):
            report.append({"capability": name, "status": "no-anchors"})
        elif not spec.get("ref") or not spec.get("anchorsHash"):
            # Mapped but never written as a spec (lazy setup): nothing to drift from.
            report.append({"capability": name, "status": "no-spec"})
        elif now != spec.get("anchorsHash"):
            # Diff against the synced commit over both old and new file sets, so
            # deletions and renames show up too.
            report.append({
                "capability": name,
                "status": "code-moved",
                "syncedCommit": spec.get("syncedCommit"),
                "changed": changed_since(spec.get("syncedCommit"), spec["anchors"]),
            })
        else:
            report.append({"capability": name, "status": "in-sync"})
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        for r in report:
            line = f"{r['status']:<11} {r['capability']}"
            if r["status"] == "code-moved":
                line += f"  (since {(r['syncedCommit'] or '?')[:9]})"
                line += "".join(f"\n              {f}" for f in r["changed"])
            print(line)
    return 1 if any(r["status"] == "code-moved" for r in report) else 0


def cmd_stamp(args):
    state, files = load(), repo_files()
    specs = state.get("specs", {})
    names = list(specs) if "--all" in args else [a for a in args if not a.startswith("--")]
    if not names:
        sys.exit("stamp needs capability names or --all")
    head = git("rev-parse", "HEAD", check=False).strip() or None
    for name in names:
        if name not in specs:
            sys.exit(f"unknown capability: {name}")
        paths = matched(specs[name], files)
        specs[name]["anchorsHash"] = content_hash(paths)
        specs[name]["syncedCommit"] = head
        print(f"stamped {name}: {len(paths)} files at {(head or 'no commit')[:9]}")
    save(state)
    return 0


def cmd_files(args):
    if len(args) != 1:
        sys.exit("files takes one capability")
    spec = load().get("specs", {}).get(args[0])
    if spec is None:
        sys.exit(f"unknown capability: {args[0]}")
    print("\n".join(matched(spec, repo_files())))
    return 0


def cmd_unanchored(args):
    since = args[args.index("--since") + 1] if "--since" in args else None
    state, files = load(), repo_files()
    covered = set()
    for spec in state.get("specs", {}).values():
        covered.update(matched(spec, files))
    if since:
        candidates = set(git("diff", "--name-only", since).split("\n")) - {""}
        candidates |= set(git("ls-files", "-o", "--exclude-standard").split("\n")) - {""}
    else:
        candidates = set(files)
    print("\n".join(sorted(f for f in candidates - covered if not f.startswith(".blueprint/"))))
    return 0


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, args = sys.argv[1], sys.argv[2:]
    handlers = {"check": cmd_check, "stamp": cmd_stamp, "files": cmd_files,
                "unanchored": cmd_unanchored}
    if cmd not in handlers:
        sys.exit(f"unknown command: {cmd}")
    return handlers[cmd](args)


if __name__ == "__main__":
    sys.exit(main())
