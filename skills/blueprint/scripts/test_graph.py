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

    def test_nodes_and_domains(self):
        d = self.repo(self.FILES, self.STATE).data()
        by = {n["id"]: n for n in d["nodes"]}
        self.assertEqual(set(by), {"core/jams", "core/agent", "room", "docs"})
        self.assertEqual(by["core/jams"]["domain"], "core")
        self.assertIsNone(by["room"]["domain"])
        self.assertEqual(d["domains"], [{"id": "core", "purpose": "The core of it."}])
        self.assertEqual(by["core/jams"]["files"],
                         ["shared/a.ts", "shared/b.ts", "shared/c.ts", "worker/index.ts"])

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

    def test_excluded_and_blueprint_files_not_matched(self):
        files = {"src/x.ts": "", "src/x.test.ts": ""}
        state = {"specs": {"a": spec("src/**", "!**/*.test.ts"), "b": spec("**")}}
        d = self.repo(files, state).data()
        by = {n["id"]: n for n in d["nodes"]}
        self.assertEqual(by["a"]["files"], ["src/x.ts"])
        self.assertNotIn(".blueprint/blueprint.json", by["b"]["files"])


class FilesDefault(GraphTest):
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


class Page(GraphTest):
    STATE = {"domains": {"core": {"purpose": "</script><b>x</b>"}},
             "specs": {"core/a": spec("a.ts"), "core/b": spec("a.ts")}}

    def test_writes_self_contained_page(self):
        r = self.repo({"a.ts": ""}, self.STATE)
        out = r.graph()
        self.assertEqual(out.returncode, 0, out.stderr)
        page = r.root / ".blueprint/map.html"
        self.assertEqual(out.stdout.strip(), str(page))
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
        self.assertIn('id="files"', html)  # files-as-nodes switch
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
