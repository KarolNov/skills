#!/usr/bin/env python3
"""Code-side drift detection for blueprint specs. Git and the standard library only.

Each capability in .blueprint/blueprint.json lists `anchors`: globs for the code that
implements it. `stamp` records a hash of each file those anchors match; `check` reports
every capability whose files were added, removed or edited since, i.e. code that moved
since its spec was last synced. It never talks to the spec backend.

    drift.py check [--json] [--tests run|REPORT.xml] [CAPABILITY ...]
                                               each capability's status, drift chance (0-1),
                                               confidence and reasons; exit 1 if any is
                                               code-moved or deps-moved, 2 on a bad
                                               drift.scoring setting, unknown capability or
                                               unusable --tests. --tests run runs tests.run
                                               ({"command", "report"}); a failing test tagged
                                               with a capability's scenario scores 1
    drift.py stamp CAPABILITY ... | --all      record the current state as synced, with the
                                               import closure of TS/JS capabilities in
                                               .blueprint/closure/<capability>.json
    drift.py files CAPABILITY [ANCHOR ...]     list the files a capability's anchors match, or
                                               the given anchors instead (writes nothing)
    drift.py unanchored [--since REF]          changed files no capability covers
    drift.py overlaps [--json]                 files two or more capabilities' anchors match
    drift.py rename OLD NEW                    rename a capability, keeping its stamps; moves
                                               its baseline and closure files and renames it in
                                               artifacts and @scenario tags
    drift.py prune CAPABILITY                  drop stamps for files its anchors no longer match,
                                               and what its closure no longer reaches
    drift.py hint                              one line suggesting /blueprint-tidy, or nothing
    drift.py artifacts [--json] [--] [CAPABILITY|DOMAIN ...]
                                               stale artifacts (outside resources describing a
                                               capability) and their changed files; exit 0.
                                               `--` lets a filter be named add/checked/remove
    drift.py artifacts add --type T --value V --description D [--id ID] CAPABILITY ...
                                               add one, stamped as checked
    drift.py artifacts checked ID ... | --all  record the current state as checked
    drift.py artifacts remove ID               drop one
    drift.py version                           the format version of blueprint.json

TS/JS imports are resolved by symbol through drift_ts.mjs (beside this script), which loads
the repo's own typescript with node. Without either, imports are followed by file, at
confidence low. Nothing is ever installed.

Run from anywhere inside the repository.
"""

import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
from collections import deque
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from urllib.parse import quote


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


def cached_hashes():
    """file_hashes with a cache, so a file several capabilities match is read once."""
    cache = {}

    def hashes(paths):
        cache.update(file_hashes([p for p in paths if p not in cache]))
        return {p: cache[p] for p in paths}
    return hashes


def changed_files(old, now):
    """Paths added, removed or edited between two {path: hash} stamps, sorted."""
    return sorted(p for p in old.keys() | now.keys() if old.get(p) != now.get(p))


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
    changed = changed_files(spec["anchorsFiles"], hashes(paths))
    return ("code-moved" if changed else "in-sync"), changed


# Scoring: each capability gets a drift chance from 0 to 1, computed by a fixed formula from
# the stamped state and the working tree, never by judgement, so the same inputs always give
# the same number. A changed anchored file scores 1.0. Signals combine as 1 - prod(1 - s).

SCORING_DEFAULTS = {"decay": 0.5, "packageWeight": 0.5, "lockfileWeight": 0.3,
                    "threshold": 0.5, "maxDepth": 6}
TS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs")


class SettingError(Exception):
    """A drift.scoring value check refuses; the message names the key."""


def unit(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1


def scoring(state):
    """drift.scoring with every absent key at its default, or SettingError naming the key."""
    drift = state.get("drift", {})
    if not isinstance(drift, dict):
        raise SettingError("drift must be an object")
    raw = drift.get("scoring", {})
    if not isinstance(raw, dict):
        raise SettingError("drift.scoring must be an object")
    out = dict(SCORING_DEFAULTS, packages={})
    for key in ("decay", "packageWeight", "lockfileWeight", "threshold"):
        if key in raw:
            if not unit(raw[key]):
                raise SettingError(f"drift.scoring.{key} must be a number from 0 to 1, "
                                   f"not {json.dumps(raw[key])}")
            out[key] = raw[key]
    if "maxDepth" in raw:
        depth = raw["maxDepth"]
        if not isinstance(depth, int) or isinstance(depth, bool) or depth < 1:
            raise SettingError("drift.scoring.maxDepth must be a whole number of at least 1, "
                               f"not {json.dumps(depth)}")
        out["maxDepth"] = depth
    packages = raw.get("packages", {})
    if not isinstance(packages, dict):
        raise SettingError("drift.scoring.packages must be an object of package names")
    for name, pkg in packages.items():
        where = f"drift.scoring.packages[{json.dumps(name)}]"
        if not isinstance(pkg, dict):
            raise SettingError(f"{where} must be an object")
        if "weight" in pkg and not unit(pkg["weight"]):
            raise SettingError(f"{where}.weight must be a number from 0 to 1, "
                               f"not {json.dumps(pkg['weight'])}")
        effects = pkg.get("sideEffects", False)
        if not (isinstance(effects, bool) or (isinstance(effects, list)
                                              and all(isinstance(g, str) for g in effects))):
            raise SettingError(f"{where}.sideEffects must be true, false or a list of globs")
        out["packages"][name] = pkg
    return out


def combine(scores):
    """Signals combined as a probabilistic "any of these": 1 - prod(1 - s), rounded so the
    same inputs print the same number on every platform."""
    rest = 1.0
    for s in scores:
        rest *= 1 - s
    return round(1 - rest, 4)


def fmt_chance(chance):
    return f"{chance:g}"


CONFIDENCE_COLORS = {"high": "32", "medium": "33", "low": "31"}  # ANSI green, yellow, red


def squares(chance):
    """How many of 10 squares a drift chance fills: rounded half up, at least 1 above 0."""
    return 0 if chance <= 0 else max(1, min(10, int(chance * 10 + 0.5)))


def meter(chance, confidence, color=False):
    """`■■■■■□□□□□ 0.5 · medium`: filled by the chance, colored by the confidence."""
    n = squares(chance)
    filled = "■" * n
    if color and n and confidence in CONFIDENCE_COLORS:
        filled = f"\033[{CONFIDENCE_COLORS[confidence]}m{filled}\033[0m"
    return f"{filled}{'□' * (10 - n)} {fmt_chance(chance)} · {confidence}"


def is_ts(paths):
    return any(p.endswith(TS_EXTENSIONS) for p in paths)


def assess(spec, paths, settings, hashes=file_hashes, imports=None, tests=None):
    """One capability's row for check: status, drift chance, confidence and reasons.

    Signals are (score, reason) pairs. A changed anchored file scores 1. `imports` is what
    compare_closure found for a TS/JS capability: (signals, confidence, confidence reason);
    None for one with no closure stamped, which is then low confidence, direct changes only.
    `tests` is what a JUnit report says of its tagged tests: (signals, whether any has a
    result); None when check was given no report. Results raise medium confidence to high.
    """
    status, changed = code_status(spec, paths, hashes)
    if status in ("no-anchors", "no-spec"):
        why = "no anchors" if status == "no-anchors" else "no stamped spec to drift from"
        return {"status": status, "changed": [], "chance": 0.0, "confidence": "low",
                "reasons": [f"confidence low: {why}"]}
    signals = [(1.0, f"{f} {verb(f, spec)} (anchored) → 1") for f in changed]
    if imports is not None:
        signals += imports[0]
    if tests is not None:
        signals += tests[0]
    chance = combine(s for s, _ in signals)
    if changed:
        status = "code-moved"
    elif chance > 0 and chance >= settings["threshold"]:
        status = "deps-moved"
    elif chance > 0:
        status = "possibly-affected"
    else:
        status = "in-sync"
    reasons = [r for _, r in sorted(signals, key=lambda x: (-x[0], x[1]))]
    if imports is not None and imports[1] == "medium" and tests is not None:
        if tests[1]:
            confidence = "high"
        else:
            confidence = "medium"
            reasons.append("confidence medium: no results for its tagged tests in the report")
    elif imports is not None:
        confidence = imports[1]
        reasons.append(imports[2])
    elif is_ts(paths) or is_ts(spec.get("anchorsFiles", {})):
        confidence = "low"
        reasons.append("confidence low: no import closure stamped yet (stamp it to follow "
                       "imports), so only direct changes count")
    else:
        confidence = "high"
    return {"status": status, "changed": changed, "chance": chance, "confidence": confidence,
            "reasons": reasons}


def verb(path, spec):
    stamped = spec.get("anchorsFiles", {})
    if path not in stamped:
        return "added"
    return "edited" if (ROOT / path).is_file() else "removed"


# Transitive drift: what a TS/JS capability's anchored files import, as a closure stamped in
# .blueprint/closure/<capability>.json. Each entry is a top-level declaration (by symbol) or a
# whole file, with its distance in import edges from the anchored files, the workspace
# packages the path enters, and a content hash. check compares it with the tree as it is now.

HELPER = Path(__file__).resolve().with_name("drift_ts.mjs")
CLOSURES = ROOT / ".blueprint" / "closure"
JS_EXTS = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
HELPER_MISSING = 3  # drift_ts.mjs's exit code when the repo's typescript can't be loaded


def closure_path(name):
    return CLOSURES / f"{name}.json"


def read_closure(name):
    try:
        closure = json.loads(closure_path(name).read_text())
    except (OSError, ValueError):
        return None
    return closure if isinstance(closure, dict) and "files" in closure else None


def remove_closure(name):
    """Delete a capability's closure file, dropping folders that leaves empty."""
    path = closure_path(name)
    path.unlink()
    parent = path.parent
    while parent != CLOSURES and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


def ts_entries(paths):
    return sorted(p for p in paths if p.endswith(TS_EXTENSIONS))


def run_helper(entries, settings):
    """({"closures": {name: {"nodes", "external"}}}, None) from drift_ts.mjs, or (None, why it
    couldn't run). entries maps each capability to its anchored TS/JS files."""
    if not HELPER.is_file():
        return None, "drift_ts.mjs is missing beside drift.py"
    node = shutil.which("node")
    if not node:
        return None, "node not found"
    overrides = {name: pkg["sideEffects"] for name, pkg in settings["packages"].items()
                 if "sideEffects" in pkg}
    payload = {"root": str(ROOT), "maxDepth": settings["maxDepth"], "sideEffects": overrides,
               "capabilities": entries}
    try:
        out = subprocess.run([node, str(HELPER)], input=json.dumps(payload), capture_output=True,
                             text=True, cwd=ROOT, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"the TypeScript helper failed ({e})"
    if out.returncode == HELPER_MISSING:
        return None, "typescript not installed"
    if out.returncode != 0:
        last = (out.stderr.strip().splitlines() or ["no output"])[-1]
        return None, f"the TypeScript helper failed ({last})"
    try:
        found = json.loads(out.stdout)
    except ValueError:
        return None, "the TypeScript helper printed no closure"
    # Files git ignores (generated types, local stubs) aren't in another checkout, so they'd
    # read as removed there: leave them out, as the file-level fallback does.
    known = set(repo_files())
    for closure in found["closures"].values():
        closure["nodes"] = [n for n in closure["nodes"] if n["file"] in known]
    return found, None


def notice(why):
    print(f"notice: {why}: imports of TS/JS capabilities are followed by file, at confidence low",
          file=sys.stderr, flush=True)


# The file-level fallback: import specifiers read with a regex, resolved like a bundler would
# (relative paths, workspace packages by name), every reachable file counted whole.

IMPORT = re.compile(r"""(?:\bfrom|\bimport\s*\(?|\brequire\s*\()\s*(['"])([^'"\n]+)\1""")
# Node's built-in modules. The file-level fallback can't tell `import "events"` from the npm
# package of that name, so it reads them as built-ins: no external package, no lockfile signal.
NODE_BUILTINS = frozenset("""
    assert async_hooks buffer child_process cluster console constants crypto dgram
    diagnostics_channel dns domain events fs http http2 https inspector module net os path
    perf_hooks process punycode querystring readline repl stream string_decoder sys timers tls
    trace_events tty url util v8 vm wasi worker_threads zlib""".split())
PACKAGE_NAME = re.compile(r"^(?:@[a-z0-9][\w.-]*/)?[a-z0-9][\w.-]*$", re.I)
BUILD_DIR = re.compile(r"^(?:\./)?(?:dist|lib|build|out)/")


def manifests(files):
    """{folder ("" for the root): package.json contents} for the repo's own packages."""
    out = {}
    for f in files:
        if posixpath.basename(f) != "package.json" or "node_modules/" in f:
            continue
        try:
            data = json.loads((ROOT / f).read_text())
        except (OSError, ValueError):
            data = {}
        out[posixpath.dirname(f)] = data if isinstance(data, dict) else {}
    return out


def package_dir(path, packages):
    folder = posixpath.dirname(path)
    while True:
        if folder in packages:
            return folder
        if not folder:
            return None
        folder = posixpath.dirname(folder)


def resolve_path(base, fileset):
    """The repo file an import of `base` (repo-relative, no extension needed) lands on."""
    base = posixpath.normpath(base)
    if base.startswith(".."):
        return None
    swaps = {".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",)}
    alts = next(([base[:-len(js)] + e for e in ts] for js, ts in swaps.items()
                 if base.endswith(js)), [])
    candidates = [base, *alts, *(base + e for e in JS_EXTS),
                  *(f"{base}/index{e}" for e in JS_EXTS)]
    return next((c for c in candidates if c in fileset), None)


def export_target(value):
    """The first path in a package.json `exports` value, preferring source and types."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return next((t for v in value if (t := export_target(v))), None)
    if isinstance(value, dict):
        keys = [k for k in ("source", "types", "import", "module", "default", "require")
                if k in value] + [k for k in value if not k.startswith(".")]
        return next((t for k in keys if (t := export_target(value[k]))), None)
    return None


def package_entry(folder, manifest, sub, fileset):
    exports = manifest.get("exports")
    if sub:
        targets = [export_target(exports.get(f"./{sub}")) if isinstance(exports, dict) else None,
                   sub]
    else:
        if isinstance(exports, dict) and any(k.startswith(".") for k in exports):
            exports = exports.get(".")
        targets = [export_target(exports)] + [manifest.get(k) for k in
                                              ("source", "types", "typings", "module", "main")]
        targets += ["src/index", "index"]
    for target in targets:
        if not isinstance(target, str):
            continue
        for t in (target, BUILD_DIR.sub("src/", target)):
            t = re.sub(r"\.d\.ts$", "", t)
            if hit := resolve_path(posixpath.join(folder, t), fileset):
                return hit
    return None


def resolve_import(spec, importer, fileset, names, packages):
    """("file", path) or ("external", package name) for one import specifier, or None."""
    if spec.startswith("."):
        hit = resolve_path(posixpath.join(posixpath.dirname(importer), spec), fileset)
        return ("file", hit) if hit else None
    if spec.startswith(("/", "node:")) or ":" in spec.split("/")[0]:
        return None
    parts = spec.split("/")
    n = 2 if spec.startswith("@") else 1
    name, sub = "/".join(parts[:n]), "/".join(parts[n:])
    if name in names:
        hit = package_entry(names[name], packages[names[name]], sub, fileset)
        return ("file", hit) if hit else None
    if name in NODE_BUILTINS:  # `events`, not the npm polyfill of that name in the lockfile
        return None
    # An alias the fallback can't resolve (`@/x`, `~/x`, `#x`) is no package.
    return ("external", name) if PACKAGE_NAME.match(name) else None


def file_closure(entries, files, settings):
    """{"nodes", "external"} like drift_ts.mjs prints, every node a whole file."""
    fileset, packages = set(files), manifests(files)
    names = {m["name"]: d for d, m in packages.items() if isinstance(m.get("name"), str)}

    def package(path):
        folder = package_dir(path, packages)
        return None if folder is None else packages[folder].get("name")

    best, external = {}, set()
    queue = deque((e, 0, ()) for e in entries)
    while queue:
        path, distance, via = queue.popleft()
        if distance >= settings["maxDepth"]:
            continue
        try:
            text = (ROOT / path).read_text(errors="replace")
        except OSError:
            continue
        for m in IMPORT.finditer(text):
            hit = resolve_import(m.group(2), path, fileset, names, packages)
            if hit is None:
                continue
            if hit[0] == "external":
                external.add(hit[1])
                continue
            target = hit[1]
            if target in entries or target in best:
                continue  # breadth first: the first visit is the shortest
            to = package(target)
            step = via + (to,) if to and to != package(path) else via
            best[target] = (distance + 1, list(step))
            queue.append((target, distance + 1, step))
    nodes = [{"file": f, "symbol": None, "distance": d, "via": v}
             for f, (d, v) in sorted(best.items())]
    return {"nodes": nodes, "external": sorted(external)}


def build_closure(mode, found, locked, why=None):
    """The closure file's contents from drift_ts.mjs's or file_closure's output for one
    capability: symbols with their hashes, files (min distance, hash, whether reached whole),
    and the external packages it imports with their locked versions (None when unlocked)."""
    nodes = found["nodes"]
    hashes = file_hashes(sorted({n["file"] for n in nodes if (ROOT / n["file"]).is_file()}))
    files, symbols = {}, []
    for n in sorted(nodes, key=lambda n: (n["distance"], len(n["via"]))):
        whole = n["symbol"] is None
        rec = files.setdefault(n["file"], {"distance": n["distance"], "via": n["via"],
                                           "hash": hashes.get(n["file"]), "whole": False})
        rec["whole"] = rec["whole"] or whole
        if not whole:
            symbols.append({k: n.get(k) for k in ("file", "symbol", "distance", "via", "hash")})
    out = {"mode": mode}
    if why:
        out["why"] = why
    out.update(files=dict(sorted(files.items())),
               symbols=sorted(symbols, key=lambda s: (s["file"], s["symbol"])),
               external=found["external"],
               locked={pkg: locked.get(pkg) for pkg in found["external"]})
    return out


def dump_closure(closure):
    """A closure as JSON with one entry per line: each top-level key on its own line, and each
    file, symbol, external package and locked version on one line of its own, so a restamp
    diffs by the entries that moved and a big closure stays short. Still plain JSON."""
    def one(value):
        return json.dumps(value, ensure_ascii=False)

    def block(value):
        if isinstance(value, dict) and value:
            items = [f"    {one(k)}: {one(v)}" for k, v in value.items()]
            return "{\n" + ",\n".join(items) + "\n  }"
        if isinstance(value, list) and value:
            return "[\n" + ",\n".join(f"    {one(v)}" for v in value) + "\n  ]"
        return one(value)

    lines = [f"  {one(k)}: {block(v)}" for k, v in closure.items()]
    return "{\n" + ",\n".join(lines) + "\n}\n"


def stamp_closures(names, specs, files, settings):
    """Write the closure of each TS/JS capability among names; drop stale ones. Returns
    {name: closure}."""
    entries = {n: ts_entries(matched(specs[n], files)) for n in names}
    for n, e in entries.items():
        if not e and closure_path(n).exists():
            remove_closure(n)
    wanted = {n: e for n, e in entries.items() if e}
    if not wanted:
        return {}
    found, why = run_helper(wanted, settings)
    if why:
        notice(why)
    locked = locked_versions()
    out = {}
    for n, e in wanted.items():
        closure = (build_closure("symbol", found["closures"][n], locked) if found
                   else build_closure("file", file_closure(e, files, settings), locked, why))
        path = closure_path(n)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dump_closure(closure))
        out[n] = closure
    return out


def path_score(distance, via, settings):
    """decay^distance, times the weight of each workspace package the path enters."""
    score = settings["decay"] ** distance
    for pkg in via:
        score *= package_weight(pkg, settings)
    return score


def package_weight(pkg, settings):
    return settings["packages"].get(pkg, {}).get("weight", settings["packageWeight"])


def fmt_score(score):
    """Two decimals, half up, as people round (0.125 → 0.13)."""
    return format(Decimal(repr(score)).quantize(Decimal("0.01"), ROUND_HALF_UP).normalize(), "f")


def import_reason(what, rec, settings, score):
    d = rec["distance"]
    via = "".join(f", via {p} (weight {package_weight(p, settings):g})" for p in rec["via"])
    return f"{what}, {d} import{'' if d == 1 else 's'} away{via} → {fmt_score(score)}"


def compare_closure(stamped, now, settings):
    """(score, reason) signals for what changed in a stamped closure. `now` is the current
    drift_ts.mjs output for the capability, compared by symbol; None compares by file."""
    signals = []
    current = file_hashes([f for f in stamped["files"] if (ROOT / f).is_file()])

    def signal(what, rec):
        if rec["distance"] > settings["maxDepth"]:
            return  # stamped with a larger maxDepth: past the current one, not followed now
        score = path_score(rec["distance"], rec["via"], settings)
        if score > 0:
            signals.append((score, import_reason(what, rec, settings, score)))

    for f, rec in stamped["files"].items():
        if now is not None and not rec.get("whole"):
            continue  # compared by its symbols below
        if current.get(f) != rec.get("hash"):
            state = "removed" if f not in current else "changed"
            signal(f"{f} {state}" + (" (whole file)" if now is not None else ""), rec)
    if now is not None:
        hashes = {(n["file"], n["symbol"]): n.get("hash") for n in now["nodes"]
                  if n["symbol"] is not None}
        for s in stamped.get("symbols", []):
            if stamped["files"].get(s["file"], {}).get("whole"):
                continue  # its file is compared whole above
            hash_now = hashes.get((s["file"], s["symbol"]))
            if hash_now != s["hash"]:
                signal(f"{s['file']} {s['symbol']} {'changed' if hash_now else 'removed'}", s)
    return signals


def import_signals(rows, settings):
    """{name: (signals, confidence, confidence reason)} for TS/JS capabilities with a stamped
    closure. rows maps each capability to the files its anchors match now. Runs drift_ts.mjs
    once for all those stamped by symbol; prints one notice when it can't."""
    closures = {n: c for n in rows if (c := read_closure(n)) is not None}
    by_symbol = {n: ts_entries(rows[n]) for n, c in closures.items() if c.get("mode") == "symbol"}
    found, why = run_helper(by_symbol, settings) if by_symbol else (None, None)
    if why:
        notice(why)
    locked = locked_versions() if any("locked" in c for c in closures.values()) else {}
    out = {}
    for n, closure in closures.items():
        bumps = lock_signals(closure, locked, settings)
        if n in by_symbol and found:
            now = found["closures"].get(n, {"nodes": [], "external": []})
            out[n] = (compare_closure(closure, now, settings) + bumps, "medium",
                      "confidence medium: no test results given")
        else:
            reason = (why if n in by_symbol else
                      f"{closure.get('why') or 'typescript was not used'} when stamped")
            out[n] = (compare_closure(closure, None, settings) + bumps, "low",
                      f"confidence low: {reason}, so imports are followed by file")
    return out


# The lockfile signal: the closure records the locked version of each external package it
# imports; a different version in the lockfile now scores lockfileWeight. npm (package-lock.json,
# npm-shrinkwrap.json), pnpm (pnpm-lock.yaml) and yarn (yarn.lock, classic and berry) are read
# at the repo root with the standard library. A package locked at several versions reads as
# all of them, sorted, so a bump of any one of them counts.

LOCKFILES = ("package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock")
PNPM_KEY = re.compile(r"""^  (['"]?)(\S.*?)\1:(?:\s|$)""")
YARN_VERSION = re.compile(r"""^  version:?\s+"?([^"\s]+)"?\s*$""")


def npm_versions(text):
    try:
        data = json.loads(text)
    except ValueError:
        return
    if not isinstance(data, dict):
        return
    packages = data.get("packages")
    if isinstance(packages, dict) and packages:  # lockfileVersion 2 and 3
        for key, rec in packages.items():
            if ("node_modules/" in key and isinstance(rec, dict) and not rec.get("link")
                    and isinstance(rec.get("version"), str)):
                yield key.rsplit("node_modules/", 1)[1], rec["version"]
        return
    stack = [data.get("dependencies")]  # lockfileVersion 1: nested dependencies
    while stack:
        deps = stack.pop()
        for name, rec in (deps.items() if isinstance(deps, dict) else ()):
            if isinstance(rec, dict):
                if isinstance(rec.get("version"), str):
                    yield name, rec["version"]
                stack.append(rec.get("dependencies"))


def pnpm_versions(text):
    """From the `packages:` keys: `/zod@3.22.0` (v6), `zod@3.22.0` (v9), `/zod/3.22.0` (v5),
    with peer suffixes (`(react@18.2.0)`, `_react@18.2.0`) dropped."""
    major, section = 6, None
    for line in text.split("\n"):
        if line and not line[0].isspace():
            section = line.split(":", 1)[0].strip()
            if section == "lockfileVersion":
                try:
                    major = int(float(line.split(":", 1)[1].strip().strip("'\"")))
                except ValueError:
                    pass
            continue
        m = section == "packages" and PNPM_KEY.match(line)
        if not m:
            continue
        key = m.group(2).lstrip("/")
        if major < 6:
            name, _, version = key.rpartition("/")
            version = version.split("_", 1)[0]
        else:
            key = key.split("(", 1)[0]
            at = key.rfind("@")
            name, version = (key[:at], key[at + 1:]) if at > 0 else ("", "")
        if name and version:
            yield name, version


def yarn_versions(text):
    """From each entry: its header (`zod@^3.22.0, "zod@npm:^3":`) names the package, its
    `version` line (indented two spaces) the locked version."""
    names = []
    for line in text.split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            names = []
            for spec in line.rstrip().rstrip(":").split(","):
                spec = spec.strip().strip('"')
                at = spec.find("@", 1)
                if at > 0 and spec[:at] not in names:
                    names.append(spec[:at])
            continue
        m = YARN_VERSION.match(line)
        if m and names:
            for name in names:
                yield name, m.group(1)
            names = []


def locked_versions():
    """{package: version} from the repo's lockfiles; several versions joined, sorted."""
    readers = {"pnpm-lock.yaml": pnpm_versions, "yarn.lock": yarn_versions}
    found = {}
    for name in LOCKFILES:
        try:
            text = (ROOT / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pkg, version in readers.get(name, npm_versions)(text):
            found.setdefault(pkg, set()).add(version)
    return {pkg: ", ".join(sorted(vs)) for pkg, vs in found.items()}


def lock_signals(closure, locked, settings):
    """(lockfileWeight, reason) for each external package whose locked version moved since
    the closure was stamped. A closure stamped before versions were recorded gives none."""
    stamped = closure.get("locked")
    weight = settings["lockfileWeight"]
    if not isinstance(stamped, dict) or weight <= 0:
        return []
    out = []
    for pkg, was in sorted(stamped.items()):
        if closure.get("mode") == "file" and pkg in NODE_BUILTINS:
            continue  # stamped by file before built-ins were told apart: not a package
        now = locked.get(pkg)
        if now != was:
            out.append((weight, f"{pkg} {was or 'not locked'} → {now or 'not locked'} in the "
                                f"lockfile → {fmt_score(weight)}"))
    return out


# The test signal: JUnit results matched to tagged tests by file and test name. A failing
# test tagged with one of a capability's scenarios scores 1; passing ones raise confidence only.
# Tests run only on `check --tests run`; otherwise a report is read, or there are no results.

class TestsError(Exception):
    """--tests can't give results (no tests.run, no report, unreadable XML): exit 2."""


def tests_run(state):
    """(command, report path) from tests.run in blueprint.json, or TestsError naming it."""
    tests = state.get("tests")
    run = tests.get("run") if isinstance(tests, dict) else None
    if run is None:
        raise TestsError('tests.run is required in .blueprint/blueprint.json for --tests run: '
                         '{"command": "<runs the tests>", "report": "<the JUnit XML it writes>"}')
    if not (isinstance(run, dict) and isinstance(run.get("command"), str) and run["command"]
            and isinstance(run.get("report"), str) and run["report"]):
        raise TestsError('tests.run must be {"command": "<runs the tests>", '
                         '"report": "<the JUnit XML it writes>"}')
    return run["command"], ROOT / run["report"]


def run_tests(state):
    """Run tests.run's command at the repo root (its output to stderr) and return the report
    it wrote. A failing run is fine: failures are what the report is for."""
    command, report = tests_run(state)
    before = report.stat().st_mtime_ns if report.is_file() else None
    print(f"running tests: {command}", file=sys.stderr, flush=True)
    subprocess.run(command, shell=True, cwd=ROOT, stdout=sys.stderr, stdin=subprocess.DEVNULL)
    if not report.is_file() or report.stat().st_mtime_ns == before:
        try:
            shown = report.relative_to(ROOT)
        except ValueError:  # an absolute report path outside the repo
            shown = report
        raise TestsError(f"tests.run didn't write its report: {shown}")
    return report


def read_junit(path):
    """[{"where": [file or class locators], "name", "outcome"}] for each <testcase>, outcome
    "failed" (a failure or error), "skipped" or "passed"."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as e:
        raise TestsError(f"can't read the JUnit report {path}: {e}") from None
    cases = []

    def walk(node, suite):
        for child in node:
            if child.tag == "testsuite":
                walk(child, [child.get("file"), child.get("name")])
            elif child.tag == "testcase":
                if child.find("failure") is not None or child.find("error") is not None:
                    outcome = "failed"
                elif child.find("skipped") is not None:
                    outcome = "skipped"
                else:
                    outcome = "passed"
                where = [w for w in [child.get("file"), child.get("classname"), *suite] if w]
                cases.append({"where": where, "name": child.get("name") or "", "outcome": outcome})
            else:
                walk(child, suite)
    top = ET.Element("report")  # the root may be <testsuites>, one <testsuite> or a <testcase>
    top.append(root)
    walk(top, [])
    return cases


class Layout:
    """What locating a report's cases needs from the repo: its files by base name (so a path
    suffix shared by several files reads as ambiguous), Go modules and Rust crates by name,
    each with its folder ("" at the root)."""

    def __init__(self, files=()):
        self.by_name, self.go, self.rust = {}, {}, {}
        for f in files:
            base, folder = posixpath.basename(f), posixpath.dirname(f)
            self.by_name.setdefault(base, []).append(f)
            if base not in ("go.mod", "Cargo.toml"):
                continue
            try:
                text = (ROOT / f).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if base == "go.mod" and (m := re.search(r"^module\s+(\S+)", text, re.M)):
                self.go[m.group(1).strip('"')] = folder
            elif base == "Cargo.toml" and (m := re.search(
                    r"^\[package\][^\[]*?^name\s*=\s*[\"']([^\"']+)", text, re.M | re.S)):
                self.rust[m.group(1).replace("-", "_")] = folder

    def unique(self, suffix):
        """Whether exactly one repo file is `suffix` or ends with `/suffix`."""
        hits = [f for f in self.by_name.get(posixpath.basename(suffix), [])
                if f == suffix or f.endswith("/" + suffix)]
        return len(hits) == 1


def locates(where, path, layout=None):
    """Whether a report's file or class name points at the repo file path: the same path
    (absolute, or relative when no other repo file ends the same way), a dotted module
    (`tests.test_auth.TestLogin`), or a Go package (by its go.mod when layout knows it)."""
    where = where.replace("\\", "/").strip()
    if where.startswith("./"):
        where = where[2:]
    if not where:
        return False
    if where == path or where.endswith("/" + path):
        return True
    if path.endswith("/" + where):  # relative to a sub-project: only if no other file fits
        return layout is None or layout.unique(where)
    folder = posixpath.dirname(path)
    mods = [m for m in (layout.go if layout else ()) if where == m or where.startswith(m + "/")]
    if mods:
        mod = max(mods, key=len)
        guess = posixpath.normpath(posixpath.join(layout.go[mod], where[len(mod):].lstrip("/")))
        return folder == ("" if guess == "." else guess)
    if folder and (where == folder or where.endswith("/" + folder)):
        return True
    module = posixpath.splitext(path)[0].replace("/", ".")
    parts = where.split(".")
    return any(module == p or module.endswith("." + p)
               for p in (".".join(parts[:k]) for k in range(len(parts), 0, -1)) if "/" not in p)


def rust_locates(where, case, path, layout):
    """Whether a cargo report case (nextest, cargo2junit: class `crate` or `crate::binary`,
    name `module::…::test`) is in the .rs file path: in the crate's folder, an integration
    test file named like the binary, and a src/ file whose module path starts the name."""
    crate, _, binary = where.partition("::")
    folder = layout.rust.get(crate.replace("-", "_")) if layout else None
    if folder is None:
        return False
    if folder and not path.startswith(folder + "/"):
        return False
    rel = path[len(folder) + 1:] if folder else path
    if rel.startswith("tests/"):
        target = posixpath.splitext(rel.split("/")[1])[0]
        return binary.rpartition("/")[2] == target
    if not rel.startswith("src/"):
        return False
    mods = posixpath.splitext(rel[4:])[0].split("/")
    if mods[-1] in ("lib", "main", "mod"):
        mods.pop()
    if mods[:1] == ["bin"]:
        mods = mods[2:]
    return case.split("::")[:-1][:len(mods)] == mods


LEAF = (" > ", " › ", " ", "::")  # how runners join describe blocks or modules to a test name
HOLDS = (" > ", " › ", "[", "/")  # what follows a describe, parametrized test or Go subtest


def leaf_match(case, test):
    """Whether the report's test name is the test itself, maybe inside describes or modules."""
    return case == test or any(case.endswith(sep + test) for sep in LEAF)


def names_match(case, test):
    """Whether a report's test name is the tagged test: the same, nested in describe blocks
    or Rust modules, a describe holding it (`test > …`), parametrized (`test[…]`) or a Go
    subtest (`Test/…`)."""
    return leaf_match(case, test) or any(case.startswith(test + sep) for sep in HOLDS)


def claims(case, test, declared):
    """names_match, except that a case whose name ends with the test's belongs to a longer
    test declared in the same file when one fits: `never rejects` is not `rejects`."""
    if any(case.startswith(test + sep) for sep in HOLDS):
        return True
    if not leaf_match(case, test):
        return False
    return not any(len(t) > len(test) and leaf_match(case, t) for t in declared)


def tested(specs, files, cases):
    """{capability: (signals, whether any of its tagged tests has a result)} for capabilities
    with tagged, named tests. A tagged test skipped or missing from the report has no result."""
    out, layout = {}, Layout(files)
    for path, data in tag_files(files):
        text = data.decode("utf-8-sig", "replace")
        declared = declared_tests(text)
        rust = path.endswith(".rs")
        for line, cap, scenario, test in scan_tags(text):
            if cap not in specs or not test:
                continue
            outcomes = {c["outcome"] for c in cases if claims(c["name"], test, declared)
                        and any(rust_locates(w, c["name"], path, layout) if rust
                                else locates(w, path, layout) for w in c["where"])}
            signals, seen = out.setdefault(cap, ([], False))
            if "failed" in outcomes:
                signals.append((1.0, f'test "{test}" ({path}:{line}) failed, claiming '
                                     f'"{scenario}" → 1'))
            if outcomes & {"failed", "passed"}:
                out[cap] = (signals, True)
    return out


DRIFTED = ("code-moved", "deps-moved")


def check_args(args):
    """(--json, --tests value or None, capability names)."""
    as_json, tests, names = False, None, []
    it = iter(args)
    for a in it:
        if a == "--json":
            as_json = True
        elif a == "--tests" or a.startswith("--tests="):
            tests = a.split("=", 1)[1] if "=" in a else next(it, None)
            if not tests or tests.startswith("--"):
                raise TestsError("--tests needs `run` or a JUnit XML report")
        elif not a.startswith("--"):
            names.append(a)
    return as_json, tests, names


def cmd_check(args):
    try:
        as_json, tests_from, names = check_args(args)
    except TestsError as e:
        print(e, file=sys.stderr)
        return 2
    state, files = load(), repo_files()
    specs = state.get("specs", {})
    try:
        settings = scoring(state)
    except SettingError as e:
        print(f"bad setting: {e}", file=sys.stderr)
        return 2
    if unknown := [n for n in names if n not in specs]:
        print(f"unknown capability: {', '.join(unknown)}", file=sys.stderr)
        return 2
    results = None
    if tests_from is not None:
        try:
            report = run_tests(state) if tests_from == "run" else Path(tests_from)
            results = tested(specs, files, read_junit(report))
        except TestsError as e:
            print(e, file=sys.stderr)
            return 2
    hashes = cached_hashes()
    paths = {name: matched(specs[name], files) for name in names or specs}
    # Only stamped capabilities have a closure to compare; the rest report as before.
    imports = import_signals({n: p for n, p in paths.items()
                              if specs[n].get("anchors") and specs[n].get("ref")
                              and "anchorsFiles" in specs[n]}, settings)
    report = []
    for name in names or specs:
        spec = specs[name]
        row = assess(spec, paths[name], settings, hashes, imports.get(name),
                     None if results is None else results.get(name, ([], False)))
        out = {"capability": name, "status": row["status"]}
        if row["status"] == "code-moved":
            out["syncedCommit"] = spec.get("syncedCommit")
            out["changed"] = row["changed"]
        out.update(chance=row["chance"], confidence=row["confidence"], reasons=row["reasons"])
        report.append(out)
    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        for r in report:
            line = f"{r['status']:<17} {r['capability']}"
            if r["status"] in ("in-sync", "no-spec", "no-anchors"):
                print(line)
                continue
            if r["status"] == "code-moved":
                line += f"  (since {(r['syncedCommit'] or '?')[:9]})"
            line += f"  {meter(r['chance'], r['confidence'], color)}"
            print(line + "".join(f"\n                  {reason}" for reason in r["reasons"]))
    return 1 if any(r["status"] in DRIFTED for r in report) else 0


def cmd_stamp(args):
    state, files = load(), repo_files()
    specs = state.get("specs", {})
    names = list(specs) if "--all" in args else [a for a in args if not a.startswith("--")]
    if not names:
        sys.exit("stamp needs capability names or --all")
    if unknown := [n for n in names if n not in specs]:
        sys.exit(f"unknown capability: {', '.join(unknown)}")
    try:
        settings = scoring(state)
    except SettingError as e:
        print(f"bad setting: {e}", file=sys.stderr)
        return 2
    head = head_commit()
    dirty = uncommitted() if head else set(files)
    closures = stamp_closures(names, specs, files, settings)
    for name in names:
        paths = matched(specs[name], files)
        specs[name]["anchorsFiles"] = file_hashes(paths)
        specs[name]["syncedCommit"] = head
        line = f"stamped {name}: {len(paths)} files at {(head or 'no commit')[:9]}"
        if closure := closures.get(name):
            line += (f"; imports: {len(closure['symbols'])} symbols in {len(closure['files'])} "
                     f"files, by {closure['mode']}")
        print(line, flush=True)
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
    # Artifacts over it drop the same paths, unless another capability they cover keeps them.
    specs, domains = state["specs"], state.get("domains", {})
    trimmed = 0
    for art in state.get("artifacts", {}).values():
        covers = resolve(art.get("capabilities", []), specs, domains)
        if args[0] not in covers:
            continue
        compiled_all = [compile_anchors(specs[c]) for c in covers]
        checked = art.get("checkedFiles", {})
        art["checkedFiles"] = {p: h for p, h in checked.items()
                               if any(matching_anchors(c, p) for c in compiled_all)}
        trimmed += len(checked) - len(art["checkedFiles"])
    closure = prune_closure(args[0], spec, state)
    save(state)
    print(f"pruned {args[0]}: dropped {len(old) - len(kept)} of {len(old)} stamps"
          + (f"; {trimmed} artifact stamps" if trimmed else "") + (f"; {closure}" if closure else ""))
    return 0


def prune_closure(name, spec, state):
    """Re-record a capability's closure for the anchors it has now, keeping the stamped hash
    of every file, symbol and locked version still in it, so what moved since the stamp still
    reads as moved and only what the narrower anchors no longer reach is dropped. A capability
    with no closure stamped gets none (recording one now would hide what moved since its
    stamp). Returns a phrase for prune's line, or None when there was nothing to re-record."""
    stamped = read_closure(name)
    if stamped is None:
        return None
    try:
        settings = scoring(state)
    except SettingError as e:
        print(f"  closure kept as stamped: bad setting: {e}", file=sys.stderr)
        return None
    files = repo_files()
    entries = ts_entries(matched(spec, files))
    if not entries:
        remove_closure(name)
        return "closure removed (no TS/JS files left)"
    found, why = run_helper({name: entries}, settings)
    mode = "symbol" if found else "file"
    if mode != stamped.get("mode"):
        # Hashes taken by symbol and by file don't compare; keep the wider, older closure,
        # which can only over-report, until a sync restamps it.
        print(f"  closure kept as stamped: it was followed by {stamped.get('mode')}, and now "
              f"would be by {mode}" + (f" ({why})" if why else "")
              + "; stamp the capability after a sync to re-record it", file=sys.stderr)
        return None
    if why:
        notice(why)
    fresh = (build_closure("symbol", found["closures"][name], locked_versions()) if found
             else build_closure("file", file_closure(entries, files, settings), locked_versions(),
                                why or stamped.get("why")))
    for f, rec in fresh["files"].items():
        if f in stamped["files"]:
            rec["hash"] = stamped["files"][f].get("hash")
    old_symbols = {(s["file"], s["symbol"]): s.get("hash") for s in stamped.get("symbols", [])}
    for s in fresh["symbols"]:
        if (s["file"], s["symbol"]) in old_symbols:
            s["hash"] = old_symbols[(s["file"], s["symbol"])]
    if isinstance(stamped.get("locked"), dict):
        fresh["locked"] = {pkg: stamped["locked"].get(pkg, v) for pkg, v in fresh["locked"].items()}
    else:
        del fresh["locked"]  # stamped before versions were recorded: still no lockfile signal
    closure_path(name).write_text(dump_closure(fresh))
    dropped = (len(stamped["files"]) - len(set(stamped["files"]) & set(fresh["files"])),
               len(old_symbols) - len(old_symbols.keys() & {(s["file"], s["symbol"])
                                                            for s in fresh["symbols"]}))
    return f"closure re-recorded, {dropped[0]} files and {dropped[1]} symbols dropped"


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


MAX_TAG_BYTES = 1 << 20  # larger files are data, not tests
# A tag is a line comment holding `@scenario <capability>: <scenario name>`; coverage.py
# parses it, rename rewrites it, and both use this one grammar.
TAG = re.compile(r"^\s*(?://+!?|#+|--+|/\*+!?|\*+|<!--)\s*@scenario\b[ \t]*(.*?)\s*$")


def tag_files(files, unreadable=None):
    """(path, bytes) for each repo file that may hold @scenario tags: regular files (not
    symlinks) up to MAX_TAG_BYTES outside .blueprint/, holding `@scenario`, with no NUL in
    their first 8 KB. Files that can't be read are skipped, and named in `unreadable`
    ("path (reason)") when a list is given."""
    for f in files:
        if f.startswith(".blueprint/"):
            continue
        full = ROOT / f
        try:
            if full.is_symlink() or full.stat().st_size > MAX_TAG_BYTES:
                continue
            data = full.read_bytes()
        except OSError as e:
            if unreadable is not None:
                unreadable.append(f"{f} ({e.strerror or e})")
            continue
        if b"@scenario" not in data or b"\0" in data[:8192]:
            continue
        yield f, data


def tag_line(line):
    """The text after `@scenario` when this line (bytes, any encoding) is a tag, else None."""
    m = TAG.match(line.decode("utf-8", "replace").lstrip("\ufeff"))
    return m and m.group(1)


# Each tag learns the name of the test declared right below it, past blank lines, comments
# (other tags among them) and decorators or attributes, so a JUnit report can be matched to it.
TAG_END = re.compile(r"\s*(?:\*+/|-->)\s*$")
_COMMENT = re.compile(r"^\s*(?://|#(?!!?\[)|--|/\*|\*|<!--)")
_ATTRIBUTE = re.compile(r"^\s*(?:@[A-Za-z_]|#!?\[)")
_JS_TEST = re.compile(r"""^\s*(?:test|it|describe)(?:\.\w+)*\s*\(\s*(['"`])((?:\\.|(?!\1).)*)\1""")
_PY_TEST = re.compile(r"^\s*(?:async\s+)?def\s+(test\w*)\s*\(")
_GO_TEST = re.compile(r"^\s*func\s+(Test\w*)\s*\(")
_RUST_FN = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(\w+)")
# `#[test]`, `#[tokio::test]`, `#[rstest]`, `#[test_case(…)]`; not `#[cfg(test)]`.
_RUST_TEST = re.compile(r"^\s*#\[\s*(?:\w+::)*(?:test|rstest|test_case)\b")


def test_below(lines, i):
    """The name of the test declared first below lines[i], or None when the first code line
    there declares none: `test`/`it`/`describe` calls in JS/TS, `def test_…` in Python,
    `func Test…` in Go, the `fn` after a `#[…test…]` attribute in Rust."""
    rust_test, depth = False, 0
    for line in lines[i + 1:]:
        if depth > 0:  # inside a decorator's arguments
            depth += line.count("(") - line.count(")")
            continue
        if not line.strip():
            continue
        if _ATTRIBUTE.match(line):
            rust_test = rust_test or bool(_RUST_TEST.match(line))
            depth = line.count("(") - line.count(")")
            continue
        if _COMMENT.match(line):
            continue
        if m := _JS_TEST.match(line):
            return re.sub(r"\\(.)", r"\1", m.group(2))
        if m := _PY_TEST.match(line) or _GO_TEST.match(line):
            return m.group(1)
        if rust_test and (m := _RUST_FN.match(line)):
            return m.group(1)
        return None
    return None


def declared_tests(text):
    """The names of every test declared in text, as test_below reads them."""
    names, rust_test = set(), False
    for line in text.split("\n"):
        if _RUST_TEST.match(line):
            rust_test = True
        elif m := _JS_TEST.match(line):
            names.add(re.sub(r"\\(.)", r"\1", m.group(2)))
        elif m := _PY_TEST.match(line) or _GO_TEST.match(line):
            names.add(m.group(1))
        elif rust_test and (m := _RUST_FN.match(line)):
            names.add(m.group(1))
            rust_test = False
        elif line.strip() and not (_ATTRIBUTE.match(line) or _COMMENT.match(line)):
            rust_test = False
    return names


def scan_tags(text):
    """[(line, capability, scenario, test name)] for each tag in text; capability None when
    the tag is malformed (scenario then holds its text), test name None when no test follows."""
    lines, tags = text.split("\n"), []
    for n, line in enumerate(lines, 1):
        m = TAG.match(line)
        if not m:
            continue
        rest = TAG_END.sub("", m.group(1))
        cap, sep, name = rest.partition(":")
        cap, name = cap.strip().strip("`"), " ".join(name.split())
        test = test_below(lines, n - 1)
        if not sep or not cap or not name or " " in cap:
            tags.append((n, None, rest, test))
        else:
            tags.append((n, cap, name, test))
    return tags


def tag_rewrites(old, new):
    """({path: (new bytes, tags rewritten)}, [unreadable "path (reason)"]) pointing
    `@scenario OLD: …` tags at NEW. Reads only. Bytes are edited in place, so encodings and
    line endings survive."""
    # The colon right after the name keeps `board` from matching `@scenario board/ops: …`;
    # coverage also accepts the name in backticks.
    tag = re.compile(rb"(@scenario[ \t]+`?)" + re.escape(old.encode()) + rb"(`?[ \t]*:)")
    out, unreadable = {}, []
    for f, data in tag_files(repo_files(), unreadable):
        lines = data.split(b"\n")
        hits = 0
        for i, line in enumerate(lines):
            if tag_line(line) is not None:
                lines[i], n = tag.subn(lambda m: m.group(1) + new.encode() + m.group(2), line, 1)
                hits += n
        if hits:
            out[f] = (b"\n".join(lines), hits)
    return out, unreadable


def move_leaving_no_empty_folder(src, dst, base):
    """Move src to dst when it exists, dropping folders the move left empty up to base."""
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    parent = src.parent
    while parent != base and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent
    return True


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
    # Read the tags before changing anything, so every edit is known before the first write.
    rewrites, unreadable = tag_rewrites(old, new)
    base = ROOT / ".blueprint" / "baseline"
    src, dst = base / f"{old}.md", base / f"{new}.md"
    if dst.exists():
        # A leftover baseline would silently become the renamed capability's merge base.
        sys.exit(f"baseline already exists: {dst.relative_to(ROOT)}")
    if closure_path(new).exists():
        sys.exit(f"closure already exists: {closure_path(new).relative_to(ROOT)}")
    # Rebuild in place so the key keeps its position, and with it the order of check's report.
    state["specs"] = {(new if k == old else k): v for k, v in specs.items()}
    renamed = []
    for aid, art in state.get("artifacts", {}).items():
        if old in art.get("capabilities", []):
            art["capabilities"] = [new if c == old else c for c in art["capabilities"]]
            renamed.append(aid)
    has_baseline = move_leaving_no_empty_folder(src, dst, base)
    has_closure = move_leaving_no_empty_folder(closure_path(old), closure_path(new), CLOSURES)
    save(state)
    failed, tags = [], 0
    for f, (data, n) in rewrites.items():
        try:
            (ROOT / f).write_bytes(data)
            tags += n
        except OSError as e:
            failed.append(f"{f} ({e.strerror or e})")
    print(f"renamed {old} to {new}" + ("; baseline moved" if has_baseline else "")
          + ("; closure moved" if has_closure else "")
          + (f"; {len(renamed)} artifacts updated" if renamed else "")
          + (f"; {tags} tags rewritten" if tags else ""))
    if failed:
        print(f"  couldn't rewrite the {old} tags in: " + ", ".join(failed)
              + f"; change them to {new} by hand", file=sys.stderr)
    if unreadable:
        print("  couldn't read, so any tags in them still name "
              + f"{old}: " + ", ".join(unreadable), file=sys.stderr)
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
# A git URL with a path after the host: scheme://host/path or scp-style user@host:path.
GIT_URL = re.compile(r"^(?:[a-z][a-z0-9+.-]*://[^/\s]+/\S+|[^@\s/]+@[^:\s/]+:\S+)$")
# The same URL forms on github.com, capturing owner/name.
GITHUB_GIT_URL = re.compile(
    r"^(?:https?://github\.com/|ssh://git@github\.com/|git@github\.com:)"
    r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$")


def value_problem(kind, value):
    """Why value isn't the right shape for an artifact of this type, or None."""
    if kind not in ARTIFACT_TYPES:
        return f"unknown type {kind!r}: use one of {', '.join(ARTIFACT_TYPES)}"
    if kind in URL_TYPES:
        if not re.match(r"^https?://[^\s/]+\S*$", value):
            return f"a {kind} value is a URL (http:// or https://)"
    elif kind == "file":
        repo, sep, path = value.rpartition(":")
        if not sep or not path.strip() or not (GITHUB_REPO.match(repo) or GIT_URL.match(repo)):
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
        m = GITHUB_GIT_URL.match(repo)
        if m or GITHUB_REPO.match(repo):
            owner_name = m.group(1) if m else repo
            return f"https://github.com/{owner_name}/blob/HEAD/{quote(path.lstrip('/'))}"
    return None


def open_link(kind, value):
    """Where a browser can open the artifact: file_link, plus obsidian:// URLs, which a
    browser hands to the Obsidian app. None when nothing can open it."""
    link = file_link(kind, value)
    if link is None and kind == "obsidian" and value.startswith("obsidian://"):
        link = value
    return link


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


def artifact_files(covers, specs, files, memo=None):
    """The files the anchors of these capabilities match, now. memo ({name: files}) is
    shared across artifacts so each capability's anchors are matched once."""
    memo = {} if memo is None else memo
    paths = set()
    for name in covers:
        if name not in memo:
            memo[name] = matched(specs[name], files)
        paths.update(memo[name])
    return sorted(paths)


def dangling(art, specs, domains):
    """The names in an artifact's capabilities that are no longer a capability or a domain."""
    return unknown_names(art.get("capabilities", []), specs, domains)


def artifact_state(art, specs, domains, files, hashes, memo):
    """An artifact's capabilities now (covers), the files changed since its check (changed)
    and the names that are gone (unknown): stale when either of the last two is non-empty."""
    covers = resolve(art.get("capabilities", []), specs, domains)
    changed = changed_files(art.get("checkedFiles", {}),
                            hashes(artifact_files(covers, specs, files, memo)))
    return covers, changed, dangling(art, specs, domains)


def artifact_ids(args, arts, what):
    if "--all" in args:
        return list(arts)
    ids = [a for a in args if not a.startswith("--")]
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
    hashes, memo = cached_hashes(), {}

    report = []
    for aid, art in state.get("artifacts", {}).items():
        # A name that no longer exists (renamed or removed by hand) is always reported, even
        # under a filter, since it can't be told which capability it was meant to cover.
        if (names and not dangling(art, specs, domains)
                and not wanted.intersection(resolve(art.get("capabilities", []), specs, domains))):
            continue
        _, changed, unknown = artifact_state(art, specs, domains, files, hashes, memo)
        if changed or unknown:
            report.append({"id": aid, "type": art.get("type"), "value": art.get("value"),
                           "link": file_link(art.get("type"), art.get("value", "")),
                           "description": art.get("description", ""),
                           "capabilities": art.get("capabilities", []), "changed": changed,
                           "unknown": unknown})
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        for r in report:
            print(f"{r['id']}  {r['type']}  {r['value']}")
            if r["description"]:
                print(f"    {r['description']}")
            if r["unknown"]:
                print(f"    unknown capability: {', '.join(r['unknown'])}: fix its capabilities")
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
    art["checkedFiles"] = file_hashes(artifact_files(resolve(caps, specs, domains), specs,
                                                     repo_files()))
    state.setdefault("artifacts", {})[aid] = art
    save(state)
    print(f"added {aid}: {len(art['checkedFiles'])} files checked")
    return 0


def artifacts_checked(args):
    state, files = load(), repo_files()
    specs, domains = state.get("specs", {}), state.get("domains", {})
    arts = state.get("artifacts", {})
    ids = artifact_ids(args, arts, "checked")
    # Stamping one with a dangling name would hide it for good: its files would never change.
    if bad := [f"{a} ({', '.join(u)})" for a in ids if (u := dangling(arts[a], specs, domains))]:
        sys.exit(f"unknown capability in artifact: {'; '.join(bad)}: fix its capabilities first")
    hashes, memo = cached_hashes(), {}
    for aid in ids:
        covers = resolve(arts[aid].get("capabilities", []), specs, domains)
        arts[aid]["checkedFiles"] = hashes(artifact_files(covers, specs, files, memo))
        print(f"checked {aid}: {len(arts[aid]['checkedFiles'])} files")
    save(state)
    return 0


def artifacts_remove(args):
    if len(args) != 1 or args[0].startswith("--"):
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
    if args and args[0] == "--":
        # `artifacts -- remove`: a filter by a capability that shares a subcommand's name.
        args = args[1:]
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
