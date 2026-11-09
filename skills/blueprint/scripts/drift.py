#!/usr/bin/env python3
"""Code-side drift detection for blueprint specs. Git and the standard library only.

Each capability in .blueprint/blueprint.json lists `anchors`: globs for the code that
implements it. `stamp` records a hash of each file those anchors match; `check` reports
every capability whose files were added, removed or edited since, i.e. code that moved
since its spec was last synced. It never talks to the spec backend.

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
    # Always from the top level, so paths are root-relative wherever the script is run.
    out = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    if check and out.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


def git_paths(*args):
    """Paths from a git command run with -z, so unusual file names come back unquoted."""
    return {f for f in git(*args, "-z").split("\0") if f}


_top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
if _top.returncode != 0:
    sys.exit("not inside a git repository")
ROOT = Path(_top.stdout.strip())
STATE = ROOT / ".blueprint" / "blueprint.json"


def load():
    if not STATE.exists():
        sys.exit(f"{STATE.relative_to(ROOT)} not found: run /blueprint-setup first")
    return json.loads(STATE.read_text())


def save(state):
    STATE.write_text(json.dumps(state, indent=2) + "\n")


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
    listed = git_paths("ls-files", "-co", "--exclude-standard")
    return sorted(f for f in listed if (ROOT / f).is_file())


def matched(spec, files):
    includes = [glob_re(p) for p in spec.get("anchors", []) if not p.startswith("!")]
    excludes = [glob_re(p[1:]) for p in spec.get("anchors", []) if p.startswith("!")]
    return [
        f for f in files
        if any(r.match(f) for r in includes) and not any(r.match(f) for r in excludes)
        and not f.startswith(".blueprint/")
    ]


def file_hashes(paths):
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()[:12] for p in paths}


def head_commit():
    """HEAD's sha, or None before the first commit."""
    return git("rev-parse", "--verify", "-q", "HEAD", check=False).strip() or None


def uncommitted():
    """Files that differ from HEAD in the working tree, plus untracked ones."""
    return (git_paths("diff", "--name-only", "--no-renames", "HEAD")
            | git_paths("ls-files", "-o", "--exclude-standard"))


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
        if not spec.get("anchors"):
            report.append({"capability": name, "status": "no-anchors"})
        elif not spec.get("ref") or "anchorsFiles" not in spec:
            # Mapped but never written as a spec (lazy setup): nothing to drift from.
            report.append({"capability": name, "status": "no-spec"})
        else:
            # Compare file by file, so additions, deletions and renames all show up.
            old, now = spec["anchorsFiles"], file_hashes(matched(spec, files))
            changed = sorted(p for p in old.keys() | now.keys() if old.get(p) != now.get(p))
            if changed:
                report.append({
                    "capability": name,
                    "status": "code-moved",
                    "syncedCommit": spec.get("syncedCommit"),
                    "changed": changed,
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
    head = head_commit()
    dirty = uncommitted() if head else set(files)
    for name in names:
        if name not in specs:
            sys.exit(f"unknown capability: {name}")
        paths = matched(specs[name], files)
        specs[name]["anchorsFiles"] = file_hashes(paths)
        specs[name]["syncedCommit"] = head
        print(f"stamped {name}: {len(paths)} files at {(head or 'no commit')[:9]}", flush=True)
        if pending := dirty.intersection(paths):
            # syncedCommit is what `git diff <syncedCommit>` reads; it must hold this code.
            print(f"  warning: {len(pending)} of them uncommitted, so syncedCommit predates "
                  "them; commit the code, then stamp again", file=sys.stderr)
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
    state = load()
    if "--since" in args:
        i = args.index("--since")
        if i + 1 == len(args):
            sys.exit("--since needs a ref")
        candidates = (git_paths("diff", "--name-only", "--no-renames", args[i + 1])
                      | git_paths("ls-files", "-o", "--exclude-standard"))
    else:
        candidates = set(repo_files())
    # Coverage is judged on the candidates themselves, so deleted files count as covered too.
    candidates = sorted(f for f in candidates if not f.startswith(".blueprint/"))
    covered = set()
    for spec in state.get("specs", {}).values():
        covered.update(matched(spec, candidates))
    print("\n".join(f for f in candidates if f not in covered))
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
