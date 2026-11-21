#!/usr/bin/env python3
"""Code-side drift detection for blueprint specs. Git and the standard library only.

Each capability in .blueprint/blueprint.json lists `anchors`: globs for the code that
implements it. `stamp` records a hash of each file those anchors match; `check` reports
every capability whose files were added, removed or edited since, i.e. code that moved
since its spec was last synced. It never talks to the spec backend.

    drift.py check [--json] [CAPABILITY ...]   exit 1 if anything drifted
    drift.py stamp CAPABILITY ... | --all      record the current state as synced
    drift.py files CAPABILITY [ANCHOR ...]     list the files a capability's anchors match, or
                                               the given anchors instead (writes nothing)
    drift.py unanchored [--since REF]          changed files no capability covers
    drift.py overlaps [--json]                 files two or more capabilities' anchors match
    drift.py rename OLD NEW                    rename a capability, keeping its stamps
    drift.py prune CAPABILITY                  drop stamps for files its anchors no longer match
    drift.py hint                              one line suggesting /blueprint-tidy, or nothing
    drift.py artifacts [--json] [CAPABILITY ...]
                                               stale artifacts (outside resources describing a
                                               capability) and their changed files; exit 0
    drift.py artifacts add --type T --value V --description D [--id ID] CAPABILITY ...
                                               add one, stamped as checked
    drift.py artifacts checked ID ... | --all  record the current state as checked
    drift.py artifacts remove ID               drop one
    drift.py version                           the format version of blueprint.json

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


def compile_anchors(spec):
    """A spec's anchors as ([(include, regex)], [exclude regex]), compiled once."""
    anchors = spec.get("anchors", [])
    return ([(p, glob_re(p)) for p in anchors if not p.startswith("!")],
            [glob_re(p[1:]) for p in anchors if p.startswith("!")])


def matching_anchors(compiled, path):
    """The include anchors that match path, or [] when none does or an exclusion wins."""
    includes, excludes = compiled
    if path.startswith(".blueprint/") or any(r.match(path) for r in excludes):
        return []
    return [p for p, r in includes if r.match(path)]


def matched(spec, files):
    compiled = compile_anchors(spec)
    return [f for f in files if matching_anchors(compiled, f)]


def file_hashes(paths):
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()[:12] for p in paths}


def head_commit():
    """HEAD's sha, or None before the first commit."""
    return git("rev-parse", "--verify", "-q", "HEAD", check=False).strip() or None


def uncommitted():
    """Files that differ from HEAD in the working tree, plus untracked ones."""
    return (git_paths("diff", "--name-only", "--no-renames", "HEAD")
            | git_paths("ls-files", "-o", "--exclude-standard"))


def code_status(spec, paths, hashes=file_hashes):
    """A capability's code-side status and changed files, given the files its anchors match.

    hashes maps paths to {path: hash}; pass a caching one to hash shared files once.
    """
    if not spec.get("anchors"):
        return "no-anchors", []
    if not spec.get("ref") or "anchorsFiles" not in spec:
        # Mapped but never written as a spec (lazy setup): nothing to drift from.
        return "no-spec", []
    # Compare file by file, so additions, deletions and renames all show up.
    old, now = spec["anchorsFiles"], hashes(paths)
    changed = sorted(p for p in old.keys() | now.keys() if old.get(p) != now.get(p))
    return ("code-moved" if changed else "in-sync"), changed


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
        status, changed = code_status(spec, matched(spec, files))
        if status == "code-moved":
            report.append({
                "capability": name,
                "status": status,
                "syncedCommit": spec.get("syncedCommit"),
                "changed": changed,
            })
        else:
            report.append({"capability": name, "status": status})
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
    if not args:
        sys.exit("files takes a capability, then optionally anchors to try instead of its own")
    spec = load().get("specs", {}).get(args[0])
    if spec is None:
        sys.exit(f"unknown capability: {args[0]}")
    if args[1:]:
        # Proposed anchors, so a narrowing can be checked before blueprint.json changes.
        spec = dict(spec, anchors=args[1:])
    print("\n".join(matched(spec, repo_files())))
    return 0


def cmd_prune(args):
    if len(args) != 1:
        sys.exit("prune takes one capability")
    state = load()
    spec = state.get("specs", {}).get(args[0])
    if spec is None:
        sys.exit(f"unknown capability: {args[0]}")
    # Judged on the path, not on whether the file exists, so a deleted file the anchors
    # still cover keeps its stamp and still reads as removed. syncedCommit stays.
    compiled, old = compile_anchors(spec), spec.get("anchorsFiles", {})
    kept = {p: h for p, h in old.items() if matching_anchors(compiled, p)}
    spec["anchorsFiles"] = kept
    save(state)
    print(f"pruned {args[0]}: dropped {len(old) - len(kept)} of {len(old)} stamps")
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


def cmd_version(args):
    print(load().get("version", 1))
    return 0


def cmd_overlaps(args):
    as_json = "--json" in args
    specs, files = load().get("specs", {}), repo_files()
    compiled = {name: compile_anchors(spec) for name, spec in specs.items()}
    report = []
    for f in files:
        hits = [{"capability": name, "anchors": anchors}
                for name, c in compiled.items() if (anchors := matching_anchors(c, f))]
        if len(hits) > 1:
            report.append({"file": f, "capabilities": hits})
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        for r in report:
            print(r["file"])
            width = max(len(h["capability"]) for h in r["capabilities"])
            for h in r["capabilities"]:
                print(f"    {h['capability']:<{width}}  {', '.join(h['anchors'])}")
    return 0


def collision(name, specs, domains, ignore=None):
    """Why name can't be a capability next to the others (a name is a domain or a capability,
    never both), or None."""
    others = [n for n in specs if n != ignore]
    parts = name.split("/")
    if len(parts) > 2 or any(p in ("", ".", "..") for p in parts):
        return f"{name} isn't <domain>/<capability> or <capability> (domains are one level deep)"
    if name in domains:
        return f"{name} is a domain"
    if clash := next((n for n in others if n.startswith(name + "/")), None):
        return f"{name} would be the parent of capability {clash}"
    if "/" in name and (parent := name.split("/")[0]) in others:
        return f"its domain {parent} is a capability"
    return None


def cmd_rename(args):
    if len(args) != 2:
        sys.exit("rename takes OLD NEW")
    old, new = args
    state = load()
    specs = state.get("specs", {})
    if old not in specs:
        sys.exit(f"unknown capability: {old}")
    if new in specs:
        sys.exit(f"capability already exists: {new}")
    if why := collision(new, specs, state.get("domains", {}), ignore=old):
        sys.exit(f"can't rename {old} to {new}: {why}")
    base = ROOT / ".blueprint" / "baseline"
    src, dst = base / f"{old}.md", base / f"{new}.md"
    if dst.exists():
        # A leftover baseline would silently become the renamed capability's merge base.
        sys.exit(f"baseline already exists: {dst.relative_to(ROOT)}")
    # Rebuild in place so the key keeps its position, and with it the order of check's report.
    state["specs"] = {(new if k == old else k): v for k, v in specs.items()}
    renamed = []
    for aid, art in state.get("artifacts", {}).items():
        if old in art.get("capabilities", []):
            art["capabilities"] = [new if c == old else c for c in art["capabilities"]]
            renamed.append(aid)
    has_baseline = src.exists()
    if has_baseline:
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        # Drop folders the move left empty, up to baseline/ itself.
        parent = src.parent
        while parent != base and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    save(state)
    print(f"renamed {old} to {new}" + ("; baseline moved" if has_baseline else "")
          + (f"; {len(renamed)} artifacts updated" if renamed else ""))
    print(f"  the backend still names it {old}: rename its page and the briefs that list it",
          file=sys.stderr)
    return 0


def anchor_folder(anchor):
    """The folder an anchor lives in, at most two levels deep (`src/board`), or None for a
    root-level file or an anchor that starts with a wildcard."""
    parts = anchor.rstrip("/").split("/")
    path, last = ROOT / anchor, parts[-1]
    # A bare directory, even one not created yet: a trailing "/", or a literal name with no
    # extension that isn't a file.
    is_dir = anchor.endswith("/") or path.is_dir() or (
        not path.is_file() and "." not in last and not any(c in last for c in "*?["))
    if not is_dir:
        parts = parts[:-1]  # a file or a glob: its folder is everything before the last part
    literal = []
    for part in parts:
        if any(c in part for c in "*?["):
            break
        literal.append(part)
    return "/".join(literal[:2]) or None


def cmd_hint(args):
    state = load()
    specs, domains = state.get("specs", {}), state.get("domains", {})
    loose = [n for n in specs if n.split("/")[0] not in domains or "/" not in n]
    if len(loose) > 10:
        print(f"{len(loose)} capabilities have no domain: /blueprint-tidy can group them.")
        return 0
    by_folder = {}
    for name in loose:
        for folder in {anchor_folder(a) for a in specs[name].get("anchors", [])
                       if not a.startswith("!")} - {None}:
            by_folder.setdefault(folder, []).append(name)
    crowded = [(f, names) for f, names in sorted(by_folder.items()) if len(names) >= 3]
    if crowded:
        folder, names = max(crowded, key=lambda c: len(c[1]))
        print(f"{len(names)} capabilities without a domain share {folder}/ ({', '.join(names)}): "
              "/blueprint-tidy can group them.")
    return 0


# Artifacts: resources outside the repo (support articles, docs pages, files in other repos)
# that describe capabilities. Each has its own checked stamp, so syncing a spec never clears
# the reminder to look at the article.

URL_TYPES = ("webpage", "notion", "confluence", "linear", "github")
ARTIFACT_TYPES = URL_TYPES + ("file", "obsidian", "markdown")
KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
GITHUB_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def value_problem(kind, value):
    """Why value isn't the right shape for an artifact of this type, or None."""
    if kind not in ARTIFACT_TYPES:
        return f"unknown type {kind!r}: use one of {', '.join(ARTIFACT_TYPES)}"
    if kind in URL_TYPES:
        if not re.match(r"^https?://[^\s/]+\S*$", value):
            return f"a {kind} value is a URL (http:// or https://)"
    elif kind == "file":
        repo, sep, path = value.rpartition(":")
        is_git_url = "://" in repo or repo.startswith("git@") or repo.endswith(".git")
        if not sep or not path.strip() or not (GITHUB_REPO.match(repo) or is_git_url):
            return "a file value is <repo>:<path>, with <repo> owner/name or a git URL"
    elif not value.strip():
        return f"a {kind} value is a path to the note"
    return None


def file_link(kind, value):
    """Where a reader can open the artifact from CI, or None when only its tool can."""
    if kind in URL_TYPES:
        return value
    if kind == "file":
        repo, _, path = value.rpartition(":")
        if GITHUB_REPO.match(repo):
            return f"https://github.com/{repo}/blob/HEAD/{path.lstrip('/')}"
    return None


def resolve(names, specs, domains):
    """Capability names, with each domain standing for every capability in it now."""
    out = []
    for name in names:
        hits = ([s for s in specs if s.startswith(name + "/")] if name in domains
                else [name] if name in specs else [])
        out.extend(h for h in hits if h not in out)
    return out


def unknown_names(names, specs, domains):
    return [n for n in names if n not in specs and n not in domains]


def artifact_files(art, specs, domains, files):
    """The files the anchors of an artifact's capabilities match, now."""
    paths = set()
    for name in resolve(art.get("capabilities", []), specs, domains):
        paths.update(matched(specs[name], files))
    return sorted(paths)


def artifact_ids(args, arts, what):
    ids = list(arts) if "--all" in args else [a for a in args if not a.startswith("--")]
    if not ids:
        sys.exit(f"artifacts {what} needs artifact ids" + (" or --all" if what == "checked" else ""))
    if missing := [i for i in ids if i not in arts]:
        sys.exit(f"unknown artifact: {', '.join(missing)}")
    return ids


def slug(text, taken):
    words = re.findall(r"[a-z0-9]+", text.lower())[:5]
    base = "-".join(words) or "artifact"
    out, n = base, 2
    while out in taken:
        out, n = f"{base}-{n}", n + 1
    return out


def artifacts_list(args):
    as_json = "--json" in args
    names = [a for a in args if not a.startswith("--")]
    state, files = load(), repo_files()
    specs, domains = state.get("specs", {}), state.get("domains", {})
    if missing := unknown_names(names, specs, domains):
        sys.exit(f"unknown capability: {', '.join(missing)}")
    wanted = set(resolve(names, specs, domains))
    cache = {}

    def hashes(paths):
        for p in paths:
            if p not in cache:
                cache.update(file_hashes([p]))
        return {p: cache[p] for p in paths}

    report = []
    for aid, art in state.get("artifacts", {}).items():
        covers = resolve(art.get("capabilities", []), specs, domains)
        if names and not wanted.intersection(covers):
            continue
        old = art.get("checkedFiles", {})
        now = hashes(artifact_files(art, specs, domains, files))
        changed = sorted(p for p in old.keys() | now.keys() if old.get(p) != now.get(p))
        if changed:
            report.append({"id": aid, "type": art.get("type"), "value": art.get("value"),
                           "link": file_link(art.get("type"), art.get("value", "")),
                           "description": art.get("description", ""),
                           "capabilities": art.get("capabilities", []), "changed": changed})
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        for r in report:
            print(f"{r['id']}  {r['type']}  {r['value']}")
            if r["description"]:
                print(f"    {r['description']}")
            print("".join(f"      {f}\n" for f in r["changed"]), end="")
    return 0


def artifacts_add(args):
    import argparse
    parser = argparse.ArgumentParser(prog="drift.py artifacts add")
    parser.add_argument("--type", required=True, dest="kind")
    parser.add_argument("--value", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--id")
    parser.add_argument("capabilities", nargs="+")
    opts = parser.parse_args(args)
    state = load()
    specs, domains = state.get("specs", {}), state.get("domains", {})
    arts = state.get("artifacts", {})
    if why := value_problem(opts.kind, opts.value):
        sys.exit(f"can't add artifact: {why}")
    if not opts.description.strip():
        sys.exit("can't add artifact: the description is empty")
    if missing := unknown_names(opts.capabilities, specs, domains):
        sys.exit(f"unknown capability or domain: {', '.join(missing)}")
    aid = opts.id if opts.id is not None else slug(opts.description, arts)
    if not KEBAB.match(aid):
        sys.exit(f"artifact id {aid!r} isn't kebab-case")
    if aid in arts:
        sys.exit(f"artifact already exists: {aid}")
    caps = list(dict.fromkeys(opts.capabilities))
    art = {"type": opts.kind, "value": opts.value, "description": opts.description.strip(),
           "capabilities": caps}
    # Whoever adds it is taken to have just read it.
    art["checkedFiles"] = file_hashes(artifact_files(art, specs, domains, repo_files()))
    state.setdefault("artifacts", {})[aid] = art
    save(state)
    print(f"added {aid}: {len(art['checkedFiles'])} files checked")
    return 0


def artifacts_checked(args):
    state, files = load(), repo_files()
    specs, domains = state.get("specs", {}), state.get("domains", {})
    arts = state.get("artifacts", {})
    for aid in artifact_ids(args, arts, "checked"):
        arts[aid]["checkedFiles"] = file_hashes(artifact_files(arts[aid], specs, domains, files))
        print(f"checked {aid}: {len(arts[aid]['checkedFiles'])} files")
    save(state)
    return 0


def artifacts_remove(args):
    if len(args) != 1:
        sys.exit("artifacts remove takes one artifact id")
    state = load()
    arts = state.get("artifacts", {})
    artifact_ids(args, arts, "remove")
    del arts[args[0]]
    save(state)
    print(f"removed {args[0]}")
    return 0


def cmd_artifacts(args):
    subs = {"add": artifacts_add, "checked": artifacts_checked, "remove": artifacts_remove}
    if args and args[0] in subs:
        return subs[args[0]](args[1:])
    return artifacts_list(args)


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, args = sys.argv[1], sys.argv[2:]
    handlers = {"check": cmd_check, "stamp": cmd_stamp, "files": cmd_files,
                "unanchored": cmd_unanchored, "overlaps": cmd_overlaps, "rename": cmd_rename,
                "prune": cmd_prune, "hint": cmd_hint, "version": cmd_version,
                "artifacts": cmd_artifacts}
    if cmd not in handlers:
        sys.exit(f"unknown command: {cmd}")
    return handlers[cmd](args)


if __name__ == "__main__":
    sys.exit(main())
