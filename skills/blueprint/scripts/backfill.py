#!/usr/bin/env python3
"""Progress of a blueprint backfill, kept in .blueprint/backfill/ until the backfill finishes.

    backfill.py init < PLAN.json      write the folder at the end of pass 1 from the plan the
                                      user accepted: {"survey": {...}, "domains": {name:
                                      {"purpose": "...", "folders": [glob, ...]}}}
    backfill.py status [--json]       where the backfill stands: the current pass, each
                                      domain's passes, and the next steps; exit 0, also when
                                      no backfill is in progress
    backfill.py uncovered DOMAIN [--json]
                                      tracked files in the domain's folders that no capability
                                      anchors and that aren't marked glue
    backfill.py stamp CAPABILITY ...  record the anchored files' hashes and HEAD in the
                                      capability's domain progress file, as drift.py stamp
                                      does in blueprint.json (writes the closure the same way)
    backfill.py pass DOMAIN N STATE   set pass N (2-5) of DOMAIN to pending, in-progress or done
    backfill.py fold [DOMAIN ...]     merge every domain that finished pass 3 (or those named)
                                      into blueprint.json and mark it folded; exit 1 if a named
                                      domain can't fold yet, saying why

The folder:

    .blueprint/backfill/
      README.md                       says a backfill is in progress, at which pass, how to
                                      resume; rewritten by init, pass and fold
      progress.json                   {"version": 1, "passes": {"1": STATE}, "survey": {...},
                                       "domains": {name: {"purpose", "folders"}}}
      domains/<domain>.progress.json  one per domain, written only by that domain's session:
                                      {"domain", "passes": {"2".."5": STATE}, "ref" (the
                                       domain overview page), "covered" (user confirmed),
                                       "glue": [glob], "folded": bool,
                                       "capabilities": {name: {"purpose", "anchors",
                                         "existing" (already in blueprint.json), "ref",
                                         "specVersion", "anchorsFiles", "syncedCommit",
                                         "review": {"accepted", "amended", "rejected"}}}}
      drafts/<capability>.md          spec drafts awaiting scenario review

A domain session never writes blueprint.json: only fold does, for every finished domain at
once, so parallel domain sessions don't conflict. Baselines go to .blueprint/baseline/ and
closures to .blueprint/closure/ as usual: one file per capability, so they don't conflict
either. Anchors match as in drift.py. Run from anywhere inside the repository. Standard
library only.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import drift  # noqa: E402  (finds the repo root on import)

FOLDER = drift.ROOT / ".blueprint" / "backfill"
PROGRESS = FOLDER / "progress.json"
DOMAINS = FOLDER / "domains"
DRAFTS = FOLDER / "drafts"
README = FOLDER / "README.md"

PASSES = {1: "survey", 2: "capabilities and anchors", 3: "spec drafts and scenario review",
          4: "test tags", 5: "artifacts"}
DOMAIN_PASSES = (2, 3, 4, 5)
# What a domain that finished pass n is, for the status line ("2 of 4 domains reviewed").
FINISHED = {2: "mapped", 3: "reviewed", 4: "tagged", 5: "done"}
STATES = ("pending", "in-progress", "done")


class Problem(Exception):
    """Bad arguments or a malformed progress file: exit 2 with the message."""


# ---- the files -------------------------------------------------------------------------

def rel(path):
    return path.relative_to(drift.ROOT).as_posix()


def read_json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise Problem(f"{rel(path)} isn't valid JSON: {e}")
    if not isinstance(data, dict):
        raise Problem(f"{rel(path)} isn't a JSON object")
    return data


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_progress():
    if not PROGRESS.is_file():
        raise Problem("no backfill in progress: .blueprint/backfill/progress.json not found")
    progress = read_json(PROGRESS)
    domains = progress.get("domains")
    if not isinstance(domains, dict):
        raise Problem(f"{rel(PROGRESS)} has no \"domains\" object")
    for name, plan in domains.items():
        if not isinstance(plan, dict) or not isinstance(plan.get("folders", []), list):
            raise Problem(f"{rel(PROGRESS)}: domain {name} needs \"folders\" as a list")
    return progress


def domain_path(name):
    return DOMAINS / f"{name}.progress.json"


def load_domain(name):
    """A domain's progress file, or a fresh one when its session hasn't written it yet."""
    path = domain_path(name)
    data = read_json(path) if path.is_file() else {}
    data.setdefault("domain", name)
    passes = data.setdefault("passes", {})
    for n in DOMAIN_PASSES:
        state = passes.setdefault(str(n), "pending")
        if state not in STATES:
            raise Problem(f"{rel(path)}: pass {n} is {state!r}, not one of {', '.join(STATES)}")
    if not isinstance(data.setdefault("capabilities", {}), dict):
        raise Problem(f"{rel(path)}: \"capabilities\" isn't an object")
    data.setdefault("glue", [])
    data.setdefault("folded", False)
    return data


def known_domain(progress, name):
    if name not in progress["domains"]:
        raise Problem(f"unknown domain: {name} (the backfill's domains: "
                      f"{', '.join(progress['domains']) or 'none'})")


def domain_of(progress, capability):
    domain = capability.split("/")[0] if "/" in capability else None
    if domain in progress["domains"]:
        return domain
    # A bare capability already in blueprint.json may be listed under any domain.
    for name in progress["domains"]:
        if capability in load_domain(name)["capabilities"]:
            return name
    raise Problem(f"{capability} belongs to none of the backfill's domains")


def drafts_of(domain):
    folder = DRAFTS / domain
    return sorted(f"{domain}/{p.stem}" for p in folder.glob("*.md")) if folder.is_dir() else []


# ---- where things stand ----------------------------------------------------------------

def next_pass(dom):
    return next((n for n in DOMAIN_PASSES if dom["passes"][str(n)] != "done"), None)


def overview(progress):
    """Everything status reports, as one dict (the --json output)."""
    pass1 = progress.get("passes", {}).get("1", "pending")
    domains, files = [], None
    for name, plan in progress["domains"].items():
        dom = load_domain(name)
        if files is None:
            files = drift.repo_files()
        n = next_pass(dom)
        domains.append({
            "name": name,
            "purpose": plan.get("purpose", ""),
            "folders": plan.get("folders", []),
            "passes": {k: dom["passes"][k] for k in map(str, DOMAIN_PASSES)},
            "nextPass": n,
            "covered": bool(dom.get("covered")),
            "folded": bool(dom["folded"]),
            "capabilities": sorted(dom["capabilities"]),
            "drafts": drafts_of(name),
            "uncovered": len(uncovered_files(progress, name, dom, files)),
        })
    if pass1 != "done":
        current, finished = 1, 0
    elif not domains:
        current, finished = 2, 0
    else:
        current = min(d["nextPass"] or 5 for d in domains)
        finished = sum(d["passes"][str(current)] == "done" for d in domains)
    if current == 1:
        line = "Backfill · pass 1 of 5 · survey"
    else:
        line = (f"Backfill · pass {current} of 5 · {finished} of {len(domains)} "
                f"domains {FINISHED[current]}")
    return {"active": True, "pass": current, "passName": PASSES[current], "line": line,
            "passes": {"1": pass1}, "domains": domains, "next": next_steps(pass1, domains)}


def next_steps(pass1, domains):
    if pass1 != "done":
        return [{"command": "/blueprint-backfill", "why": "finish pass 1: survey and domains"}]
    steps = []
    for d in domains:
        n, name = d["nextPass"], d["name"]
        if n is None and d["folded"]:
            continue
        if (n is None or n >= 4) and not d["folded"]:
            steps.append({"command": "/blueprint-backfill fold", "domain": name,
                          "why": f"{name} finished scenario review: fold it into blueprint.json"})
            continue
        state = d["passes"][str(n)]
        steps.append({"command": f"/blueprint-backfill domain {name}", "domain": name,
                      "pass": n, "why": f"pass {n} for {name} ({PASSES[n]})"
                      + (", in progress" if state == "in-progress" else "")})
    if domains and not steps:
        steps.append({"command": "/blueprint-backfill",
                      "why": "every domain is done and folded: finish the backfill"})
    return steps


def cmd_status(args):
    as_json = "--json" in args
    if not PROGRESS.is_file():
        if as_json:
            print(json.dumps({"active": False}))
        else:
            print("no backfill in progress")
        return 0
    report = overview(load_progress())
    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    print(report["line"])
    for d in report["domains"]:
        passes = " ".join(f"{k}:{d['passes'][k]}" for k in d["passes"])
        extra = ["folded" if d["folded"] else "not folded"]
        if d["drafts"]:
            extra.append(f"{len(d['drafts'])} drafts awaiting review")
        if d["uncovered"]:
            extra.append(f"{d['uncovered']} files uncovered")
        print(f"  {d['name']}: {passes} · {len(d['capabilities'])} capabilities · "
              + " · ".join(extra))
    if report["next"]:
        print("next:")
        for step in report["next"]:
            print(f"  {step['command']}  ({step['why']})")
    return 0


# ---- coverage of a domain --------------------------------------------------------------

def uncovered_files(progress, name, dom, files):
    """Files under the domain's folders that no capability anchors and no glue glob matches.
    A capability anywhere in blueprint.json or in any domain's progress file covers a file."""
    folders = [drift.glob_re(g) for g in progress["domains"][name].get("folders", [])]
    glue = [drift.glob_re(g) for g in dom.get("glue", [])]
    specs = list(drift.load().get("specs", {}).values())
    for other in progress["domains"]:
        specs += (dom if other == name else load_domain(other))["capabilities"].values()
    compiled = [drift.compile_anchors(s) for s in specs if isinstance(s, dict)]
    out = []
    for f in files:
        if f.startswith(".blueprint/") or not any(r.match(f) for r in folders):
            continue
        if any(r.match(f) for r in glue) or any(drift.matching_anchors(c, f) for c in compiled):
            continue
        out.append(f)
    return out


def cmd_uncovered(args):
    names = [a for a in args if not a.startswith("--")]
    if len(names) != 1:
        raise Problem("uncovered takes one domain")
    progress = load_progress()
    known_domain(progress, names[0])
    files = uncovered_files(progress, names[0], load_domain(names[0]), drift.repo_files())
    if "--json" in args:
        print(json.dumps(files, indent=2))
    elif files:
        print("\n".join(files))
    return 0


# ---- writers ---------------------------------------------------------------------------

def write_readme(progress):
    current = overview(progress)
    README.write_text(
        "# Blueprint backfill\n\n"
        f"Blueprint backfill in progress: pass {current['pass']} of 5 "
        f"({current['passName']}). Resume with `/blueprint-backfill`. "
        "This folder is deleted when the backfill finishes.\n\n"
        f"{current['line']}\n", encoding="utf-8")


def cmd_init(args):
    if PROGRESS.exists():
        raise Problem("a backfill is already in progress: .blueprint/backfill/progress.json "
                      "exists (see `backfill.py status`)")
    try:
        plan = json.loads(sys.stdin.read())
    except ValueError as e:
        raise Problem(f"the plan on stdin isn't valid JSON: {e}")
    domains = plan.get("domains") if isinstance(plan, dict) else None
    if not isinstance(domains, dict) or not domains:
        raise Problem("the plan needs \"domains\": {name: {\"purpose\", \"folders\"}}")
    specs = drift.load().get("specs", {})
    for name, d in domains.items():
        if "/" in name or not name or name in specs:
            raise Problem(f"{name} can't be a domain: domains are one level deep and never a "
                          "capability")
        if not isinstance(d, dict) or not d.get("folders") or not isinstance(d["folders"], list):
            raise Problem(f"domain {name} needs \"folders\": a list of globs")
    progress = {"version": 1, "passes": {"1": "done"}, "survey": plan.get("survey", {}),
                "domains": {n: {"purpose": d.get("purpose", ""), "folders": d["folders"]}
                            for n, d in domains.items()}}
    write_json(PROGRESS, progress)
    DOMAINS.mkdir(exist_ok=True)
    DRAFTS.mkdir(exist_ok=True)
    write_readme(progress)
    print(f"wrote {rel(FOLDER)}/ with {len(domains)} domains; next sessions:")
    for name in domains:
        print(f"  /blueprint-backfill domain {name}")
    return 0


def cmd_pass(args):
    if len(args) != 3:
        raise Problem("pass takes DOMAIN N STATE")
    name, n, state = args
    progress = load_progress()
    known_domain(progress, name)
    if n not in map(str, DOMAIN_PASSES):
        raise Problem(f"pass {n} isn't a domain pass (2 to 5)")
    if state not in STATES:
        raise Problem(f"state {state} isn't one of {', '.join(STATES)}")
    dom = load_domain(name)
    if int(n) >= 4 and state != "pending" and not dom["folded"]:
        raise Problem(f"{name} isn't folded yet: run `backfill.py fold {name}` before pass {n}")
    dom["passes"][n] = state
    write_json(domain_path(name), dom)
    write_readme(progress)
    print(f"{name}: pass {n} {state}")
    return 0


def cmd_stamp(args):
    if not args:
        raise Problem("stamp takes capability names")
    progress, state, files = load_progress(), drift.load(), drift.repo_files()
    try:
        settings = drift.scoring(state)
    except drift.SettingError as e:
        raise Problem(f"bad setting: {e}")
    by_domain = {}
    for name in args:
        by_domain.setdefault(domain_of(progress, name), []).append(name)
    head = drift.head_commit()
    dirty = drift.uncommitted() if head else set(files)
    for domain, names in by_domain.items():
        dom = load_domain(domain)
        caps = dom["capabilities"]
        if missing := [n for n in names if n not in caps or not caps[n].get("anchors")]:
            raise Problem(f"no anchors recorded for {', '.join(missing)} in "
                          f"{rel(domain_path(domain))}")
        closures = drift.stamp_closures(names, caps, files, settings)
        for name in names:
            paths = drift.matched(caps[name], files)
            caps[name]["anchorsFiles"] = drift.file_hashes(paths)
            caps[name]["syncedCommit"] = head
            line = f"stamped {name}: {len(paths)} files at {(head or 'no commit')[:9]}"
            if closure := closures.get(name):
                line += f"; imports: {len(closure['files'])} files, by {closure['mode']}"
            print(line, flush=True)
            if pending := dirty.intersection(paths):
                print(f"  warning: {len(pending)} of them uncommitted, so syncedCommit predates "
                      "them; commit the code, then stamp again", file=sys.stderr)
        write_json(domain_path(domain), dom)
    return 0


# ---- fold ------------------------------------------------------------------------------

SPEC_KEYS = ("ref", "specVersion", "anchors", "anchorsFiles", "syncedCommit")


def fold_problems(name, dom, state, taken):
    """Why a domain can't fold yet ([] when it can), and the spec entries it would write."""
    if dom["folded"]:
        return ["already folded"], {}
    if dom["passes"]["3"] != "done":
        return [f"pass 3 is {dom['passes']['3']}, not done"], {}
    specs, domains = state.get("specs", {}), state.get("domains", {})
    problems, entries = [], {}
    if name not in domains and not dom.get("ref"):
        problems.append("no overview page: set \"ref\" in its progress file")
    for cap, rec in sorted(dom["capabilities"].items()):
        current = specs.get(cap)
        if current is not None and current.get("ref"):
            continue  # already specced before the backfill: kept exactly as it is
        if current is None and (why := drift.collision(cap, {**specs, **taken},
                                                        {**domains, name: {}})):
            problems.append(why)
            continue
        if current is None and not cap.startswith(name + "/"):
            problems.append(f"{cap} isn't named {name}/<capability>")
            continue
        if missing := [k for k in ("ref", "anchors", "anchorsFiles") if not rec.get(k)]:
            problems.append(f"{cap} has no {', '.join(missing)} yet")
            continue
        if "syncedCommit" not in rec:
            problems.append(f"{cap} isn't stamped: run `backfill.py stamp {cap}`")
            continue
        if not (drift.ROOT / ".blueprint" / "baseline" / f"{cap}.md").is_file():
            problems.append(f"{cap} has no baseline at .blueprint/baseline/{cap}.md")
            continue
        entries[cap] = {k: rec[k] for k in SPEC_KEYS if k in rec}
    return problems, entries


def cmd_fold(args):
    progress, state = load_progress(), drift.load()
    named = [a for a in args if not a.startswith("--")]
    for name in named:
        known_domain(progress, name)
    candidates = named or list(progress["domains"])
    folded, refused, taken = [], {}, {}
    for name in candidates:
        dom = load_domain(name)
        if not named and (dom["folded"] or dom["passes"]["3"] != "done"):
            continue  # not finished: fold all takes only what's ready
        problems, entries = fold_problems(name, dom, state, taken)
        if problems:
            refused[name] = problems
            continue
        taken.update(entries)
        folded.append((name, dom, entries))
    for name, dom, entries in folded:
        domains = state.setdefault("domains", {})
        if name not in domains:
            domains[name] = {"ref": dom["ref"],
                             "purpose": progress["domains"][name].get("purpose", "")}
        specs = state.setdefault("specs", {})
        for cap, entry in entries.items():
            specs[cap] = {**specs.get(cap, {}), **entry}
    if folded:
        drift.save(state)
        for name, dom, entries in folded:
            dom["folded"] = True
            write_json(domain_path(name), dom)
            print(f"folded {name}: {len(entries)} capabilities"
                  + (f" ({', '.join(entries)})" if entries else ""))
        write_readme(progress)
    elif not refused:
        print("nothing to fold: no domain has finished scenario review since the last fold")
    for name, problems in refused.items():
        print(f"can't fold {name}:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
    return 1 if refused else 0


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    handlers = {"init": cmd_init, "status": cmd_status, "uncovered": cmd_uncovered,
                "stamp": cmd_stamp, "pass": cmd_pass, "fold": cmd_fold}
    cmd = sys.argv[1]
    if cmd not in handlers:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 2
    try:
        return handlers[cmd](sys.argv[2:])
    except Problem as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
