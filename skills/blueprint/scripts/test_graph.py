#!/usr/bin/env python3
"""Tests for graph.py: each runs the script in a throwaway git repo.

    python3 skills/blueprint/scripts/test_graph.py
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GRAPH = Path(__file__).resolve().parent / "graph.py"
# Ignore the developer's git config (signing, hooks, templates) in the throwaway repos.
ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")


class Repo:
    def __init__(self, files, state):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.git("init", "-q")
        for path, text in files.items():
            self.write(path, text)
        self.write(".blueprint/blueprint.json", json.dumps(state, indent=2) + "\n")
        self.git("add", "-A")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")

    def write(self, path, text):
        (self.root / path).parent.mkdir(parents=True, exist_ok=True)
        (self.root / path).write_text(text)

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True,
                       env=ENV)

    def scored(self, rows, *args):
        """graph.py with drift.assess answering `rows` ({capability: row}) for the named capabilities,
        so statuses no fixture produces yet (deps-moved, possibly-affected) can be drawn."""
        script = (f"import sys, json; sys.path.insert(0, {str(GRAPH.parent)!r}); sys.argv[1:] = {list(args)!r}\n"
                  "import drift, graph\n"
                  f"rows = json.loads({json.dumps(rows)!r}); real = drift.assess\n"
                  "def fake(spec, paths, settings, hashes=drift.file_hashes, imports=None):\n"
                  "    name = next(n for n, s in drift.load()['specs'].items() if s.get('anchors') == spec.get('anchors'))\n"
                  "    return rows[name] if name in rows else real(spec, paths, settings, hashes, imports)\n"
                  "drift.assess = fake\n"
                  "sys.exit(graph.main(sys.argv[1:]))\n")
        return subprocess.run([sys.executable, "-c", script], cwd=self.root, capture_output=True,
                              text=True, env=ENV)

    def graph(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(GRAPH), *args], cwd=cwd or self.root,
                              capture_output=True, text=True, env=ENV)

    def data(self):
        out = self.graph("--json")
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout)

    def close(self):
        self._tmp.cleanup()


def spec(*anchors):
    return {"ref": None, "anchors": list(anchors)}


def stamped(files, *anchors):
    """A synced spec whose stamps match `files` (path → text) as they are now."""
    hashes = {p: hashlib.sha256(t.encode()).hexdigest()[:12] for p, t in files.items()}
    return {"ref": "page", "anchors": list(anchors), "anchorsFiles": hashes, "syncedCommit": "abc"}


SYNC_MD = """## Purpose

Finds capabilities whose code moved.

## Requirements

### Requirement: Code drift detection

`drift.py check` SHALL report each capability.

- **Scenario: Anchored file edited**
  - **WHEN** one of its anchored files changes
  - **THEN** check lists it

### Requirement: Stamping

`drift.py stamp` SHALL record a hash per file.
"""


class GraphTest(unittest.TestCase):
    def repo(self, files, state):
        r = Repo(files, state)
        self.addCleanup(r.close)
        return r


class Extract(GraphTest):
    FILES = {
        "shared/a.ts": "a", "shared/b.ts": "b", "shared/c.ts": "c",
        "worker/index.ts": "w", "docs/readme.md": "r",
    }
    STATE = {
        "domains": {"core": {"ref": "x", "purpose": "The core of it."}},
        "specs": {
            "core/jams": spec("shared/**", "worker/index.ts"),
            "core/agent": spec("shared/**"),
            "room": spec("worker/index.ts", "shared/a.ts"),
            "docs": spec("docs/**"),
        },
    }

    # @scenario blueprint/map: Domain
    def test_nodes_and_domains(self):
        d = self.repo(self.FILES, self.STATE).data()
        by = {n["id"]: n for n in d["nodes"]}
        self.assertEqual(set(by), {"core/jams", "core/agent", "room", "docs"})
        self.assertEqual(by["core/jams"]["domain"], "core")
        self.assertIsNone(by["room"]["domain"])
        self.assertEqual(d["domains"], [{"id": "core", "purpose": "The core of it."}])
        self.assertEqual(by["core/jams"]["files"],
                         ["shared/a.ts", "shared/b.ts", "shared/c.ts", "worker/index.ts"])

    # @scenario blueprint/map: Shared files
    def test_links_weighted_by_shared_files(self):
        d = self.repo(self.FILES, self.STATE).data()
        links = {(e["source"], e["target"]): e for e in d["edges"]}
        self.assertEqual(set(links), {("core/agent", "core/jams"), ("core/jams", "room"),
                                      ("core/agent", "room")})
        self.assertEqual(links[("core/agent", "core/jams")]["count"], 3)
        self.assertEqual(links[("core/jams", "room")]["files"], ["shared/a.ts", "worker/index.ts"])
        self.assertEqual(links[("core/agent", "room")]["count"], 1)
        self.assertFalse(d["filesDefault"])

    def test_domain_needs_a_slash(self):
        state = {"domains": {"core": {}}, "specs": {"core": spec("docs/**")}}
        d = self.repo(self.FILES, state).data()
        self.assertIsNone(d["nodes"][0]["domain"])

    # @scenario blueprint/sync: Excluded tests
    def test_excluded_and_blueprint_files_not_matched(self):
        files = {"src/x.ts": "", "src/x.test.ts": ""}
        state = {"specs": {"a": spec("src/**", "!**/*.test.ts"), "b": spec("**")}}
        d = self.repo(files, state).data()
        by = {n["id"]: n for n in d["nodes"]}
        self.assertEqual(by["a"]["files"], ["src/x.ts"])
        self.assertNotIn(".blueprint/blueprint.json", by["b"]["files"])


class FilesDefault(GraphTest):
    # @scenario blueprint/map: No shared files
    def test_on_when_nothing_is_shared(self):
        files = {"a/x.ts": "", "b/y.ts": ""}
        state = {"specs": {"a": spec("a/**"), "b": spec("b/**")}}
        d = self.repo(files, state).data()
        self.assertEqual(d["edges"], [])
        self.assertTrue(d["filesDefault"])


class Baseline(GraphTest):
    def test_purpose_and_requirements(self):
        files = {".blueprint/baseline/blueprint/sync.md": SYNC_MD, "drift.py": ""}
        state = {"domains": {"blueprint": {}}, "specs": {"blueprint/sync": spec("drift.py")}}
        n = self.repo(files, state).data()["nodes"][0]
        self.assertTrue(n["hasBaseline"])
        self.assertEqual(n["purpose"], "Finds capabilities whose code moved.")
        self.assertEqual([r["title"] for r in n["requirements"]], ["Code drift detection", "Stamping"])
        self.assertIn("Scenario: Anchored file edited", n["requirements"][0]["body"])
        self.assertNotIn("Stamping", n["requirements"][0]["body"])

    def test_missing_baseline(self):
        n = self.repo({"x.py": ""}, {"specs": {"x": spec("x.py")}}).data()["nodes"][0]
        self.assertFalse(n["hasBaseline"])
        self.assertEqual((n["purpose"], n["requirements"]), ("", []))


class Drift(GraphTest):
    FILES = {"sync/a.py": "one", "sync/b.py": "two"}

    # @scenario blueprint/map: Code moved
    def test_in_sync_then_code_moved(self):
        r = self.repo(self.FILES, {"specs": {"sync": stamped(self.FILES, "sync/**")}})
        n = r.data()["nodes"][0]
        self.assertEqual((n["status"], n["changed"]), ("in-sync", []))
        r.write("sync/b.py", "edited")
        r.write("sync/c.py", "new")
        n = r.data()["nodes"][0]
        self.assertEqual((n["status"], n["changed"]), ("code-moved", ["sync/b.py", "sync/c.py"]))

    def test_unwritten_and_unanchored(self):
        state = {"specs": {"lazy": spec("sync/**"), "bare": {"ref": "p", "anchors": []}}}
        by = {n["id"]: n["status"] for n in self.repo(self.FILES, state).data()["nodes"]}
        self.assertEqual(by, {"lazy": "no-spec", "bare": "no-anchors"})


class Scoring(GraphTest):
    """Drift chance, confidence and reasons on the map, as `drift.py check` reports them."""
    FILES = {"sync/a.py": "one", "ui/b.ts": "two", "map/c.ts": "three"}
    STATE = {"specs": {"sync": stamped({"sync/a.py": "one"}, "sync/**"),
                       "ui": stamped({"ui/b.ts": "two"}, "ui/**"),
                       "map": stamped({"map/c.ts": "three"}, "map/**")}}
    DEPS = {"status": "deps-moved", "changed": [], "chance": 0.5, "confidence": "medium",
            "reasons": ["packages/core/src/token.ts signToken changed, 1 import away, "
                        "via @company/core (weight 1) → 0.5", "confidence medium: no test results given"]}
    MAYBE = {"status": "possibly-affected", "changed": [], "chance": 0.13, "confidence": "medium",
             "reasons": ["packages/core/src/token.ts signToken changed, 2 imports away, "
                         "via @company/core (weight 0.5) → 0.13", "confidence medium: no test results given"]}

    def test_agrees_with_check(self):
        """Each node carries the status, chance, confidence and reasons `drift.py check --json` gives."""
        r = self.repo(self.FILES, self.STATE)
        r.write("sync/a.py", "edited")
        r.write("ui/b.ts", "edited")
        check = subprocess.run([sys.executable, str(GRAPH.parent / "drift.py"), "check", "--json"],
                               cwd=r.root, capture_output=True, text=True, env=ENV)
        want = {x["capability"]: (x["status"], x["chance"], x["confidence"], x["reasons"])
                for x in json.loads(check.stdout)}
        got = {n["id"]: (n["status"], n["chance"], n["confidence"], n["reasons"]) for n in r.data()["nodes"]}
        self.assertEqual(got, want)
        self.assertEqual(got["sync"][:3], ("code-moved", 1.0, "high"))
        self.assertEqual(got["ui"][:3], ("code-moved", 1.0, "low"))
        self.assertEqual(got["map"][:2], ("in-sync", 0.0))

    def test_deps_moved_and_possibly_affected(self):
        r = self.repo(self.FILES, self.STATE)
        out = r.scored({"ui": self.DEPS, "map": self.MAYBE}, "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        by = {n["id"]: n for n in json.loads(out.stdout)["nodes"]}
        self.assertEqual((by["ui"]["status"], by["ui"]["chance"], by["ui"]["confidence"]),
                         ("deps-moved", 0.5, "medium"))
        self.assertEqual(by["map"]["reasons"], self.MAYBE["reasons"])
        self.assertEqual(by["sync"]["status"], "in-sync")

    def test_summary_counts_imports_moved_as_drift(self):
        r = self.repo(self.FILES, self.STATE)
        out = r.scored({"ui": self.DEPS, "map": self.MAYBE}, "--out", "m.html")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.splitlines()[1],
                         "3 capabilities, 0 domains; code-drifted: ui; 1 possibly affected; "
                         "no shared files, so files start as nodes")

    def test_bad_setting_draws_at_the_defaults(self):
        state = dict(self.STATE, drift={"scoring": {"decay": 2}})
        r = self.repo(self.FILES, state)
        r.write("sync/a.py", "edited")
        d = r.data()
        self.assertIn("drift.scoring.decay", d["scoringError"])
        self.assertEqual({n["id"]: n["status"] for n in d["nodes"]},
                         {"sync": "code-moved", "ui": "in-sync", "map": "in-sync"})
        out = r.graph()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("scored at the defaults: drift.scoring.decay", out.stdout)

    def test_page_draws_the_lighter_tint_and_the_panel(self):
        """The page's own rules for the new statuses: a lighter tint, its legend row, the panel parts."""
        template = (GRAPH.parent / "map_template.html").read_text()
        self.assertIn("--maybe:", template)
        self.assertRegex(template, r"\.cap\.maybe rect \{[^}]*var\(--maybe-bg\)")
        self.assertIn('"possibly-affected": ["possibly affected", "maybe"]', template)
        self.assertIn('"deps-moved": ["imports moved", "drift"]', template)
        legend = re.search(r'<details class="legend".*?</details>', template, re.S).group(0)
        self.assertIn('class="sw maybe"', legend)
        self.assertIn("<h3>Drift chance</h3>", template)


class Artifacts(GraphTest):
    FILES = {"billing/invoices.py": "one", "billing/refunds.py": "two", "room.py": "r"}

    def state(self, arts):
        return {"domains": {"billing": {}},
                "specs": {"billing/invoices": spec("billing/invoices.py"),
                          "billing/refunds": spec("billing/refunds.py"), "room": spec("room.py")},
                "artifacts": arts}

    def art(self, kind, value, caps, checked):
        hashes = {p: hashlib.sha256(self.FILES[p].encode()).hexdigest()[:12] for p in checked}
        return {"type": kind, "value": value, "description": "Help article", "capabilities": caps,
                "checkedFiles": hashes}

    # @scenario blueprint/map: Artifacts as nodes
    def test_direct_and_through_domain(self):
        arts = {"help": self.art("webpage", "https://help.example.com/x", ["billing/invoices"],
                                 ["billing/invoices.py"]),
                "guide": self.art("notion", "https://notion.so/p", ["billing"],
                                  ["billing/invoices.py", "billing/refunds.py"])}
        d = self.repo(self.FILES, self.state(arts)).data()
        by = {n["id"]: n["artifacts"] for n in d["nodes"]}
        self.assertEqual(by, {"billing/invoices": ["help", "guide"], "billing/refunds": ["guide"],
                              "room": []})
        a = {x["id"]: x for x in d["artifacts"]}
        self.assertEqual(a["guide"]["covers"], ["billing/invoices", "billing/refunds"])
        self.assertEqual(a["help"]["link"], "https://help.example.com/x")
        self.assertEqual((a["help"]["stale"], a["guide"]["stale"]), (False, False))
        self.assertEqual(a["help"]["description"], "Help article")

    # @scenario blueprint/map: Stale article
    def test_stale_after_code_changes(self):
        arts = {"help": self.art("webpage", "https://help.example.com/x", ["billing/invoices"],
                                 ["billing/invoices.py"])}
        r = self.repo(self.FILES, self.state(arts))
        r.write("billing/invoices.py", "edited")
        a = r.data()["artifacts"][0]
        self.assertEqual((a["stale"], a["changed"]), (True, ["billing/invoices.py"]))
        out = r.graph("--out", "m.html")
        self.assertIn("1 stale artifact", out.stdout)

    def test_links_and_unknown_names(self):
        arts = {"readme": self.art("file", "acme/docs:billing/README.md", ["room"], ["room.py"]),
                "note": self.art("markdown", "notes/billing.md", ["room"], ["room.py"]),
                "vault": self.art("obsidian", "obsidian://open?vault=v&file=b", ["room"], ["room.py"]),
                "gone": self.art("webpage", "https://x.example.com", ["room", "old/cap"], ["room.py"])}
        a = {x["id"]: x for x in self.repo(self.FILES, self.state(arts)).data()["artifacts"]}
        self.assertEqual(a["readme"]["link"], "https://github.com/acme/docs/blob/HEAD/billing/README.md")
        self.assertIsNone(a["note"]["link"])
        self.assertEqual(a["vault"]["link"], "obsidian://open?vault=v&file=b")
        # A name that is no longer a capability or domain keeps the artifact flagged, as in drift.py.
        self.assertEqual((a["gone"]["stale"], a["gone"]["changed"], a["gone"]["unknown"]),
                         (True, [], ["old/cap"]))
        self.assertFalse(a["readme"]["stale"])

    def test_agrees_with_drift(self):
        """The map flags exactly what `drift.py artifacts` lists, with the same files."""
        arts = {"help": self.art("webpage", "https://h.example.com", ["billing/invoices"],
                                 ["billing/invoices.py"]),
                "guide": self.art("notion", "https://notion.so/p", ["billing"], ["billing/refunds.py"]),
                "room": self.art("webpage", "https://r.example.com", ["room"], ["room.py"]),
                "gone": self.art("webpage", "https://g.example.com", ["old/cap"], [])}
        r = self.repo(self.FILES, self.state(arts))
        r.write("billing/invoices.py", "edited")
        listed = subprocess.run([sys.executable, str(GRAPH.parent / "drift.py"), "artifacts", "--json"],
                                cwd=r.root, capture_output=True, text=True, env=ENV)
        want = {x["id"]: x["changed"] for x in json.loads(listed.stdout)}
        got = {x["id"]: x["changed"] for x in r.data()["artifacts"] if x["stale"]}
        self.assertEqual(got, want)
        self.assertEqual(set(want), {"help", "guide", "gone"})

    def test_none(self):
        d = self.repo(self.FILES, {"specs": {"room": spec("room.py")}}).data()
        self.assertEqual((d["artifacts"], d["nodes"][0]["artifacts"]), ([], []))


class Coverage(GraphTest):
    KINDS = {"kinds": {"e2e": ["e2e/**"], "unit": ["**/test_*.py"]}}
    FILES = {
        ".blueprint/baseline/blueprint/sync.md": SYNC_MD, "drift.py": "", "graph.py": "",
        "tests/test_sync.py": "# @scenario blueprint/sync: anchored FILE   edited\ndef test_a(): pass\n",
        "e2e/sync.spec.ts": "x\n// @scenario blueprint/sync: Anchored file edited\n"
                            "// @scenario blueprint/sync: Anchored file gone\n"
                            "// @scenario nope/cap: Whatever\n",
    }

    def state(self, tests=KINDS):
        s = {"domains": {"blueprint": {}},
             "specs": {"blueprint/sync": spec("drift.py"), "blueprint/map": spec("graph.py")}}
        if tests is not None:
            s["tests"] = tests
        return s

    # @scenario blueprint/map: Uncovered scenarios in the panel
    def test_claims_per_scenario(self):
        d = self.repo(self.FILES, self.state()).data()
        by = {n["id"]: n for n in d["nodes"]}
        sync = by["blueprint/sync"]
        self.assertEqual(sync["coverage"], {"claimed": 1, "total": 1})
        [scen] = sync["requirements"][0]["scenarios"]
        self.assertEqual(scen["name"], "Anchored file edited")
        self.assertEqual([(c["file"], c["line"], c["kind"]) for c in scen["claims"]],
                         [("e2e/sync.spec.ts", 2, "e2e"), ("tests/test_sync.py", 1, "unit")])
        self.assertEqual(sync["requirements"][1]["scenarios"], [])  # Stamping has none
        # Requirements keep their title and body beside the scenarios.
        self.assertEqual(sync["requirements"][0]["title"], "Code drift detection")
        # No baseline: nothing to count.
        self.assertIsNone(by["blueprint/map"]["coverage"])
        self.assertEqual(d["coverage"]["summary"], {"claimed": 1, "total": 1, "byKind": {"e2e": 1, "unit": 1}})
        self.assertNotIn("capabilities", d["coverage"])

    # @scenario blueprint/map: Tests as nodes
    def test_claiming_test_files(self):
        d = self.repo(self.FILES, self.state()).data()
        self.assertEqual([t["file"] for t in d["tests"]], ["e2e/sync.spec.ts", "tests/test_sync.py"])
        e2e = d["tests"][0]
        self.assertEqual((e2e["kind"], e2e["covers"]), ("e2e", ["blueprint/sync"]))
        self.assertEqual(e2e["claims"], [{"capability": "blueprint/sync", "scenario": "Anchored file edited", "line": 2}])
        by = {n["id"]: n["tests"] for n in d["nodes"]}
        self.assertEqual(by, {"blueprint/sync": ["e2e/sync.spec.ts", "tests/test_sync.py"], "blueprint/map": []})

    def test_orphans_and_summary_line(self):
        r = self.repo(self.FILES, self.state())
        orphans = {(o["capability"], o["reason"], o["suggestion"]) for o in r.data()["coverage"]["orphans"]}
        self.assertEqual(orphans, {("blueprint/sync", "unknown scenario", "Anchored file edited"),
                                   ("nope/cap", "unknown capability", None)})
        out = r.graph("--out", "m.html")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("code-drifted: none; 1 of 1 scenario claimed, 2 orphan tags", out.stdout)

    # @scenario blueprint/map: Map without kinds
    def test_without_kinds(self):
        r = self.repo(self.FILES, self.state(tests=None))
        d = r.data()
        self.assertEqual((d["coverage"], d["coverageError"], d["tests"]), (None, None, []))
        self.assertTrue(all(n["coverage"] is None and n["tests"] == [] for n in d["nodes"]))
        self.assertNotIn("scenarios", d["nodes"][0]["requirements"][0])
        out = r.graph()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("scenario", out.stdout)
        html = (r.root / ".blueprint/map.html").read_text()
        legend = re.search(r'<details class="legend".*?</details>', html, re.S).group(0)
        self.assertIn("<code>tests.kinds</code>", legend)
        self.assertIn("/blueprint coverage", legend)

    def test_coverage_problem_does_not_stop_the_map(self):
        """What makes coverage.py exit 2 (here a synced spec with no baseline) leaves the map drawn."""
        state = self.state()
        state["specs"]["blueprint/map"]["ref"] = "page"
        r = self.repo(self.FILES, state)
        d = r.data()
        self.assertIsNone(d["coverage"])
        self.assertIn("no .blueprint/baseline/blueprint/map.md", d["coverageError"])
        out = r.graph()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("coverage not shown: blueprint/map has a spec but no", out.stdout)


class Page(GraphTest):
    STATE = {"domains": {"core": {"purpose": "</script><b>x</b>"}},
             "specs": {"core/a": spec("a.ts"), "core/b": spec("a.ts")}}

    # @scenario blueprint/map: First run
    def test_writes_self_contained_page(self):
        r = self.repo({"a.ts": ""}, self.STATE)
        out = r.graph()
        self.assertEqual(out.returncode, 0, out.stderr)
        page = r.root / ".blueprint/map.html"
        path, summary, told = out.stdout.strip().splitlines()
        self.assertEqual(path, str(page))
        self.assertEqual(summary, "2 capabilities, 1 domain; code-drifted: none")
        # The page keeps itself out of git, once, without touching the root .gitignore,
        # and says so the time it adds the line.
        self.assertIn(".blueprint/.gitignore", told)
        self.assertEqual((r.root / ".blueprint/.gitignore").read_text(), "map.html\n")
        again = r.graph()
        self.assertEqual(len(again.stdout.strip().splitlines()), 2)
        self.assertEqual((r.root / ".blueprint/.gitignore").read_text(), "map.html\n")
        html = page.read_text()
        self.assertIn("https://d3js.org v7.9.0", html)
        self.assertNotIn("/*D3*/", html)
        self.assertNotIn("/*DATA*/", html)
        # Nothing loaded from the network: every script is inline.
        self.assertNotRegex(html, r"<script[^>]*\bsrc=")
        self.assertNotRegex(html, r"<link[^>]*\bhref=")

    def test_controls_and_legend(self):
        r = self.repo({"a.ts": ""}, self.STATE)
        r.graph()
        html = (r.root / ".blueprint/map.html").read_text()
        self.assertIn('id="q"', html)  # search box
        # One "Show as nodes" menu holds the files, artifacts and tests switches.
        menu = re.search(r'<details class="nodes".*?</details>', html, re.S).group(0)
        self.assertIn('id="files"', menu)
        self.assertIn('id="artifacts"', menu)
        self.assertIn('id="tests"', menu)
        # The map says "claimed", never that a test passed or verified anything.
        template = (GRAPH.parent / "map_template.html").read_text()
        self.assertNotRegex(template, r"(?i)\b(passing|passes|verified)\b")
        self.assertIn('id="panel"', html)  # details panel
        # The legend says spec-side drift is not drawn and where it is reported.
        legend = re.search(r'<details class="legend".*?</details>', html, re.S).group(0)
        self.assertIn("Only code-side drift is shown", legend)
        self.assertIn("/blueprint-sync", legend)

    def test_data_cannot_close_the_script(self):
        r = self.repo({"a.ts": ""}, self.STATE)
        r.graph()
        html = (r.root / ".blueprint/map.html").read_text()
        self.assertEqual(html.lower().count("</script"), html.lower().count("<script"))
        data = re.search(r"const DATA = (.*?);\n", html).group(1)
        self.assertEqual(json.loads(data)["domains"][0]["purpose"], "</script><b>x</b>")

    def test_out_and_from_a_subfolder(self):
        r = self.repo({"a.ts": "", "sub/dir/x.txt": ""}, self.STATE)
        out = r.graph("--out", "map.html", cwd=r.root / "sub/dir")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue((r.root / "sub/dir/map.html").is_file())
        self.assertIn('"core/a"', (r.root / "sub/dir/map.html").read_text())


if __name__ == "__main__":
    unittest.main()
