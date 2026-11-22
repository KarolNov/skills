#!/usr/bin/env python3
"""Trace spec scenarios to the tests that claim them. Reads only; writes nothing.

    python3 coverage.py [<capability>] [--json] [--strict | --strict=all] [--delta FILE]

A test claims a scenario with a comment line holding `@scenario <capability>: <scenario name>`,
in any line comment (//, #, --, /* */, *, <!-- -->), usually just above the test. Scenarios
come from .blueprint/baseline/; each claiming test gets the first kind in blueprint.json's
`tests.kinds` (kind -> globs) whose globs match its file. Without `tests.kinds` the script
exits 2: it never guesses kinds.

The report lists, per capability with a baseline, every requirement and scenario with the
tests that claim it (file:line, kind), then a summary of scenarios claimed per kind, then
the problems: orphan tags (unknown capability or scenario, with the nearest name), tags in
files no kind matches (unclassified), duplicate scenario names within a capability, and
tags for capabilities that have no spec yet. A claim says a test points at the scenario;
nothing is run.

  <capability>  limit the report and the gate to one capability
  --json        print the same data as JSON
  --strict      exit 1 on orphans, unclassified tags or duplicates
  --strict=all  also exit 1 when any scenario is uncovered
  --delta FILE  a brief (or its Spec delta) in markdown: its ADDED and MODIFIED scenarios
                count as known, marked pending; its REMOVED requirements' scenarios are gone

Run from anywhere inside the repository. Standard library only.
"""

import difflib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import drift  # noqa: E402  (finds the repo root on import)
from graph import parse_baseline  # noqa: E402
from notion_normalize import normalize  # noqa: E402

_TAG = drift.TAG  # one tag grammar, shared with drift.py rename
_TAG_END = re.compile(r"\s*(?:\*+/|-->)\s*$")
_SCENARIO = re.compile(r"^\s*[-*]\s*(?:\*\*|<b>)\s*Scenario:\s*(.+?)\s*(?:\*\*|</b>)", re.M)
_DELTA = re.compile(r"^## Spec delta[ \t]*\n(.*?)(?=^## |\Z)", re.S | re.M)
_DELTA_CAP = re.compile(r"^###[ \t]+(\S+)[ \t]*·[ \t]*(ADDED|MODIFIED|REMOVED|RENAMED)[ \t]*$", re.M)
_DELTA_REQ = re.compile(r"^####[ \t]+Requirement:[ \t]*(.*?)[ \t]*\n(.*?)(?=^#### |\Z)", re.S | re.M)
_LIST_ITEM = re.compile(r"^\s*[-*]\s+(.+?)\s*$", re.M)
_MARKUP = re.compile(r"</?(?:b|code|i|em|strong)>|\*\*|`")


class Usage(Exception):
    """A problem with the setup or the arguments: exit 2, report nothing."""


def norm(name):
    """A name as tags match it: markup dropped, whitespace collapsed, case folded."""
    return " ".join(_MARKUP.sub("", name).split()).casefold()


def plain(name):
    return " ".join(_MARKUP.sub("", name).split())


# ---- spec side -------------------------------------------------------------------------

def scenarios_in(body):
    return [plain(s) for s in _SCENARIO.findall(body)]


def baseline_requirements(name):
    """[(requirement, [scenario])] from the capability's baseline, or None without one."""
    path = drift.ROOT / ".blueprint" / "baseline" / f"{name}.md"
    if not path.is_file():
        return None
    _, reqs = parse_baseline(path.read_text(encoding="utf-8"))
    return [(plain(r["title"]), scenarios_in(r["body"])) for r in reqs]


def parse_delta(text):
    """{capability: {kind: [...]}}: ADDED/MODIFIED hold [(requirement, [scenario])],
    REMOVED [requirement], RENAMED [(old, new)]."""
    m = _DELTA.search(text)
    text = m.group(1) if m else text
    out = {}
    heads = list(_DELTA_CAP.finditer(text))
    for i, h in enumerate(heads):
        body = text[h.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        cap, kind = h.group(1).strip("`"), h.group(2)
        slot = out.setdefault(cap, {}).setdefault(kind, [])
        if kind in ("ADDED", "MODIFIED"):
            slot += [(plain(t), scenarios_in(b)) for t, b in _DELTA_REQ.findall(body)]
        elif kind == "REMOVED":
            for item in _LIST_ITEM.findall(body):
                bold = re.match(r"(?:\*\*|<b>)(.+?)(?:\*\*|</b>)", item)
                slot.append(plain(bold.group(1) if bold else item.split(":")[0]))
        else:
            for item in _LIST_ITEM.findall(body):
                parts = re.split(r"\s*(?:→|->)\s*", item, maxsplit=1)
                if len(parts) == 2:
                    slot.append((plain(parts[0]), plain(parts[1])))
    return out


def apply_delta(reqs, change):
    """The requirements as they read once the delta is folded, each scenario as
    (name, pending): RENAMED, REMOVED, MODIFIED (whole block by name), then ADDED."""
    known = {norm(s) for _, scen in reqs for s in scen}
    reqs = [(r, [(s, False) for s in scen]) for r, scen in reqs]
    for old, new in change.get("RENAMED", []):
        reqs = [(new if norm(r) == norm(old) else r, scen) for r, scen in reqs]
    gone = {norm(r) for r in change.get("REMOVED", [])}
    reqs = [(r, scen) for r, scen in reqs if norm(r) not in gone]
    for kind in ("MODIFIED", "ADDED"):
        for name, scen in change.get(kind, []):
            block = (name, [(s, norm(s) not in known) for s in scen])
            at = next((i for i, (r, _) in enumerate(reqs) if norm(r) == norm(name)), None)
            if at is None:
                reqs.append(block)
            else:
                reqs[at] = block
    return reqs


def capabilities(specs, delta):
    """{capability: [(requirement, [(scenario, pending)])] or None when it has no spec yet}."""
    out = {}
    for name in sorted(set(specs) | {c for c, ch in delta.items() if ch.get("ADDED")}):
        reqs = baseline_requirements(name)
        if reqs is None and (specs.get(name) or {}).get("ref"):
            raise Usage(f"{name} has a spec but no .blueprint/baseline/{name}.md: sync it first")
        change = delta.get(name)
        if change:
            reqs = apply_delta(reqs or [], change)
        elif reqs is not None:
            reqs = [(r, [(s, False) for s in scen]) for r, scen in reqs]
        out[name] = reqs
    return out


# ---- test side -------------------------------------------------------------------------

def kinds_of(state):
    tests = state.get("tests")
    kinds = tests.get("kinds") if isinstance(tests, dict) else None
    if kinds is None:
        raise Usage("tests.kinds is required in .blueprint/blueprint.json (a map of kind name "
                    "to globs, first match wins); /blueprint coverage proposes one")
    if not isinstance(kinds, dict) or not kinds or not all(
            isinstance(g, list) and g and all(isinstance(p, str) for p in g) for g in kinds.values()):
        raise Usage('tests.kinds must map each kind name to a non-empty list of globs, '
                    'e.g. {"unit": ["**/*.test.ts"], "e2e": ["e2e/**"]}')
    return [(k, [drift.glob_re(p) for p in g]) for k, g in kinds.items()]


def kind_of(path, kinds):
    return next((k for k, res in kinds if any(r.match(path) for r in res)), None)


def scan_text(text):
    """[(line, capability, scenario)] for each tag; capability None when malformed."""
    tags = []
    for n, line in enumerate(text.split("\n"), 1):
        m = _TAG.match(line)
        if not m:
            continue
        rest = _TAG_END.sub("", m.group(1))
        cap, sep, name = rest.partition(":")
        cap, name = cap.strip().strip("`"), " ".join(name.split())
        if not sep or not cap or not name or " " in cap:
            tags.append((n, None, rest))
        else:
            tags.append((n, cap, name))
    return tags


def scan(files):
    """[{file, line, capability, scenario}] across the repo's text files."""
    tags = []
    for path, data in drift.tag_files(files):
        for line, cap, name in scan_text(data.decode("utf-8-sig", "replace")):
            tags.append({"file": path, "line": line, "capability": cap, "scenario": name})
    return tags


# ---- the report ------------------------------------------------------------------------

def _keeps(a, b):
    """Whether b holds a's words in order (words added around or between them)."""
    rest = iter(b.split())
    return all(w in rest for w in a.split())


_KEPT_MARGIN = 0.1  # how much closer as text a name may be and still lose to a kept one


def nearest(word, names):
    """The closest of names, or None. A close name that keeps word's words in order, or whose
    words word keeps (words added or dropped: how a scenario is usually reworded), wins over one
    a little closer as text, so `Filters buyer` suggests `Filters buyer quickly`, not
    `Flags buyer`. A name much closer still wins: `Rejects expird token` is a typo of
    `Rejects expired token`, not a longer `Rejects token`."""
    w, normed = norm(word), {norm(n): n for n in reversed(names)}
    if not normed:
        return None
    score = {c: difflib.SequenceMatcher(None, w, c).ratio()
             for c in difflib.get_close_matches(w, list(normed), n=len(normed), cutoff=0.6)}
    if not score:
        return None
    best = max(score, key=score.get)
    kept = [c for c in score if score[c] >= score[best] - _KEPT_MARGIN
            and (_keeps(w, c) or _keeps(c, w))]
    return normed[kept[0] if kept else best]


def build(state=None, files=None, delta=None, only=None):
    """The coverage data, as --json prints it. `delta` is parse_delta's output."""
    state = drift.load() if state is None else state
    kinds = kinds_of(state)
    specs = state.get("specs", {})
    caps = capabilities(specs, delta or {})
    if only is not None and only not in caps:
        hint = nearest(only, list(caps))
        raise Usage(f"unknown capability: {only}" + (f" (did you mean {hint}?)" if hint else ""))
    tags = scan(drift.repo_files() if files is None else files)

    index, duplicates = {}, []
    for cap, reqs in caps.items():
        for req, scen in reqs or []:
            for s, _ in scen:
                key = (cap, norm(s))
                if key in index:
                    duplicates.append({"capability": cap, "scenario": s,
                                       "requirements": [index[key], req]})
                index.setdefault(key, req)

    claims, orphans, no_spec, unclassified = {}, [], [], []
    for t in tags:
        t = dict(t, kind=kind_of(t["file"], kinds))
        if t["kind"] is None:
            unclassified.append(t)
        cap = t["capability"]
        if cap is None:
            orphans.append(dict(t, reason="malformed tag", suggestion=None))
        elif cap not in caps:
            orphans.append(dict(t, reason="unknown capability", suggestion=nearest(cap, list(caps))))
        elif caps[cap] is None:
            no_spec.append(t)
        elif (cap, norm(t["scenario"])) not in index:
            names = [s for _, scen in caps[cap] for s, _ in scen]
            orphans.append(dict(t, reason="unknown scenario", suggestion=nearest(t["scenario"], names)))
        else:
            claims.setdefault((cap, norm(t["scenario"])), []).append(
                {"file": t["file"], "line": t["line"], "kind": t["kind"]})

    kind_names = [k for k, _ in kinds]
    out_caps, total, claimed, by_kind = [], 0, 0, dict.fromkeys(kind_names, 0)
    for cap, reqs in caps.items():
        if reqs is None or (only is not None and cap != only):
            continue
        c_total = c_claimed = 0
        out_reqs = []
        for req, scen in reqs:
            out_scen = []
            for s, pending in scen:
                cl = claims.get((cap, norm(s)), [])
                out_scen.append({"name": s, "pending": pending, "claims": cl})
                c_total += 1
                c_claimed += bool(cl)
                for k in {c["kind"] for c in cl if c["kind"]}:
                    by_kind[k] += 1
            out_reqs.append({"name": req, "scenarios": out_scen})
        total, claimed = total + c_total, claimed + c_claimed
        out_caps.append({"name": cap, "claimed": c_claimed, "total": c_total,
                         "requirements": out_reqs})

    def keep(items):
        # An unknown capability whose nearest name is `only` is a typo aimed at it.
        return items if only is None else [i for i in items if i["capability"] == only or (
            i.get("reason") == "unknown capability" and i.get("suggestion") == only)]

    return {
        "kinds": kind_names,
        "capabilities": out_caps,
        "summary": {"claimed": claimed, "total": total, "byKind": by_kind},
        "orphans": keep(orphans),
        "unclassified": keep(unclassified),
        "duplicates": keep(duplicates),
        "noSpec": keep(no_spec),
    }


def where(c):
    return f"{c['file']}:{c['line']}"


def text_report(data):
    lines = []
    for cap in data["capabilities"]:
        lines.append(f"{cap['name']}: {cap['claimed']} of {cap['total']} scenarios claimed")
        for req in cap["requirements"]:
            lines.append(f"  {req['name']}")
            if not req["scenarios"]:
                lines.append("    (no scenarios)")
            for s in req["scenarios"]:
                tag = " (pending)" if s["pending"] else ""
                if not s["claims"]:
                    lines.append(f"    uncovered  {s['name']}{tag}")
                    continue
                lines.append(f"    claimed    {s['name']}{tag}")
                for c in s["claims"]:
                    lines.append(f"                 {where(c)} ({c['kind'] or 'unclassified'})")
        lines.append("")
    s = data["summary"]
    kinds = ", ".join(f"{k} {n}" for k, n in s["byKind"].items())
    lines.append(f"{s['claimed']} of {s['total']} scenarios claimed" + (f" ({kinds})" if kinds else ""))
    if data["orphans"]:
        lines += ["", f"Orphan tags ({len(data['orphans'])}):"]
        for o in data["orphans"]:
            what = o["scenario"] if o["capability"] is None else f"{o['capability']}: {o['scenario']}"
            hint = f"; nearest: {o['suggestion']}" if o["suggestion"] else ""
            lines.append(f"  {where(o)}  {what}  ({o['reason']}{hint})")
    if data["unclassified"]:
        lines += ["", f"Unclassified tags, in files no tests.kinds glob matches ({len(data['unclassified'])}):"]
        lines += [f"  {where(u)}  {u['capability'] or '?'}: {u['scenario']}" for u in data["unclassified"]]
    if data["duplicates"]:
        lines += ["", f"Duplicate scenario names ({len(data['duplicates'])}):"]
        lines += [f"  {d['capability']}: {d['scenario']}  (in {' and '.join(d['requirements'])})"
                  for d in data["duplicates"]]
    if data["noSpec"]:
        lines += ["", f"Tags for capabilities with no spec yet ({len(data['noSpec'])}):"]
        lines += [f"  {where(t)}  {t['capability']}: {t['scenario']}" for t in data["noSpec"]]
    return "\n".join(lines)


def failed(data, strict):
    if not strict:
        return False
    problems = data["orphans"] or data["unclassified"] or data["duplicates"]
    uncovered = data["summary"]["claimed"] < data["summary"]["total"]
    return bool(problems) or (strict == "all" and uncovered)


def parse_args(argv):
    opts = {"json": False, "strict": None, "delta": None, "only": None}
    it = iter(argv)
    for a in it:
        if a in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        elif a == "--json":
            opts["json"] = True
        elif a == "--strict":
            opts["strict"] = "problems"
        elif a.startswith("--strict="):
            if a != "--strict=all":
                raise Usage(f"unknown --strict value: {a.split('=', 1)[1]} (only --strict=all)")
            opts["strict"] = "all"
        elif a == "--delta" or a.startswith("--delta="):
            opts["delta"] = a.split("=", 1)[1] if "=" in a else next(it, None)
            if not opts["delta"] or opts["delta"].startswith("-"):
                raise Usage("--delta needs a file")
        elif a.startswith("-"):
            raise Usage(f"unknown option: {a}")
        elif opts["only"] is None:
            opts["only"] = a
        else:
            raise Usage("give at most one capability")
    return opts


def main(argv):
    try:
        opts = parse_args(argv)
        delta = None
        if opts["delta"]:
            path = Path(opts["delta"])
            if not path.is_file():
                raise Usage(f"--delta file not found: {opts['delta']}")
            # Through the Notion normalizer, so escapes, entities and spans match the baseline.
            delta = parse_delta(normalize(path.read_text(encoding="utf-8")))
            if not delta:
                raise Usage(f"--delta file has no Spec delta (### <capability> · ADDED|MODIFIED|"
                            f"REMOVED|RENAMED headings): {opts['delta']}")
        data = build(delta=delta, only=opts["only"])
    except Usage as e:
        print(f"coverage.py: {e}", file=sys.stderr)
        return 2
    print(json.dumps(data, indent=2) if opts["json"] else text_report(data))
    return 1 if failed(data, opts["strict"]) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
