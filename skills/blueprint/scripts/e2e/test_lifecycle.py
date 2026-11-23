#!/usr/bin/env python3
"""End-to-end tests on the demo shop: drift.py, coverage.py and graph.py run on the same repo
as it is synced, drifts, is renamed and re-synced, and must agree at every step.

    python3 skills/blueprint/scripts/e2e/test_lifecycle.py

The e2e kind in this repo's tests.kinds; the per-script edge cases live in ../test_drift.py,
../test_coverage.py and ../test_graph.py. Tags are built so coverage reads them: each sits on
its own line above the test, and claims a scenario only where the test checks its WHEN and THEN.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fakerepo import DRIFTED, ENV, SHARED, STALE, UNTESTED, FakeRepo, shop, tag

FAKEREPO = Path(__file__).resolve().parent / "fakerepo.py"


def agree(test, r):
    """drift.py, coverage.py and graph.py tell the same story about the repo as it is now."""
    m, cov = r.map(), r.coverage()
    test.assertEqual(sorted(n["id"] for n in m["nodes"] if n["status"] == "code-moved"), r.moved())
    test.assertEqual(sorted(a["id"] for a in m["artifacts"] if a["stale"]), r.stale())
    test.assertEqual(m["coverage"]["summary"], cov["summary"])
    test.assertEqual(m["coverage"]["orphans"], cov["orphans"])
    by_id = {n["id"]: n for n in m["nodes"]}
    for c in cov["capabilities"]:
        test.assertEqual(by_id[c["name"]]["coverage"], {"claimed": c["claimed"], "total": c["total"]},
                         c["name"])
    return m, cov


def claimed(cov, cap):
    return next(c["claimed"] for c in cov["capabilities"] if c["name"] == cap)


class ShopTest(unittest.TestCase):
    """Builds the shop once; each test gets its own copy to change."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.base, cls.scenarios = shop(Path(cls._tmp.name) / "shop")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def repo(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dst = Path(tmp.name) / "shop"
        shutil.copytree(self.base.root, dst)
        return FakeRepo(dst)


class AsBuilt(ShopTest):
    def test_one_drift_one_stale_artifact(self):
        r = self.repo()
        self.assertEqual(r.moved(), [DRIFTED])
        self.assertEqual(r.stale(), [STALE])
        agree(self, r)

    def test_untested_orphans_and_unclassified(self):
        cov = self.repo().coverage()
        # No unit tests of their own; e2e flows and neighbours may still claim their scenarios.
        for c in cov["capabilities"]:
            if c["name"] in UNTESTED:
                files = {cl["file"] for q in c["requirements"] for sc in q["scenarios"] for cl in sc["claims"]}
                self.assertFalse({f for f in files if f.startswith(f"src/{c['name']}/")}, c["name"])
        self.assertEqual(sorted(o["reason"] for o in cov["orphans"]),
                         ["unknown capability", "unknown scenario"])
        self.assertEqual([u["file"] for u in cov["unclassified"]], ["scripts/smoke.test.ts"])

    def test_seeded(self):
        """Same seed, same repo: the map's data is identical apart from the folder name."""
        with tempfile.TemporaryDirectory() as tmp:
            other, _ = shop(Path(tmp) / "again")
            a, b = self.repo().map(), other.map()
            a.pop("repo"), b.pop("repo")
            self.assertEqual(a, b)


class Drifting(ShopTest):
    # @scenario blueprint/sync: Anchored file edited
    # @scenario blueprint/sync: Code changes after a check
    # @scenario blueprint/map: Code moved
    def test_shared_file_drifts_every_capability_that_anchors_it(self):
        r = self.repo()
        r.edit("src/shared/money.ts")
        check = r.drift("check", "--json")
        self.assertEqual(check.returncode, 1)
        for c in json.loads(check.stdout):
            if c["capability"] in SHARED["src/shared/money.ts"]:
                self.assertIn("src/shared/money.ts", c["changed"], c["capability"])
                self.assertEqual(c["chance"], 1.0, c["capability"])
        self.assertEqual(r.moved(), sorted({DRIFTED, *SHARED["src/shared/money.ts"]}))
        # billing-help covers the billing domain, which anchors money.ts.
        self.assertEqual(r.stale(), sorted(["billing-help", STALE]))
        arts = {a["id"]: a for a in json.loads(r.drift("artifacts", "--json").stdout)}
        self.assertIn("src/shared/money.ts", arts["billing-help"]["changed"])
        m, _ = agree(self, r)
        for n in m["nodes"]:
            if n["id"] in SHARED["src/shared/money.ts"]:
                self.assertIn("src/shared/money.ts", n["changed"], n["id"])

    def test_added_and_removed_files_drift_uncommitted_too(self):
        r = self.repo()
        r.write("src/shipping/rates/zones.ts", "export const z = 1;\n")
        r.remove(next(str(p.relative_to(r.root)) for p in sorted((r.root / "src/audit-log").glob("*.ts"))
                      if not p.name.endswith(".test.ts")))
        self.assertEqual(r.moved(), sorted([DRIFTED, "audit-log", "shipping/rates"]))
        agree(self, r)

    def test_test_files_move_coverage_not_drift(self):
        r = self.repo()
        cap = "auth/mfa"
        before = r.coverage()
        free = next(sc["name"] for c in before["capabilities"] if c["name"] == cap
                    for q in c["requirements"] for sc in q["scenarios"] if not sc["claims"])
        r.write("src/auth/mfa/service.test.ts", tag(cap, free) + "it('x', () => {});\n")
        self.assertEqual(r.moved(), [DRIFTED])
        _, cov = agree(self, r)
        self.assertEqual(claimed(cov, cap), claimed(before, cap) + 1)

    # @scenario blueprint/sync: Spec synced, artifact not checked
    def test_resync_clears_drift_and_staleness(self):
        r = self.repo()
        r.sync(DRIFTED)
        self.assertEqual((r.moved(), r.stale()), ([], [STALE]))
        r.checked_run("drift.py", "artifacts", "checked", STALE)
        self.assertEqual((r.moved(), r.stale()), ([], []))
        agree(self, r)
        self.assertIn("code-drifted: none", r.draw()[1])


class Renaming(ShopTest):
    # @scenario blueprint/sync: Rename rewrites tags
    def test_rename_carries_drift_artifacts_tags_and_baseline(self):
        r = self.repo()
        before = r.coverage()
        r.checked_run("drift.py", "rename", DRIFTED, "orders/pay")
        self.assertEqual(r.moved(), ["orders/pay"])
        self.assertEqual(r.load()["artifacts"][STALE]["capabilities"], ["orders/pay", "orders/cart"])
        self.assertTrue((r.root / ".blueprint/baseline/orders/pay.md").is_file())
        m, after = agree(self, r)
        self.assertEqual(after["summary"], before["summary"])
        self.assertEqual(claimed(after, "orders/pay"), claimed(before, DRIFTED))
        self.assertNotIn(DRIFTED, {n["id"] for n in m["nodes"]})
        # The orphan in legacy.spec.ts was rewritten too, and is still an orphan.
        self.assertIn("orders/pay", {o["capability"] for o in after["orphans"]})


class Rewording(ShopTest):
    # @scenario blueprint/coverage: Scenario reworded
    def test_reworded_scenario_orphans_its_tags_and_suggests_the_new_name(self):
        r = self.repo()
        cap = "catalog/search"
        old = self.scenarios[cap][0]  # the one smoke.test.ts and others claim
        before = r.coverage()
        path = f".blueprint/baseline/{cap}.md"
        r.write(path, r.read(path).replace(f"Scenario: {old}**", f"Scenario: {old} quickly**"))
        _, after = agree(self, r)
        new = [o for o in after["orphans"] if o["capability"] == cap]
        self.assertTrue(new)
        self.assertEqual({(o["scenario"], o["reason"], o["suggestion"]) for o in new},
                         {(old, "unknown scenario", f"{old} quickly")})
        self.assertIn(f"nearest: {old} quickly", r.run("coverage.py").stdout)
        self.assertLess(after["summary"]["claimed"], before["summary"]["claimed"])


class Stamping(unittest.TestCase):
    # @scenario blueprint/sync: Uncommitted code
    def test_stamp_warns_when_anchored_code_is_uncommitted(self):
        with FakeRepo() as r:
            r.capability("auth/session", ["src/auth/**"], {"Expiry": ["Expired session redirects"]})
            r.write("src/auth/session.ts", "export const ttl = 1;\n")
            r.write("src/other.ts", "export const o = 1;\n")
            r.sync()
            head = r.git("rev-parse", "HEAD").strip()
            # Only unanchored files are dirty: no warning.
            r.edit("src/other.ts")
            quiet = r.checked_run("drift.py", "stamp", "auth/session")
            self.assertNotIn("warning", quiet.stderr)
            r.edit("src/auth/session.ts")
            r.write("src/auth/new.ts", "export const n = 1;\n")  # untracked counts too
            out = r.checked_run("drift.py", "stamp", "auth/session")
            self.assertIn("warning: 2 of them uncommitted, so syncedCommit predates them", out.stderr)
            self.assertIn("commit the code, then stamp again", out.stderr)
            # The stamp is still written, at the commit that predates the edits.
            self.assertEqual(r.load()["specs"]["auth/session"]["syncedCommit"], head)


class Tidying(ShopTest):
    # @scenario blueprint/tidy: Status after tidy
    def test_renames_into_domains_keep_an_in_sync_repo_in_sync(self):
        r = self.repo()
        r.sync(DRIFTED)
        r.checked_run("drift.py", "artifacts", "checked", STALE)
        before = r.drift_status()
        self.assertEqual(set(before.values()), {"in-sync"})
        stamps = {c: (s["syncedCommit"], s.get("specVersion"), s["anchorsFiles"])
                  for c, s in r.load()["specs"].items()}
        # What an approved tidy table writes: a new domain, the bare capabilities moved under it.
        r.domain("platform", "What every part of the shop leans on.")
        renames = {c: f"platform/{c}" for c in ("notifications", "audit-log", "api-gateway")}
        for old, new in renames.items():
            r.checked_run("drift.py", "rename", old, new)
        r.commit("tidy")
        check = r.drift("check")
        self.assertEqual(check.returncode, 0, check.stdout)
        after = r.drift_status()
        self.assertEqual(sorted(after), sorted(renames.get(c, c) for c in before))
        self.assertEqual(set(after.values()), {"in-sync"})
        self.assertEqual(r.stale(), [])
        specs = r.load()["specs"]
        for old, new in renames.items():
            self.assertEqual((specs[new]["syncedCommit"], specs[new].get("specVersion"),
                              specs[new]["anchorsFiles"]), stamps[old], new)
        agree(self, r)


class Demo(unittest.TestCase):
    def run_demo(self, folder):
        return subprocess.run([sys.executable, str(FAKEREPO), str(folder)], capture_output=True,
                              text=True, env=ENV)

    # @scenario blueprint/map: Elsewhere
    def test_draws_reruns_and_refuses_other_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self.run_demo(Path(tmp) / "shop")
            self.assertEqual(out.returncode, 0, out.stderr)
            path, summary = out.stdout.strip().splitlines()
            self.assertEqual(Path(path), (Path(tmp) / "shop/map.html").resolve())
            self.assertTrue(Path(path).is_file())
            # Written with --out, so no ignore line is added.
            self.assertFalse((Path(tmp) / "shop/.blueprint/.gitignore").exists())
            self.assertEqual(summary, "22 capabilities, 5 domains; code-drifted: orders/checkout; "
                                      "1 stale artifact; 104 of 227 scenarios claimed, 2 orphan tags")
            again = self.run_demo(Path(tmp) / "shop")
            self.assertEqual(again.returncode, 0, again.stderr)
            refused = self.run_demo(tmp)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("isn't an earlier demo", refused.stderr)


if __name__ == "__main__":
    unittest.main()
