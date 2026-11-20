#!/usr/bin/env python3
"""Tests for drift.py: each runs the script in a throwaway git repo.

    python3 skills/blueprint/scripts/test_drift.py
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DRIFT = Path(__file__).resolve().parent / "drift.py"
# Ignore the developer's git config (signing, hooks, templates) in the throwaway repos.
ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")


class Repo:
    def __init__(self, files, state):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
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

    def drift(self, *args):
        return subprocess.run([sys.executable, str(DRIFT), *args], cwd=self.root,
                              capture_output=True, text=True, env=ENV)

    def state(self):
        return json.loads((self.root / ".blueprint/blueprint.json").read_text())

    def close(self):
        self._tmp.cleanup()


def spec(*anchors):
    return {"ref": "page", "anchors": list(anchors)}


class DriftTest(unittest.TestCase):
    def repo(self, files, state):
        r = Repo(files, state)
        self.addCleanup(r.close)
        return r


class Version(DriftTest):
    def test_absent_means_one(self):
        r = self.repo({}, {"specs": {}})
        self.assertEqual(r.drift("version").stdout, "1\n")

    def test_recorded(self):
        r = self.repo({}, {"version": 2, "domains": {}, "specs": {}})
        self.assertEqual(r.drift("version").stdout, "2\n")


class Overlaps(DriftTest):
    FILES = {
        "shared/board/ops.ts": "", "shared/clock.ts": "", "shared/board/ops.test.ts": "",
        "worker/index.ts": "", "worker/board.ts": "",
    }
    STATE = {"specs": {
        "jams": spec("shared/**", "worker/index.ts", "!**/*.test.ts"),
        "board/ops": spec("shared/board/**", "!**/*.test.ts"),
        "room": spec("worker/board.ts", "worker/index.ts"),
    }}

    def test_broad_glob_and_entry_point(self):
        r = self.repo(self.FILES, self.STATE)
        out = r.drift("overlaps")
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout, (
            "shared/board/ops.ts\n"
            "    jams       shared/**\n"
            "    board/ops  shared/board/**\n"
            "worker/index.ts\n"
            "    jams  worker/index.ts\n"
            "    room  worker/index.ts\n"))

    def test_json(self):
        r = self.repo(self.FILES, self.STATE)
        report = json.loads(r.drift("overlaps", "--json").stdout)
        self.assertEqual([o["file"] for o in report], ["shared/board/ops.ts", "worker/index.ts"])
        self.assertEqual(report[1]["capabilities"], [
            {"capability": "jams", "anchors": ["worker/index.ts"]},
            {"capability": "room", "anchors": ["worker/index.ts"]},
        ])

    def test_none(self):
        r = self.repo({"a.ts": "", "b.ts": ""}, {"specs": {"a": spec("a.ts"), "b": spec("b.ts")}})
        self.assertEqual(r.drift("overlaps").stdout, "")
        self.assertEqual(json.loads(r.drift("overlaps", "--json").stdout), [])


class Rename(DriftTest):
    FILES = {"src/board/session.ts": "s", "shared/board/ops.ts": "o", "src/ui/app.ts": "u",
             ".blueprint/baseline/board.md": "# board\n"}
    STATE = {"specs": {
        "board": spec("src/board/**"),
        "board/ops": spec("shared/board/**"),
        "ui": spec("src/ui/**"),
    }, "changes": {
        "open": {"status": "approved", "capabilities": ["board", "ui"]},
        "other": {"status": "applied"},
    }}

    def stamped(self):
        r = self.repo(self.FILES, self.STATE)
        r.drift("stamp", "--all")
        r.git("add", "-A")
        r.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "stamp")
        return r

    def test_moves_key_and_baseline_keeping_stamps(self):
        r = self.stamped()
        before = r.state()
        out = r.drift("rename", "board", "board/session")
        self.assertEqual(out.returncode, 0, out.stderr)
        after = r.state()
        self.assertEqual(list(after["specs"]), ["board/session", "board/ops", "ui"])
        self.assertEqual(after["specs"]["board/session"], before["specs"]["board"])
        self.assertEqual(after["changes"], before["changes"])
        base = r.root / ".blueprint/baseline"
        self.assertFalse((base / "board.md").exists())
        self.assertEqual((base / "board/session.md").read_text(), "# board\n")

    def test_check_unchanged_but_for_the_name(self):
        r = self.stamped()
        r.write("src/board/session.ts", "edited")
        before = r.drift("check").stdout
        r.drift("rename", "board", "board/session")
        self.assertEqual(r.drift("check").stdout,
                         before.replace("board  ", "board/session  ", 1))

    def test_removes_emptied_baseline_folder(self):
        r = self.stamped()
        r.write(".blueprint/baseline/board/ops.md", "# ops\n")
        r.drift("rename", "board/ops", "ops")
        self.assertTrue((r.root / ".blueprint/baseline/ops.md").exists())
        self.assertFalse((r.root / ".blueprint/baseline/board").exists())

    def test_refuses_collisions(self):
        r = self.repo(self.FILES, dict(self.STATE, domains={"core": {}}))
        before = r.state()
        cases = {
            ("ui", "board/ops"): "already exists",
            ("ui", "core"): "is a domain",
            ("board/ops", "ui/ops"): "its domain ui is a capability",
            ("ui", "board/ops/x"): "domains are one level deep",
            ("ui", "x/y/z"): "domains are one level deep",
            ("ui", "../../escaped"): "domains are one level deep",
            ("ui", "ui/"): "domains are one level deep",
        }
        for (old, new), why in cases.items():
            out = r.drift("rename", old, new)
            self.assertNotEqual(out.returncode, 0, (old, new))
            self.assertIn(why, out.stderr, (old, new))
        self.assertEqual(r.state(), before)

    def test_refuses_new_parent_of_a_capability(self):
        r = self.repo({}, {"specs": {"a/b": spec("a"), "c": spec("c")}})
        out = r.drift("rename", "c", "a")
        self.assertIn("would be the parent of capability a/b", out.stderr)

    def test_leaf_may_move_under_its_own_name(self):
        r = self.repo(self.FILES, self.STATE)
        out = r.drift("rename", "ui", "ui/app")
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_refuses_leftover_baseline_at_new_name(self):
        r = self.repo(dict(self.FILES, **{".blueprint/baseline/ui/app.md": "# old\n"}), self.STATE)
        out = r.drift("rename", "ui", "ui/app")
        self.assertIn("baseline already exists", out.stderr)
        self.assertIn("ui", r.state()["specs"])

    def test_unknown(self):
        r = self.repo(self.FILES, self.STATE)
        self.assertIn("unknown capability", r.drift("rename", "nope", "x").stderr)


class Hint(DriftTest):
    def test_more_than_ten_without_domain(self):
        r = self.repo({}, {"specs": {f"c{i}": spec(f"c{i}/**") for i in range(11)}})
        out = r.drift("hint")
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout,
                         "11 capabilities have no domain: /blueprint-tidy can group them.\n")

    def test_ten_spread_out_is_quiet(self):
        r = self.repo({}, {"specs": {f"c{i}": spec(f"c{i}/**") for i in range(10)}})
        self.assertEqual(r.drift("hint").stdout, "")

    def test_three_share_a_folder(self):
        files = {"src/board/model.ts": "", "src/board/console/Deck.tsx": "", "src/ui/a.ts": ""}
        r = self.repo(files, {"specs": {
            "board": spec("src/board/model.ts"),
            "looper": spec("src/board/console/Deck.tsx", "src/audio/**"),
            "pads": spec("src/board/console/**"),
            "ui": spec("src/ui/**", "DESIGN.md", "**/*.css"),
        }})
        self.assertEqual(r.drift("hint").stdout,
                         "3 capabilities without a domain share src/board/ (board, looper, pads): "
                         "/blueprint-tidy can group them.\n")

    def test_bare_directory_anchor_is_its_own_folder(self):
        files = {"src/a/x.ts": "", "src/b/x.ts": "", "src/c/x.ts": ""}
        r = self.repo(files, {"specs": {n: spec(f"src/{n}") for n in "abc"}})
        self.assertEqual(r.drift("hint").stdout, "")

    def test_missing_bare_directory_is_its_own_folder(self):
        r = self.repo({}, {"specs": {"a": spec("src/a"), "b": spec("src/b/"), "c": spec("src/c")}})
        self.assertEqual(r.drift("hint").stdout, "")

    def test_capabilities_in_a_domain_do_not_count(self):
        files = {"src/board/a.ts": ""}
        r = self.repo(files, {"version": 2, "domains": {"board": {"ref": "p", "purpose": "x"}},
                              "specs": {n: spec("src/board/a.ts")
                                        for n in ["board/a", "board/b", "board/c"]}})
        self.assertEqual(r.drift("hint").stdout, "")


class FilesAndPrune(DriftTest):
    FILES = {"shared/board/ops.ts": "o", "shared/util.ts": "u", "shared/gone.ts": "g"}
    STATE = {"specs": {"jams": spec("shared/**")}}

    def test_files_with_proposed_anchors_writes_nothing(self):
        r = self.repo(self.FILES, self.STATE)
        before = r.state()
        out = r.drift("files", "jams", "shared/**", "!shared/board/**").stdout.split()
        self.assertEqual(out, ["shared/gone.ts", "shared/util.ts"])
        self.assertEqual(r.state(), before)

    def test_prune_keeps_synced_commit_and_real_removals(self):
        r = self.repo(self.FILES, self.STATE)
        r.drift("stamp", "jams")
        (r.root / "shared/gone.ts").unlink()
        state = r.state()
        synced = state["specs"]["jams"]["syncedCommit"]
        state["specs"]["jams"]["anchors"] = ["shared/**", "!shared/board/**"]
        r.write(".blueprint/blueprint.json", json.dumps(state))
        self.assertEqual(r.drift("prune", "jams").returncode, 0)
        jams = r.state()["specs"]["jams"]
        self.assertEqual(sorted(jams["anchorsFiles"]), ["shared/gone.ts", "shared/util.ts"])
        self.assertEqual(jams["syncedCommit"], synced)
        check = json.loads(r.drift("check", "--json").stdout)[0]
        self.assertEqual(check["changed"], ["shared/gone.ts"])


if __name__ == "__main__":
    unittest.main()
