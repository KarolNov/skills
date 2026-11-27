#!/usr/bin/env python3
"""The docs site builds from a shallow clone of the repo, with this commit's own map.

    npm ci && python3 tests/test_docs.py

Clones the committed HEAD with --depth 1 into a temporary folder, borrows the repo's
node_modules, then runs `npm run docs:build` there with no credentials in the environment, the
way Cloudflare Workers Builds does. Skips when node_modules has no vitepress (run `npm ci`).
Publishing and previews happen on Cloudflare and aren't checked here.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODES = ["setup", "propose", "apply", "ask", "map", "coverage", "drift", "sync", "tidy", "backfill"]


def map_data(html):
    """The data graph.py inlined in map.html."""
    m = re.search(r"^const DATA = (.*);$", html, re.M)
    assert m, "no DATA in map.html"
    return json.loads(m.group(1))


@unittest.skipUnless((ROOT / "node_modules/.bin/vitepress").exists(), "needs npm ci")
class ShallowBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        clone = cls.clone = Path(cls._tmp.name) / "skills"
        subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{ROOT}", str(clone)],
                       check=True, capture_output=True)
        os.symlink(ROOT / "node_modules", clone / "node_modules")
        # A capability added in this commit, and blueprint/sync's code moved since its stamp.
        state_path = clone / ".blueprint/blueprint.json"
        state = json.loads(state_path.read_text())
        state["specs"]["docs-probe"] = {"ref": None, "anchors": ["docs/index.md"]}
        state_path.write_text(json.dumps(state, indent=2) + "\n")
        cls.moved = sorted(state["specs"]["blueprint/sync"]["anchorsFiles"])[0]
        with open(clone / cls.moved, "a") as f:
            f.write("\n")
        # Nothing but a toolchain: no tokens, no backend connection.
        env = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR", "LANG") if k in os.environ}
        cls.build = subprocess.run(["npm", "run", "docs:build"], cwd=clone, capture_output=True,
                                   text=True, env=env)
        cls.dist = clone / "docs/.vitepress/dist"

    def page(self, path):
        return (self.dist / path).read_text(encoding="utf-8")

    # @scenario docs: Shallow clone builds
    def test_a_depth_1_clone_builds_with_the_map(self):
        self.assertEqual(self.build.returncode, 0, self.build.stdout + self.build.stderr)
        commits = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=self.clone,
                                 capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(commits, "1")
        self.assertTrue((self.dist / "map.html").is_file())
        self.assertIn('src="/map.html"', self.page("capability-map.html"))

    # @scenario docs: Map matches the commit
    def test_map_shows_a_capability_added_in_the_commit(self):
        ids = {n["id"] for n in map_data(self.page("map.html"))["nodes"]}
        self.assertIn("docs-probe", ids)
        self.assertIn("blueprint/sync", ids)

    # @scenario docs: No drift on the public map
    def test_moved_capability_is_drawn_like_any_other(self):
        data = map_data(self.page("map.html"))
        self.assertFalse(data["drift"])
        sync = next(n for n in data["nodes"] if n["id"] == "blueprint/sync")
        self.assertIn(self.moved, sync["files"])
        self.assertEqual((sync["status"], sync["changed"], sync["reasons"]), (None, [], []))
        self.assertFalse(any(a["stale"] for a in data["artifacts"]))
        page = self.page("capability-map.html")
        self.assertIn("Drift is not shown on this map", page)
        self.assertIn('href="https://karolnov.dev/projects/blueprint"', page)

    # @scenario docs: Find a mode
    def test_every_mode_has_a_page_in_the_sidebar_and_the_search_index(self):
        config = (self.clone / "docs/.vitepress/config.mts").read_text()
        self.assertIn('search: { provider: "local" }', config)
        index = "".join(p.read_text() for p in (self.dist / "assets/chunks").glob("@localSearchIndex*.js"))
        for page in [f"modes/{m}" for m in MODES] + ["getting-started", "review-pane", "backends", "upgrading"]:
            self.assertTrue((self.dist / f"{page}.html").is_file(), page)
            self.assertIn(f'link: "/{page}"', config, page)
            self.assertIn(f'"/{page}', index, page)
        self.assertRegex(index, r'"/modes/coverage#coverage"')


class Wrangler(unittest.TestCase):
    def test_assets_only_worker_on_the_custom_domain(self):
        text = (ROOT / "wrangler.jsonc").read_text()
        conf = json.loads(re.sub(r"^\s*//.*$", "", text, flags=re.M))
        self.assertNotIn("main", conf)
        self.assertEqual(conf["assets"]["directory"], "docs/.vitepress/dist")
        self.assertEqual(conf["routes"], [{"pattern": "blueprint.karolnov.dev", "custom_domain": True}])
        # Workers Builds runs `wrangler preview` on pull requests, and it needs a previews block.
        self.assertIn("previews", conf)


if __name__ == "__main__":
    unittest.main()
