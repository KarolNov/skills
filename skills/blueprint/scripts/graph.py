#!/usr/bin/env python3
"""Write the capability map: one self-contained HTML page drawn from .blueprint/.

    python3 graph.py [--out PATH] [--json]

Reads blueprint.json, baseline/ and the repo's files; writes .blueprint/map.html (git-ignored)
(or PATH) with d3, the page script and the data inlined, so it opens offline.
--json prints the extracted data instead of writing the page.

Run from anywhere inside the repository. Anchor matching comes from the drift.py
next to this script (the skill's copy), not the repo's .blueprint/drift.py.
Standard library only.
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import drift  # noqa: E402  (sits next to this script; finds the repo root on import)

TEMPLATE = HERE / "map_template.html"
D3 = HERE / "vendor" / "d3.v7.9.0.min.js"

_PURPOSE = re.compile(r"^## Purpose[ \t]*\n(.*?)(?=^## |\Z)", re.S | re.M)
_REQUIREMENT = re.compile(r"^### Requirement:[ \t]*(.*?)[ \t]*\n(.*?)(?=^### |^## |\Z)", re.S | re.M)


def parse_baseline(text):
    """A baseline's Purpose and its requirements as [{title, body}], body holding the scenarios."""
    m = _PURPOSE.search(text)
    purpose = m.group(1).strip() if m else ""
    reqs = [{"title": t.strip(), "body": b.strip()} for t, b in _REQUIREMENT.findall(text)]
    return purpose, reqs


def domain_of(name, domains):
    """The domain a capability sits in: its name's first part, when that part is a domain."""
    head = name.split("/")[0]
    return head if "/" in name and head in domains else None


def cached_hashes():
    """drift.file_hashes with a cache, so a file several capabilities match is read once."""
    cache = {}

    def hashes(paths):
        cache.update(drift.file_hashes([p for p in paths if p not in cache]))
        return {p: cache[p] for p in paths}
    return hashes


def repo_name(root):
    """The repository's folder name, the main checkout's when run inside a linked worktree."""
    common = drift.git("rev-parse", "--path-format=absolute", "--git-common-dir", check=False).strip()
    if common.endswith("/.git"):
        return Path(common).parent.name
    return root.name


def build(state=None, files=None):
    """The map's data: domains, capability nodes, and links between capabilities sharing files."""
    state = drift.load() if state is None else state
    files = drift.repo_files() if files is None else files
    specs, domains = state.get("specs", {}), state.get("domains", {})

    nodes, owners, hashes = [], {}, cached_hashes()
    for name, spec in specs.items():
        compiled = drift.compile_anchors(spec)
        mine = [f for f in files if drift.matching_anchors(compiled, f)]
        for f in mine:
            owners.setdefault(f, []).append(name)
        status, changed = drift.code_status(spec, mine, hashes)
        baseline = drift.ROOT / ".blueprint" / "baseline" / f"{name}.md"
        has_baseline = baseline.is_file()
        purpose, reqs = parse_baseline(baseline.read_text(encoding="utf-8")) if has_baseline else ("", [])
        nodes.append({
            "id": name,
            "domain": domain_of(name, domains),
            "status": status,
            "ref": spec.get("ref"),
            "hasBaseline": has_baseline,
            "purpose": purpose,
            "requirements": reqs,
            "files": mine,
            "changed": changed,
        })

    shared = {}
    for f, caps in owners.items():
        for i, a in enumerate(caps):
            for b in caps[i + 1:]:
                shared.setdefault(tuple(sorted((a, b))), []).append(f)
    edges = [{"source": a, "target": b, "count": len(fs), "files": sorted(fs)}
             for (a, b), fs in sorted(shared.items())]

    return {
        "repo": repo_name(drift.ROOT),
        "domains": [{"id": d, "purpose": (v or {}).get("purpose", "")} for d, v in domains.items()],
        "nodes": nodes,
        "edges": edges,
        # With no shared files there are no lines, so the page starts with files drawn as nodes.
        "filesDefault": not edges,
    }


def script_json(data):
    """JSON safe to inline in a <script>: no `</` can close the tag, no `<!--` can open a comment."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return (text.replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def render(data, template=None, d3=None):
    """The page: the template with d3 and the data dropped in at their markers."""
    template = TEMPLATE.read_text(encoding="utf-8") if template is None else template
    d3 = D3.read_text(encoding="utf-8") if d3 is None else d3
    for marker in ("/*D3*/", "/*DATA*/"):
        if template.count(marker) != 1:
            sys.exit(f"map template: expected one {marker} marker")
    # Split rather than str.replace, so nothing inside d3 or the data is read as a marker.
    head, rest = template.split("/*D3*/")
    mid, tail = rest.split("/*DATA*/")
    return head + d3 + mid + script_json(data) + tail


def main(argv):
    out = drift.ROOT / ".blueprint" / "map.html"
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 >= len(argv):
            sys.exit("--out needs a path")
        out = Path(argv[i + 1]).resolve()
    data = build()
    if "--json" in argv:
        print(json.dumps(data, indent=1, ensure_ascii=False))
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
