#!/usr/bin/env python3
"""Tests for backfill.py: each runs the script in a throwaway git repo.

    python3 skills/blueprint/scripts/test_backfill.py
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKFILL = HERE / "backfill.py"
DRIFT = HERE / "drift.py"
# Ignore the developer's git config (signing, hooks, templates) in the throwaway repos.
ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")

FILES = {
    "src/auth/session.py": "def session(): pass\n",
    "src/auth/tokens.py": "def token(): pass\n",
    "src/auth/oauth.py": "def oauth(): pass\n",
    "src/auth/__init__.py": "",
    "src/billing/invoice.py": "def invoice(): pass\n",
    "README.md": "app\n",
}
STATE = {
    "version": 2,
    "domains": {},
    "specs": {"auth/session": {"ref": "https://notion/session", "specVersion": "v1",
                               "anchors": ["src/auth/session.py"],
                               "anchorsFiles": {"src/auth/session.py": "keep"},
                               "syncedCommit": "abc"}},
}
PLAN = {"survey": {"stack": "python"},
        "domains": {"auth": {"purpose": "Who you are", "folders": ["src/auth"]},
                    "billing": {"purpose": "Getting paid", "folders": ["src/billing/**"]}}}


class Repo:
    def __init__(self, files=FILES, state=STATE):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.git("init", "-q")
        for path, text in files.items():
            self.write(path, text)
        self.write(".blueprint/blueprint.json", json.dumps(state, indent=2) + "\n")
        self.commit("init")

    def write(self, path, text):
        (self.root / path).parent.mkdir(parents=True, exist_ok=True)
        (self.root / path).write_text(text)

    def read(self, path):
        return json.loads((self.root / path).read_text())

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True, text=True, env=ENV).stdout

    def commit(self, msg):
        self.git("add", "-A")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", msg)

    def run(self, *args, stdin=None):
        return subprocess.run([sys.executable, str(BACKFILL), *args], cwd=self.root, input=stdin,
                              capture_output=True, text=True, env=ENV)

    def ok(self, *args, stdin=None):
        out = self.run(*args, stdin=stdin)
        assert out.returncode == 0, out.stderr
        return out.stdout

    def status(self):
        return json.loads(self.ok("status", "--json"))

    def init(self, plan=PLAN):
        return self.ok("init", stdin=json.dumps(plan))

    def domain(self, name):
        return self.read(f".blueprint/backfill/domains/{name}.progress.json")

    def set_domain(self, name, data):
        self.write(f".blueprint/backfill/domains/{name}.progress.json", json.dumps(data))

    def close(self):
        self._tmp.cleanup()


def reviewed(repo, domain, caps, ref="https://notion/auth"):
    """A domain whose passes 2 and 3 are done, with capabilities stamped and baselines written."""
    repo.set_domain(domain, {"domain": domain, "ref": ref, "covered": True,
                             "passes": {"2": "done", "3": "done"},
                             "capabilities": {c: {"anchors": a, "ref": f"https://notion/{c}",
                                                  "specVersion": "v1"}
                                              for c, a in caps.items()}})
    for cap in caps:
        if cap in STATE["specs"]:
            continue
        repo.write(f".blueprint/baseline/{cap}.md", "## Purpose\n\nx\n")
    repo.commit(f"review {domain}")
    new = [c for c in caps if c not in STATE["specs"]]
    if new:
        repo.ok("stamp", *new)


class Init(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()

    def tearDown(self):
        self.repo.close()

    # @scenario blueprint/backfill: README explains the folder
    def test_init_writes_the_folder_and_readme(self):
        out = self.repo.init()
        self.assertIn("/blueprint-backfill domain auth", out)
        self.assertIn("/blueprint-backfill domain billing", out)
        progress = self.repo.read(".blueprint/backfill/progress.json")
        self.assertEqual(progress["passes"], {"1": "done"})
        self.assertEqual(progress["survey"], {"stack": "python"})
        self.assertEqual(progress["domains"]["auth"]["folders"], ["src/auth"])
        self.assertTrue((self.repo.root / ".blueprint/backfill/domains").is_dir())
        self.assertTrue((self.repo.root / ".blueprint/backfill/drafts").is_dir())
        readme = (self.repo.root / ".blueprint/backfill/README.md").read_text()
        self.assertIn("Blueprint backfill in progress: pass 2 of 5", readme)
        self.assertIn("Resume with `/blueprint-backfill`", readme)
        self.assertIn("deleted when the backfill finishes", readme)

    def test_init_refuses_a_second_backfill(self):
        self.repo.init()
        out = self.repo.run("init", stdin=json.dumps(PLAN))
        self.assertEqual(out.returncode, 2)
        self.assertIn("already in progress", out.stderr)

    def test_init_refuses_a_domain_that_is_a_capability_or_nested(self):
        state = json.loads(json.dumps(STATE))
        state["specs"]["session"] = {"ref": None, "anchors": ["src/auth/session.py"]}
        self.repo.write(".blueprint/blueprint.json", json.dumps(state))
        for name in ("session", "auth/session", "a/b"):
            plan = {"domains": {name: {"folders": ["src"]}}}
            out = self.repo.run("init", stdin=json.dumps(plan))
            self.assertEqual(out.returncode, 2, name)
        out = self.repo.run("init", stdin=json.dumps({"domains": {"auth": {"purpose": "x"}}}))
        self.assertIn("needs \"folders\"", out.stderr)

    def test_init_never_touches_blueprint_json(self):
        before = (self.repo.root / ".blueprint/blueprint.json").read_text()
        self.repo.init()
        self.assertEqual((self.repo.root / ".blueprint/blueprint.json").read_text(), before)


class Status(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()

    def tearDown(self):
        self.repo.close()

    def test_no_backfill(self):
        self.assertEqual(self.repo.status(), {"active": False})
        self.assertEqual(self.repo.ok("status").strip(), "no backfill in progress")

    def test_pass_one_unfinished(self):
        self.repo.write(".blueprint/backfill/progress.json",
                        json.dumps({"passes": {"1": "in-progress"}, "domains": {}}))
        s = self.repo.status()
        self.assertEqual(s["pass"], 1)
        self.assertEqual(s["line"], "Backfill · pass 1 of 5 · survey")
        self.assertEqual(s["next"][0]["command"], "/blueprint-backfill")

    # @scenario blueprint/backfill: Resume in a new session
    def test_resume_offers_the_domain_left_behind(self):
        self.repo.init()
        self.repo.ok("pass", "auth", "2", "done")
        s = self.repo.status()
        self.assertEqual(s["pass"], 2)
        self.assertEqual(s["line"], "Backfill · pass 2 of 5 · 1 of 2 domains mapped")
        steps = {st["domain"]: st for st in s["next"]}
        self.assertEqual(steps["billing"]["command"], "/blueprint-backfill domain billing")
        self.assertEqual(steps["billing"]["pass"], 2)
        self.assertEqual(steps["auth"]["pass"], 3)
        text = self.repo.ok("status")
        self.assertIn("/blueprint-backfill domain billing", text)
        readme = (self.repo.root / ".blueprint/backfill/README.md").read_text()
        self.assertIn("pass 2 of 5", readme)

    def test_line_counts_domains_reviewed(self):
        plan = {"domains": {d: {"folders": [f"src/{d}"]} for d in ("a", "b", "c", "d")}}
        self.repo.init(plan)
        for d in ("a", "b"):
            self.repo.set_domain(d, {"passes": {"2": "done", "3": "done"}})
        for d in ("c", "d"):
            self.repo.set_domain(d, {"passes": {"2": "done", "3": "in-progress"}})
        self.assertEqual(self.repo.status()["line"],
                         "Backfill · pass 3 of 5 · 2 of 4 domains reviewed")

    def test_reviewed_unfolded_domain_points_to_fold(self):
        self.repo.init()
        self.repo.set_domain("auth", {"passes": {"2": "done", "3": "done"}})
        steps = {st["domain"]: st for st in self.repo.status()["next"]}
        self.assertEqual(steps["auth"]["command"], "/blueprint-backfill fold")

    def test_lists_drafts_awaiting_review(self):
        self.repo.init()
        self.repo.write(".blueprint/backfill/drafts/auth/tokens.md", "draft\n")
        auth = next(d for d in self.repo.status()["domains"] if d["name"] == "auth")
        self.assertEqual(auth["drafts"], ["auth/tokens"])

    def test_lists_drafts_of_bare_capabilities(self):
        self.repo.init()
        self.repo.set_domain("auth", {"capabilities": {"tokens": {"anchors": ["src"]}}})
        self.repo.write(".blueprint/backfill/drafts/tokens.md", "draft\n")
        auth = next(d for d in self.repo.status()["domains"] if d["name"] == "auth")
        self.assertEqual(auth["drafts"], ["tokens"])

    def test_bad_state_is_reported(self):
        self.repo.init()
        self.repo.set_domain("auth", {"passes": {"2": "finished"}})
        out = self.repo.run("status")
        self.assertEqual(out.returncode, 2)
        self.assertIn("finished", out.stderr)


class Uncovered(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.repo.init()

    def tearDown(self):
        self.repo.close()

    # @scenario blueprint/backfill: Domain not yet covered
    def test_names_unanchored_files_in_the_domains_folders(self):
        self.repo.set_domain("auth", {"capabilities": {"auth/tokens":
                                                       {"anchors": ["src/auth/tokens.py"]}}})
        files = json.loads(self.repo.ok("uncovered", "auth", "--json"))
        # session.py is anchored in blueprint.json, tokens.py in the domain's progress file.
        self.assertEqual(files, ["src/auth/__init__.py", "src/auth/oauth.py"])
        self.assertEqual(self.repo.ok("uncovered", "auth").split(), files)

    def test_glue_and_exclusions(self):
        self.repo.set_domain("auth", {"glue": ["**/__init__.py"], "capabilities": {
            "auth/tokens": {"anchors": ["src/auth/**", "!src/auth/oauth.py"]}}})
        self.assertEqual(json.loads(self.repo.ok("uncovered", "auth", "--json")),
                         ["src/auth/oauth.py"])

    def test_another_domains_capability_covers_a_file(self):
        self.repo.set_domain("billing", {"capabilities": {
            "billing/invoices": {"anchors": ["src/billing/**", "src/auth/oauth.py"]}}})
        self.assertNotIn("src/auth/oauth.py",
                         json.loads(self.repo.ok("uncovered", "auth", "--json")))
        self.assertEqual(json.loads(self.repo.ok("uncovered", "billing", "--json")), [])

    def test_unknown_domain(self):
        out = self.repo.run("uncovered", "search")
        self.assertEqual(out.returncode, 2)
        self.assertIn("unknown domain: search", out.stderr)


class Stamp(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.repo.init()

    def tearDown(self):
        self.repo.close()

    # @scenario blueprint/backfill: Two domains in parallel
    def test_stamps_go_to_the_domain_file_only(self):
        before = (self.repo.root / ".blueprint/blueprint.json").read_text()
        self.repo.set_domain("auth", {"capabilities": {"auth/tokens":
                                                       {"anchors": ["src/auth/tokens.py"]}}})
        self.repo.set_domain("billing", {"capabilities": {"billing/invoices":
                                                          {"anchors": ["src/billing/**"]}}})
        self.repo.commit("map")
        out = self.repo.ok("stamp", "auth/tokens", "billing/invoices")
        self.assertIn("stamped auth/tokens: 1 files", out)
        head = self.repo.git("rev-parse", "HEAD").strip()
        tokens = self.repo.domain("auth")["capabilities"]["auth/tokens"]
        self.assertEqual(list(tokens["anchorsFiles"]), ["src/auth/tokens.py"])
        self.assertEqual(tokens["syncedCommit"], head)
        self.assertIn("src/billing/invoice.py",
                      self.repo.domain("billing")["capabilities"]["billing/invoices"]["anchorsFiles"])
        self.assertEqual((self.repo.root / ".blueprint/blueprint.json").read_text(), before)

    def test_warns_about_uncommitted_files(self):
        self.repo.set_domain("auth", {"capabilities": {"auth/tokens":
                                                       {"anchors": ["src/auth/tokens.py"]}}})
        self.repo.write("src/auth/tokens.py", "changed\n")
        out = self.repo.run("stamp", "auth/tokens")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("uncommitted", out.stderr)

    def test_refuses_a_capability_blueprint_json_owns(self):
        self.repo.set_domain("auth", {"capabilities": {"auth/session":
                                                       {"anchors": ["src/auth/session.py"]}}})
        out = self.repo.run("stamp", "auth/session")
        self.assertEqual(out.returncode, 2)
        self.assertIn("drift.py stamp", out.stderr)

    def test_writes_nothing_when_one_capability_lacks_anchors(self):
        self.repo.set_domain("auth", {"capabilities": {"auth/tokens":
                                                       {"anchors": ["src/auth/tokens.py"]}}})
        out = self.repo.run("stamp", "auth/tokens", "billing/invoices")
        self.assertEqual(out.returncode, 2)
        self.assertNotIn("anchorsFiles", self.repo.domain("auth")["capabilities"]["auth/tokens"])

    def test_finds_the_domain_that_lists_the_capability(self):
        self.repo.set_domain("auth", {"capabilities": {"billing/x":
                                                       {"anchors": ["src/auth/oauth.py"]}}})
        self.repo.ok("stamp", "billing/x")
        self.assertIn("syncedCommit", self.repo.domain("auth")["capabilities"]["billing/x"])

    def test_malformed_progress_exits_2(self):
        self.repo.set_domain("auth", {"passes": ["done"]})
        self.assertEqual(self.repo.run("stamp", "auth/tokens").returncode, 2)
        self.repo.set_domain("auth", {"capabilities": {"auth/tokens": "x"}})
        self.assertEqual(self.repo.run("stamp", "auth/tokens").returncode, 2)

    def test_refuses_without_anchors(self):
        out = self.repo.run("stamp", "auth/tokens")
        self.assertEqual(out.returncode, 2)
        self.assertIn("no anchors recorded for auth/tokens", out.stderr)


class Pass(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.repo.init()

    def tearDown(self):
        self.repo.close()

    def test_sets_a_pass(self):
        self.repo.ok("pass", "auth", "2", "in-progress")
        self.assertEqual(self.repo.domain("auth")["passes"]["2"], "in-progress")

    def test_refuses_bad_values(self):
        for args in (("auth", "1", "done"), ("auth", "2", "finished"), ("nope", "2", "done")):
            self.assertEqual(self.repo.run("pass", *args).returncode, 2, args)

    def test_a_pass_waits_for_the_one_before(self):
        out = self.repo.run("pass", "auth", "3", "done")
        self.assertEqual(out.returncode, 2)
        self.assertIn("pass 2 is pending", out.stderr)

    def test_leaves_the_shared_readme_alone(self):
        readme = self.repo.root / ".blueprint/backfill/README.md"
        before = readme.read_text()
        self.repo.ok("pass", "auth", "2", "done")
        self.assertEqual(readme.read_text(), before)

    def test_tags_and_artifacts_wait_for_fold(self):
        out = self.repo.run("pass", "auth", "4", "in-progress")
        self.assertEqual(out.returncode, 2)
        self.assertIn("isn't folded yet", out.stderr)


class Fold(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.repo.init()

    def tearDown(self):
        self.repo.close()

    def drift_check(self):
        out = subprocess.run([sys.executable, str(DRIFT), "check", "--json"], cwd=self.repo.root,
                             capture_output=True, text=True, env=ENV)
        return {c["capability"]: c["status"] for c in json.loads(out.stdout)}

    # @scenario blueprint/backfill: Fold
    def test_folds_every_finished_domain_at_once(self):
        reviewed(self.repo, "auth", {"auth/tokens": ["src/auth/tokens.py"],
                                     "auth/oauth": ["src/auth/oauth.py"]})
        reviewed(self.repo, "billing", {"billing/invoices": ["src/billing/**"]},
                 ref="https://notion/billing")
        self.assertNotIn("auth/tokens", self.drift_check())
        out = self.repo.ok("fold")
        self.assertIn("folded auth: 2 capabilities", out)
        self.assertIn("folded billing: 1 capabilities", out)
        state = self.repo.read(".blueprint/blueprint.json")
        self.assertEqual(state["domains"]["auth"],
                         {"ref": "https://notion/auth", "purpose": "Who you are"})
        tokens = state["specs"]["auth/tokens"]
        self.assertEqual(tokens["ref"], "https://notion/auth/tokens")
        self.assertEqual(tokens["specVersion"], "v1")
        self.assertEqual(tokens["anchors"], ["src/auth/tokens.py"])
        self.assertIn("src/auth/tokens.py", tokens["anchorsFiles"])
        self.assertTrue(self.repo.domain("auth")["folded"])
        self.repo.commit("fold")
        checked = self.drift_check()
        for cap in ("auth/tokens", "auth/oauth", "billing/invoices"):
            self.assertEqual(checked[cap], "in-sync", cap)
        self.assertIn("nothing to fold", self.repo.ok("fold"))

    # @scenario blueprint/backfill: Existing capability kept
    def test_existing_capability_kept(self):
        reviewed(self.repo, "auth", {"auth/session": ["src/auth/**"],
                                     "auth/tokens": ["src/auth/tokens.py"]})
        self.repo.ok("fold", "auth")
        session = self.repo.read(".blueprint/blueprint.json")["specs"]["auth/session"]
        self.assertEqual(session, STATE["specs"]["auth/session"])

    def test_existing_unspecced_capability_gets_its_spec(self):
        state = json.loads(json.dumps(STATE))
        state["specs"]["auth/tokens"] = {"ref": None, "anchors": ["src/auth/tokens.py"]}
        self.repo.write(".blueprint/blueprint.json", json.dumps(state))
        reviewed(self.repo, "auth", {"auth/tokens": ["src/auth/tokens.py"]})
        self.repo.ok("fold")
        tokens = self.repo.read(".blueprint/blueprint.json")["specs"]["auth/tokens"]
        self.assertEqual(tokens["ref"], "https://notion/auth/tokens")
        self.assertIn("syncedCommit", tokens)

    def test_unfinished_domain_waits(self):
        reviewed(self.repo, "auth", {"auth/tokens": ["src/auth/tokens.py"]})
        self.repo.set_domain("billing", {"passes": {"2": "done", "3": "in-progress"}})
        self.repo.ok("fold")
        state = self.repo.read(".blueprint/blueprint.json")
        self.assertIn("auth", state["domains"])
        self.assertNotIn("billing", state["domains"])
        out = self.repo.run("fold", "billing")
        self.assertEqual(out.returncode, 1)
        self.assertIn("pass 3 is in-progress", out.stderr)

    def test_refuses_unstamped_or_misnamed_capabilities(self):
        self.repo.set_domain("auth", {"ref": "r", "covered": True,
                                      "passes": {"2": "done", "3": "done"},
                                      "capabilities": {
                                          "auth/tokens": {"ref": "x", "anchors": ["src/auth/tokens.py"]},
                                          "billing/x": {"ref": "x", "anchors": ["src"],
                                                        "anchorsFiles": {"a": "b"},
                                                        "syncedCommit": None}}})
        before = (self.repo.root / ".blueprint/blueprint.json").read_text()
        out = self.repo.run("fold", "auth")
        self.assertEqual(out.returncode, 1)
        self.assertIn("auth/tokens isn't stamped", out.stderr)
        self.assertIn("billing/x isn't named auth/<capability>", out.stderr)
        self.assertEqual((self.repo.root / ".blueprint/blueprint.json").read_text(), before)
        self.assertFalse(self.repo.domain("auth").get("folded"))

    def test_refuses_a_domain_without_an_overview(self):
        reviewed(self.repo, "auth", {"auth/tokens": ["src/auth/tokens.py"]}, ref=None)
        out = self.repo.run("fold")
        self.assertEqual(out.returncode, 1)
        self.assertIn("no overview page", out.stderr)

    def test_refuses_an_uncovered_domain(self):
        reviewed(self.repo, "auth", {"auth/tokens": ["src/auth/tokens.py"]})
        dom = self.repo.domain("auth")
        dom["covered"] = False
        self.repo.set_domain("auth", dom)
        out = self.repo.run("fold", "auth")
        self.assertEqual(out.returncode, 1)
        self.assertIn("coverage isn't confirmed", out.stderr)

    def test_anchors_matching_nothing_are_named(self):
        reviewed(self.repo, "auth", {"auth/legacy": ["src/legacy/**"]})
        out = self.repo.run("fold", "auth")
        self.assertEqual(out.returncode, 1)
        self.assertIn("anchors match no files", out.stderr)

    def test_refuses_a_capability_without_a_baseline(self):
        reviewed(self.repo, "auth", {"auth/tokens": ["src/auth/tokens.py"]})
        (self.repo.root / ".blueprint/baseline/auth/tokens.md").unlink()
        out = self.repo.run("fold")
        self.assertEqual(out.returncode, 1)
        self.assertIn("no baseline", out.stderr)


class Finish(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.repo.init()
        reviewed(self.repo, "auth", {"auth/session": ["src/auth/session.py"],
                                     "auth/tokens": ["src/auth/**"]})
        reviewed(self.repo, "billing", {"billing/invoices": ["src/billing/**"]},
                 ref="https://notion/billing")
        self.repo.ok("fold")

    def tearDown(self):
        self.repo.close()

    def finish_passes(self, *domains):
        for name in domains:
            for n in ("4", "5"):
                self.repo.ok("pass", name, n, "done")

    # @scenario blueprint/backfill: Last pass done
    def test_reports_what_the_backfill_wrote_and_deletes_the_folder(self):
        self.finish_passes("auth", "billing")
        auth = self.repo.domain("auth")
        auth["capabilities"]["auth/session"]["existing"] = True
        auth["capabilities"]["auth/tokens"].update(
            review={"accepted": 3, "amended": 1, "rejected": 2}, tags=4)
        auth["artifacts"] = ["auth-guide", "login-help"]
        self.repo.set_domain("auth", auth)
        billing = self.repo.domain("billing")
        billing["capabilities"]["billing/invoices"].update(review={"accepted": 2}, tags=1)
        self.repo.set_domain("billing", billing)
        self.assertIn("finish the backfill", self.repo.status()["next"][0]["why"])
        out = self.repo.ok("finish")
        self.assertIn("backfill finished: 2 domains · 3 capabilities (2 new) · scenarios "
                      "5 accepted, 1 amended, 2 rejected · 5 tags · 2 artifacts", out)
        self.assertIn("  auth: 2 capabilities (1 new)", out)
        self.assertFalse((self.repo.root / ".blueprint/backfill").exists())
        self.assertEqual(self.repo.status(), {"active": False})
        self.assertIn("auth/tokens", self.repo.read(".blueprint/blueprint.json")["specs"])

    def test_refuses_while_a_domain_has_passes_left(self):
        self.finish_passes("auth")
        self.repo.ok("pass", "billing", "4", "done")
        out = self.repo.run("finish")
        self.assertEqual(out.returncode, 1)
        self.assertIn("billing: pass 5 not done", out.stderr)
        self.assertIn("/blueprint-backfill domain billing", out.stderr)
        self.assertTrue((self.repo.root / ".blueprint/backfill/progress.json").is_file())

    def test_refuses_an_unfolded_domain(self):
        repo = Repo()
        self.addCleanup(repo.close)
        repo.init()
        reviewed(repo, "auth", {"auth/tokens": ["src/auth/tokens.py"]})
        out = repo.run("finish")
        self.assertEqual(out.returncode, 1)
        self.assertIn("auth isn't folded", out.stderr)

    def test_without_a_backfill(self):
        repo = Repo()
        self.addCleanup(repo.close)
        self.assertEqual(repo.run("finish").returncode, 2)


if __name__ == "__main__":
    unittest.main()
