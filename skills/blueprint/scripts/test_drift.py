#!/usr/bin/env python3
"""Tests for drift.py: each runs the script in a throwaway git repo.

    python3 skills/blueprint/scripts/test_drift.py
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DRIFT = Path(__file__).resolve().parent / "drift.py"
sys.path.insert(0, str(DRIFT.parent / "e2e"))
import fakerepo  # noqa: E402  (the TS workspace fixture)
# Ignore the developer's git config (signing, hooks, templates) in the throwaway repos.
# NODE_PATH goes too, so no typescript is found but one linked into a fixture.
ENV = dict({k: v for k, v in os.environ.items() if k != "NODE_PATH"},
           GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
# Tests that expect "typescript not installed" need node to get as far as looking for it.
NEEDS_NODE = unittest.skipUnless(shutil.which("node"), "node not found")


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

    # @scenario blueprint/sync: Overlap listed
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

    # @scenario blueprint/sync: Rename rewrites tags
    def test_rewrites_scenario_tags(self):
        files = dict(self.FILES, **{
            "tests/ui.test.ts": "// @scenario ui: Empty query\n"
                                "// @scenario ui : Spaced colon\nit('x')\n",
            "tests/test_ui.py": "# @scenario ui: Empty query\r\n"
                                "# @scenario ui/other: Not this one\r\n",
            "tests/other.rs": "// @scenario board: Untouched\n",
            ".blueprint/notes.md": "@scenario ui: inside .blueprint stays\n",
            "tests/blob.bin": "@scenario ui: binary\0\n",
        })
        r = self.repo(files, self.STATE)
        out = r.drift("rename", "ui", "catalog/ui")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout, "renamed ui to catalog/ui; 3 tags rewritten\n")
        read = lambda p: (r.root / p).read_bytes().decode()
        self.assertEqual(read("tests/ui.test.ts"), "// @scenario catalog/ui: Empty query\n"
                                                   "// @scenario catalog/ui : Spaced colon\nit('x')\n")
        self.assertEqual(read("tests/test_ui.py"), "# @scenario catalog/ui: Empty query\r\n"
                                                   "# @scenario ui/other: Not this one\r\n")
        for path in ("tests/other.rs", ".blueprint/notes.md", "tests/blob.bin"):
            self.assertEqual(read(path), files[path], path)

    def test_rewrites_only_what_coverage_reads(self):
        files = dict(self.FILES, **{
            "tests/fixture.py": 'FIX = "// @scenario ui: Empty query\\n"\n',
            "README.md": "Tag a test with `@scenario ui: Empty query`.\n",
            "tests/tick.ts": "// @scenario `ui`: Empty query\n" + "x" * 9000 + "\0\n",
        })
        r = self.repo(files, self.STATE)
        (r.root / "tests/latin.py").write_bytes(b"# @scenario ui: Caf\xe9\n")
        outside = tempfile.NamedTemporaryFile("w", suffix=".ts", delete=False)
        outside.write("// @scenario ui: Outside\n")
        outside.close()
        self.addCleanup(os.unlink, outside.name)
        (r.root / "tests/link.ts").symlink_to(outside.name)
        out = r.drift("rename", "ui", "catalog/ui")
        self.assertEqual(out.stdout, "renamed ui to catalog/ui; 2 tags rewritten\n", out.stderr)
        read = lambda p: (r.root / p).read_bytes()
        self.assertEqual(read("tests/latin.py"), b"# @scenario catalog/ui: Caf\xe9\n")
        self.assertTrue(read("tests/tick.ts").startswith(b"// @scenario `catalog/ui`: Empty query\n"))
        for path in ("tests/fixture.py", "README.md"):
            self.assertEqual(read(path).decode(), files[path], path)
        self.assertEqual(Path(outside.name).read_text(), "// @scenario ui: Outside\n")

    def test_unwritable_tag_file_is_named(self):
        files = dict(self.FILES, **{"tests/a.test.ts": "// @scenario ui: A\n"})
        r = self.repo(files, self.STATE)
        (r.root / "tests/a.test.ts").chmod(0o444)
        out = r.drift("rename", "ui", "catalog/ui")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("couldn't rewrite the ui tags in: tests/a.test.ts", out.stderr)
        self.assertIn("catalog/ui", r.state()["specs"])

    def test_unreadable_file_is_named(self):
        files = dict(self.FILES, **{"tests/a.test.ts": "// @scenario ui: A\n",
                                    "tests/b.test.ts": "// @scenario ui: B\n"})
        r = self.repo(files, self.STATE)
        (r.root / "tests/b.test.ts").chmod(0o000)
        self.addCleanup((r.root / "tests/b.test.ts").chmod, 0o644)
        out = r.drift("rename", "ui", "catalog/ui")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout, "renamed ui to catalog/ui; 1 tags rewritten\n")
        self.assertIn("couldn't read, so any tags in them still name ui: tests/b.test.ts (",
                      out.stderr)
        self.assertEqual((r.root / "tests/a.test.ts").read_text(), "// @scenario catalog/ui: A\n")

    def test_no_tags_no_count(self):
        r = self.repo(self.FILES, self.STATE)
        out = r.drift("rename", "ui", "ui/app")
        self.assertEqual(out.stdout, "renamed ui to ui/app\n")


class Hint(DriftTest):
    # @scenario blueprint/sync: Growing flat list
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


class Artifacts(DriftTest):
    FILES = {"billing/invoices.ts": "i", "billing/refunds.ts": "r", "search/index.ts": "s"}
    STATE = {"version": 2, "domains": {"billing": {"ref": "p", "purpose": "money"}}, "specs": {
        "billing/invoices": spec("billing/invoices.ts"),
        "search": spec("search/**"),
    }}
    URL = "https://help.example.com/invoices"

    def add(self, r, *caps, kind="webpage", value=URL, description="Invoices help", **kw):
        extra = [a for k, v in kw.items() for a in (f"--{k}", v)]
        return r.drift("artifacts", "add", "--type", kind, "--value", value,
                       "--description", description, *extra, *caps)

    def stale(self, r, *args):
        out = r.drift("artifacts", "--json", *args)
        self.assertEqual(out.returncode, 0, out.stderr)
        return {a["id"]: a["changed"] for a in json.loads(out.stdout)}

    def test_add_stamps_as_checked(self):
        r = self.repo(self.FILES, self.STATE)
        out = self.add(r, "billing/invoices", id="invoices-help")
        self.assertEqual(out.returncode, 0, out.stderr)
        art = r.state()["artifacts"]["invoices-help"]
        self.assertEqual(art["type"], "webpage")
        self.assertEqual(art["value"], self.URL)
        self.assertEqual(art["description"], "Invoices help")
        self.assertEqual(art["capabilities"], ["billing/invoices"])
        self.assertEqual(list(art["checkedFiles"]), ["billing/invoices.ts"])
        listed = r.drift("artifacts")
        self.assertEqual((listed.returncode, listed.stdout), (0, ""))

    def test_id_derived_from_description(self):
        r = self.repo(self.FILES, self.STATE)
        self.add(r, "search", description="Search: how it ranks results, explained in full")
        self.add(r, "search", description="Search: how it ranks results, explained again")
        self.assertEqual(list(r.state()["artifacts"]),
                         ["search-how-it-ranks-results", "search-how-it-ranks-results-2"])

    # @scenario blueprint/sync: Code changes after a check
    def test_code_change_lists_artifact_with_file(self):
        r = self.repo(self.FILES, self.STATE)
        self.add(r, "billing/invoices", id="invoices-help")
        self.add(r, "search", id="search-help")
        r.write("billing/invoices.ts", "edited")
        self.assertEqual(self.stale(r), {"invoices-help": ["billing/invoices.ts"]})
        report = json.loads(r.drift("artifacts", "--json").stdout)[0]
        self.assertEqual(report["link"], self.URL)
        self.assertEqual(report["capabilities"], ["billing/invoices"])
        text = r.drift("artifacts").stdout
        self.assertEqual(text, f"invoices-help  webpage  {self.URL}\n    Invoices help\n"
                               "      billing/invoices.ts\n")

    # @scenario blueprint/sync: Spec synced, artifact not checked
    def test_spec_stamp_does_not_clear_it(self):
        r = self.repo(self.FILES, self.STATE)
        self.add(r, "billing/invoices", id="invoices-help")
        r.write("billing/invoices.ts", "edited")
        r.drift("stamp", "billing/invoices")
        self.assertIn("invoices-help", self.stale(r))
        out = r.drift("artifacts", "checked", "invoices-help")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.stale(r), {})

    # @scenario blueprint/sync: Domain-wide artifact
    def test_domain_covers_capability_added_later(self):
        r = self.repo(self.FILES, self.STATE)
        self.add(r, "billing", id="billing-help")
        state = r.state()
        state["specs"]["billing/refunds"] = spec("billing/refunds.ts")
        r.write(".blueprint/blueprint.json", json.dumps(state))
        # The new capability's files count as added since the check.
        self.assertEqual(self.stale(r), {"billing-help": ["billing/refunds.ts"]})
        r.drift("artifacts", "checked", "--all")
        r.write("billing/refunds.ts", "edited")
        self.assertEqual(self.stale(r), {"billing-help": ["billing/refunds.ts"]})

    def test_filter_by_capability_or_domain(self):
        r = self.repo(self.FILES, self.STATE)
        self.add(r, "billing", id="billing-help")
        self.add(r, "search", id="search-help")
        r.write("billing/invoices.ts", "edited")
        r.write("search/index.ts", "edited")
        self.assertEqual(list(self.stale(r, "search")), ["search-help"])
        self.assertEqual(list(self.stale(r, "billing/invoices")), ["billing-help"])
        self.assertEqual(list(self.stale(r, "billing")), ["billing-help"])
        self.assertNotEqual(r.drift("artifacts", "nope").returncode, 0)

    def test_removed_file_counts(self):
        r = self.repo(self.FILES, self.STATE)
        self.add(r, "search", id="search-help")
        (r.root / "search/index.ts").unlink()
        self.assertEqual(self.stale(r), {"search-help": ["search/index.ts"]})

    # @scenario blueprint/sync: Unknown type
    def test_refuses_bad_input_and_writes_nothing(self):
        r = self.repo(self.FILES, self.STATE)
        before = r.state()
        cases = [
            dict(kind="wiki"),
            dict(kind="webpage", value="help.example.com"),
            dict(kind="notion", value="not a url"),
            dict(kind="file", value="just/a/path.md"),
            dict(kind="file", value="owner/name:"),
            dict(kind="markdown", value="  "),
            dict(id="Not Kebab"),
        ]
        for kw in cases:
            out = self.add(r, "search", **kw)
            self.assertNotEqual(out.returncode, 0, kw)
        self.assertNotEqual(self.add(r, "nope").returncode, 0)
        self.assertNotEqual(r.drift("artifacts", "add", "--type", "webpage").returncode, 0)
        self.assertEqual(r.state(), before)
        self.add(r, "search", id="dup")
        self.assertIn("already exists", self.add(r, "search", id="dup").stderr)

    # @scenario blueprint/sync: Page in the same backend
    def test_value_shapes_and_links(self):
        r = self.repo(self.FILES, self.STATE)
        ok = {
            "gh-file": ("file", "acme/docs:guides/search.md",
                        "https://github.com/acme/docs/blob/HEAD/guides/search.md"),
            "git-file": ("file", "git@gitlab.com:acme/docs.git:guides/search.md", None),
            "notion-page": ("notion", "https://www.notion.so/acme/Search-123", None),
            "vault-note": ("obsidian", "Product/Search.md", None),
            "notes": ("markdown", "/srv/notes/search.md", None),
        }
        for aid, (kind, value, _) in ok.items():
            out = self.add(r, "search", kind=kind, value=value, id=aid)
            self.assertEqual(out.returncode, 0, (aid, out.stderr))
        self.assertEqual(r.state()["artifacts"]["notion-page"]["type"], "notion")
        r.write("search/index.ts", "edited")
        report = {a["id"]: a for a in json.loads(r.drift("artifacts", "--json").stdout)}
        self.assertEqual(list(report), list(ok))
        for aid, (kind, value, link) in ok.items():
            expected = value if kind == "notion" else link
            self.assertEqual(report[aid]["link"], expected, aid)

    def test_checked_and_remove_refuse_unknown(self):
        r = self.repo(self.FILES, self.STATE)
        self.add(r, "search", id="search-help")
        before = r.state()
        self.assertIn("unknown artifact", r.drift("artifacts", "checked", "nope").stderr)
        self.assertNotEqual(r.drift("artifacts", "checked").returncode, 0)
        self.assertIn("unknown artifact", r.drift("artifacts", "remove", "nope").stderr)
        self.assertEqual(r.state(), before)
        self.assertEqual(r.drift("artifacts", "remove", "search-help").returncode, 0)
        self.assertEqual(r.state()["artifacts"], {})

    def test_rename_updates_artifacts(self):
        r = self.repo(self.FILES, self.STATE)
        self.add(r, "search", "billing", id="both")
        out = r.drift("rename", "search", "billing/search")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(r.state()["artifacts"]["both"]["capabilities"],
                         ["billing/search", "billing"])
        self.assertEqual(self.stale(r), {})

    def test_remove_refuses_flags(self):
        r = self.repo(self.FILES, self.STATE)
        self.add(r, "search", id="search-help")
        out = r.drift("artifacts", "remove", "--all")
        self.assertIn("takes one artifact id", out.stderr)
        self.assertNotIn("Traceback", out.stderr)
        self.assertIn("search-help", r.state()["artifacts"])

    def test_checked_all_with_none_is_a_no_op(self):
        r = self.repo(self.FILES, self.STATE)
        out = r.drift("artifacts", "checked", "--all")
        self.assertEqual(out.returncode, 0, out.stderr)

    # @scenario blueprint/sync: Capability removed by hand
    def test_dangling_capability_is_reported_and_blocks_checked(self):
        r = self.repo(self.FILES, self.STATE)
        self.add(r, "search", id="search-help")
        state = r.state()
        state["specs"]["find"] = state["specs"].pop("search")  # renamed by hand
        r.write(".blueprint/blueprint.json", json.dumps(state))
        report = {a["id"]: a for a in json.loads(r.drift("artifacts", "--json", "find").stdout)}
        self.assertEqual(report["search-help"]["unknown"], ["search"])
        out = r.drift("artifacts", "checked", "search-help")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("search", out.stderr)
        self.assertEqual(r.state()["artifacts"]["search-help"]["checkedFiles"],
                         {"search/index.ts": state["artifacts"]["search-help"]["checkedFiles"]
                          ["search/index.ts"]})

    def test_prune_trims_artifact_stamps(self):
        files = dict(self.FILES, **{"search/core.ts": "c"})
        r = self.repo(files, self.STATE)
        self.add(r, "search", id="search-help")
        state = r.state()
        state["specs"]["search"]["anchors"] = ["search/core.ts"]
        r.write(".blueprint/blueprint.json", json.dumps(state))
        self.assertEqual(self.stale(r), {"search-help": ["search/index.ts"]})
        self.assertEqual(r.drift("prune", "search").returncode, 0)
        self.assertEqual(self.stale(r), {})

    def test_git_urls_need_a_path(self):
        r = self.repo(self.FILES, self.STATE)
        for value in ("git@github.com:acme/docs.git", "ssh://git@host:2222/acme/docs.git",
                      "docs.git:guides/search.md"):
            self.assertNotEqual(self.add(r, "search", kind="file", value=value).returncode, 0,
                                value)

    def test_github_git_urls_link_and_paths_are_escaped(self):
        r = self.repo(self.FILES, self.STATE)
        ok = {
            "ssh-gh": ("git@github.com:acme/docs.git:guides/search.md",
                       "https://github.com/acme/docs/blob/HEAD/guides/search.md"),
            "https-gh": ("https://github.com/acme/docs.git:guides/FAQ #2.md",
                         "https://github.com/acme/docs/blob/HEAD/guides/FAQ%20%232.md"),
        }
        for aid, (value, _) in ok.items():
            out = self.add(r, "search", kind="file", value=value, id=aid)
            self.assertEqual(out.returncode, 0, (aid, out.stderr))
        r.write("search/index.ts", "edited")
        report = {a["id"]: a for a in json.loads(r.drift("artifacts", "--json").stdout)}
        for aid, (_, link) in ok.items():
            self.assertEqual(report[aid]["link"], link, aid)

    def test_double_dash_filters_by_subcommand_name(self):
        state = json.loads(json.dumps(self.STATE))
        state["specs"]["remove"] = spec("search/**")
        r = self.repo(self.FILES, state)
        self.add(r, "remove", id="remove-help")
        r.write("search/index.ts", "edited")
        self.assertEqual(list(self.stale(r, "--", "remove")), ["remove-help"])

    def test_no_artifacts(self):
        r = self.repo(self.FILES, self.STATE)
        out = r.drift("artifacts")
        self.assertEqual((out.returncode, out.stdout), (0, ""))
        self.assertEqual(json.loads(r.drift("artifacts", "--json").stdout), [])


class Scoring(DriftTest):
    """Drift chance, confidence and reasons on direct changes, and drift.scoring."""

    def stamped(self, files, state):
        r = self.repo(files, state)
        self.assertEqual(r.drift("stamp", "--all").returncode, 0)
        return r

    def check(self, r, *args):
        out = r.drift("check", "--json", *args)
        return out, {row["capability"]: row for row in json.loads(out.stdout or "[]")}

    def test_in_sync_has_no_chance(self):
        r = self.stamped({"lib/core.py": "x = 1\n"}, {"specs": {"core": spec("lib/**")}})
        out, rows = self.check(r)
        self.assertEqual(out.returncode, 0)
        self.assertEqual(rows["core"], {"capability": "core", "status": "in-sync", "chance": 0.0,
                                        "confidence": "high", "reasons": []})

    def test_anchored_change_scores_one(self):
        r = self.stamped({"lib/core.py": "x = 1\n", "lib/old.py": ""},
                         {"specs": {"core": spec("lib/**")}})
        r.write("lib/core.py", "x = 2\n")
        r.write("lib/new.py", "")
        (r.root / "lib/old.py").unlink()
        out, rows = self.check(r)
        self.assertEqual(out.returncode, 1)
        row = rows["core"]
        self.assertEqual((row["status"], row["chance"], row["confidence"]),
                         ("code-moved", 1.0, "high"))
        self.assertEqual(row["changed"], ["lib/core.py", "lib/new.py", "lib/old.py"])
        self.assertEqual(row["reasons"], ["lib/core.py edited (anchored) → 1",
                                          "lib/new.py added (anchored) → 1",
                                          "lib/old.py removed (anchored) → 1"])
        text = r.drift("check").stdout
        self.assertIn("■■■■■■■■■■ 1 · high", text)
        self.assertIn("lib/core.py edited (anchored) → 1", text)

    @NEEDS_NODE
    def test_ts_capability_without_typescript_is_low_confidence(self):
        r = self.stamped({"src/a.ts": "", "lib/b.py": ""},
                         {"specs": {"web": spec("src/**"), "py": spec("lib/**")}})
        _, rows = self.check(r)
        self.assertEqual(rows["web"]["confidence"], "low")
        self.assertEqual(rows["web"]["reasons"][-1], "confidence low: typescript not installed "
                         "when stamped, so imports are followed by file")
        self.assertEqual(rows["py"]["confidence"], "high")
        self.assertFalse((r.root / ".blueprint/closure/py.json").exists())

    def test_ts_capability_stamped_before_closures(self):
        r = self.stamped({"src/a.ts": ""}, {"specs": {"web": spec("src/**")}})
        (r.root / ".blueprint/closure/web.json").unlink()
        _, rows = self.check(r)
        self.assertEqual(rows["web"]["confidence"], "low")
        self.assertIn("no import closure stamped yet", rows["web"]["reasons"][-1])

    def test_unstamped_rows_carry_the_fields(self):
        r = self.repo({"a.py": ""}, {"specs": {"lazy": {"ref": None, "anchors": ["a.py"]},
                                               "bare": {"ref": "page"}}})
        _, rows = self.check(r)
        self.assertEqual(rows["lazy"]["status"], "no-spec")
        self.assertEqual(rows["bare"]["status"], "no-anchors")
        for row in rows.values():
            self.assertEqual((row["chance"], row["confidence"]), (0.0, "low"))

    # @scenario blueprint/sync: Same diff, same number
    def test_same_diff_same_number(self):
        r = self.stamped({"src/a.ts": "a", "lib/b.py": "b"},
                         {"specs": {"web": spec("src/**"), "py": spec("lib/**")}})
        r.write("src/a.ts", "changed")
        first, second = r.drift("check", "--json"), r.drift("check", "--json")
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(r.drift("check").stdout, r.drift("check").stdout)

    # @scenario blueprint/sync: Bad setting
    def test_bad_setting_names_the_key(self):
        bad = [({"decay": 2}, "drift.scoring.decay"),
               ({"threshold": -0.1}, "drift.scoring.threshold"),
               ({"lockfileWeight": "0.3"}, "drift.scoring.lockfileWeight"),
               ({"packageWeight": True}, "drift.scoring.packageWeight"),
               ({"maxDepth": 0}, "drift.scoring.maxDepth"),
               ({"maxDepth": 2.5}, "drift.scoring.maxDepth"),
               ({"packages": {"@co/core": {"weight": 1.5}}}, 'drift.scoring.packages["@co/core"].weight'),
               ({"packages": {"@co/core": {"sideEffects": "yes"}}},
                'drift.scoring.packages["@co/core"].sideEffects')]
        for scoring, key in bad:
            with self.subTest(key=key, scoring=scoring):
                r = self.repo({"a.py": ""}, {"specs": {"a": spec("a.py")},
                                            "drift": {"scoring": scoring}})
                out = r.drift("check")
                self.assertEqual(out.returncode, 2)
                self.assertIn(key, out.stderr)
                self.assertEqual(out.stdout, "")

    def test_drift_not_an_object(self):
        r = self.repo({"a.py": ""}, {"specs": {"a": spec("a.py")}, "drift": None})
        out = r.drift("check", "--json")
        self.assertEqual(out.returncode, 2)
        self.assertIn("drift must be an object", out.stderr)

    def test_zero_threshold_keeps_untouched_in_sync(self):
        r = self.stamped({"a.py": ""}, {"specs": {"a": spec("a.py")},
                                        "drift": {"scoring": {"threshold": 0}}})
        out, rows = self.check(r)
        self.assertEqual((out.returncode, rows["a"]["status"]), (0, "in-sync"))

    def test_unknown_capability_exits_2(self):
        r = self.stamped({"a.py": ""}, {"specs": {"a": spec("a.py")}})
        out = r.drift("check", "nope")
        self.assertEqual(out.returncode, 2)
        self.assertIn("unknown capability: nope", out.stderr)

    def test_good_settings_accepted(self):
        r = self.stamped({"a.py": ""}, {"specs": {"a": spec("a.py")}, "drift": {"scoring": {
            "decay": 1, "packageWeight": 0, "lockfileWeight": 0.3, "threshold": 0.9,
            "maxDepth": 3, "packages": {"@co/core": {"weight": 1.0, "sideEffects": ["*.css"]}}}}})
        self.assertEqual(r.drift("check").returncode, 0)


SESSION_TEST = ("# @scenario auth/session: Expired session redirects to login\n"
                "def test_expired():\n    assert False\n\n"
                "# @scenario auth/session: Fresh session stays\n"
                "def test_fresh():\n    pass\n")


def junit(*cases):
    """A JUnit report: cases are (classname, name, outcome) with outcome passed, failed,
    error or skipped."""
    body = {"passed": "", "failed": '<failure message="no"/>', "error": '<error message="x"/>',
            "skipped": "<skipped/>"}
    rows = "".join(f'<testcase classname="{c}" name="{n}">{body[o]}</testcase>'
                   for c, n, o in cases)
    return f'<?xml version="1.0"?><testsuites><testsuite name="t">{rows}</testsuite></testsuites>'


class Tests(DriftTest):
    """check --tests: JUnit results matched to tagged tests by file and name."""

    def stamped(self, state=None, files=None):
        r = self.repo({"lib/session.py": "x = 1\n", "tests/test_session.py": SESSION_TEST,
                       **(files or {})},
                      state or {"specs": {"auth/session": spec("lib/**")}})
        self.assertEqual(r.drift("stamp", "--all").returncode, 0)
        return r

    def check(self, r, *args):
        out = r.drift("check", "--json", *args)
        self.assertIn(out.returncode, (0, 1), out.stderr)
        return out, {row["capability"]: row for row in json.loads(out.stdout)}

    # @scenario blueprint/sync: Failing tagged test
    def test_failing_tagged_test(self):
        r = self.stamped()
        r.write("report.xml", junit(("tests.test_session", "test_expired", "failed"),
                                    ("tests.test_session", "test_fresh", "passed")))
        out, rows = self.check(r, "--tests", "report.xml")
        self.assertEqual(out.returncode, 1)
        row = rows["auth/session"]
        self.assertEqual((row["status"], row["chance"], row["confidence"]),
                         ("deps-moved", 1.0, "high"))
        self.assertEqual(row["reasons"], [
            'test "test_expired" (tests/test_session.py:1) failed, claiming '
            '"Expired session redirects to login" → 1'])
        self.assertNotIn("changed", row)

    def test_without_tests_nothing_runs_or_counts(self):
        r = self.stamped()
        r.write("report.xml", junit(("tests.test_session", "test_expired", "failed")))
        out, rows = self.check(r)
        self.assertEqual((out.returncode, rows["auth/session"]["status"]), (0, "in-sync"))

    def test_passing_skipped_and_missing_tests_dont_move_it(self):
        r = self.stamped()
        for report in [junit(("tests.test_session", "test_expired", "passed")),
                       junit(("tests.test_session", "test_expired", "skipped")),
                       junit(("tests.test_other", "test_expired", "failed"),
                             ("tests.test_session", "test_expired_again", "failed")),
                       junit()]:
            with self.subTest(report=report):
                r.write("report.xml", report)
                out, rows = self.check(r, "--tests=report.xml")
                self.assertEqual((out.returncode, rows["auth/session"]["status"],
                                  rows["auth/session"]["chance"]), (0, "in-sync", 0.0))

    def test_error_counts_as_failing(self):
        r = self.stamped()
        r.write("report.xml", junit(("tests.test_session", "test_fresh", "error")))
        _, rows = self.check(r, "--tests", "report.xml")
        self.assertEqual(rows["auth/session"]["status"], "deps-moved")
        self.assertIn('"Fresh session stays"', rows["auth/session"]["reasons"][0])

    def test_code_moved_and_failing(self):
        r = self.stamped()
        r.write("lib/session.py", "x = 2\n")
        r.write("report.xml", junit(("tests.test_session", "test_expired", "failed")))
        _, rows = self.check(r, "--tests", "report.xml")
        row = rows["auth/session"]
        self.assertEqual((row["status"], row["chance"]), ("code-moved", 1.0))
        self.assertEqual(len(row["reasons"]), 2)

    def test_runners_report_shapes(self):
        """Vitest names the file and nests describe titles; jest-junit may add a file
        attribute; a single <testsuite> root; pytest parametrized; Go subtests."""
        ts = ("// @scenario auth/session: Expired session redirects to login\n"
              "it('rejects an expired token', () => {})\n")
        go = ("// @scenario auth/session: Expired session redirects to login\n"
              "func TestExpired(t *testing.T) {}\n")
        files = {"src/session.test.ts": ts, "pkg/auth/session_test.go": go}
        reports = {
            "vitest": '<testsuites><testsuite name="src/session.test.ts"><testcase '
                      'classname="src/session.test.ts" name="session &gt; rejects an expired '
                      'token"><failure/></testcase></testsuite></testsuites>',
            "jest": '<testsuite name="session"><testcase classname="session rejects an expired '
                    'token" name="session rejects an expired token" file="/ci/repo/src/session'
                    '.test.ts"><failure/></testcase></testsuite>',
            "pytest": '<testsuites><testsuite><testcase classname="tests.test_session" '
                      'name="test_expired[case-1]"><failure/></testcase></testsuite></testsuites>',
            "go": '<testsuites><testsuite name="example.com/shop/pkg/auth"><testcase '
                  'classname="example.com/shop/pkg/auth" name="TestExpired/past"><failure/>'
                  '</testcase></testsuite></testsuites>',
        }
        r = self.stamped(files=files)
        for runner, report in reports.items():
            with self.subTest(runner=runner):
                r.write("report.xml", report)
                _, rows = self.check(r, "--tests", "report.xml")
                self.assertEqual(rows["auth/session"]["status"], "deps-moved")

    def test_run(self):
        script = ("import pathlib, sys\nprint('ran the tests')\n"
                  "pathlib.Path('out').mkdir(exist_ok=True)\n"
                  "pathlib.Path('out/report.xml').write_text(sys.argv[1])\nsys.exit(1)\n")
        report = junit(("tests.test_session", "test_expired", "failed"))
        command = f"{sys.executable} run_tests.py '{report}'"
        r = self.stamped({"specs": {"auth/session": spec("lib/**")},
                          "tests": {"run": {"command": command, "report": "out/report.xml"}}},
                         {"run_tests.py": script})
        out, rows = self.check(r, "--tests", "run")
        self.assertEqual(rows["auth/session"]["status"], "deps-moved")
        self.assertIn("ran the tests", out.stderr)  # its output stays off stdout

    def test_run_that_writes_no_report(self):
        r = self.stamped({"specs": {"auth/session": spec("lib/**")},
                          "tests": {"run": {"command": "true", "report": "out/report.xml"}}})
        out = r.drift("check", "--tests", "run")
        self.assertEqual(out.returncode, 2)
        self.assertIn("tests.run didn't write its report: out/report.xml", out.stderr)
        r.write("out/report.xml", junit())  # a stale report from an earlier run
        out = r.drift("check", "--tests", "run")
        self.assertEqual(out.returncode, 2)

    # @scenario blueprint/sync: Run mode without a command
    def test_run_mode_without_a_command(self):
        r = self.stamped()
        out = r.drift("check", "--tests", "run")
        self.assertEqual(out.returncode, 2)
        self.assertIn("tests.run", out.stderr)
        self.assertEqual(out.stdout, "")

    def test_unusable_tests_argument(self):
        r = self.stamped({"specs": {"auth/session": spec("lib/**")},
                          "tests": {"run": "pytest"}})
        r.write("bad.xml", "<testsuites><testcase")
        for args, message in [(["--tests"], "--tests needs"),
                              (["--tests", "--json"], "--tests needs"),
                              (["--tests", "missing.xml"], "can't read the JUnit report"),
                              (["--tests", "bad.xml"], "can't read the JUnit report"),
                              (["--tests", "run"], "tests.run must be")]:
            with self.subTest(args=args):
                out = r.drift("check", *args)
                self.assertEqual(out.returncode, 2)
                self.assertIn(message, out.stderr)


    def test_absolute_report_not_written(self):
        missing = str(Path(r"/nonexistent-blueprint-dir") / "report.xml")
        r = self.stamped({"specs": {"auth/session": spec("lib/**")},
                          "tests": {"run": {"command": "true", "report": missing}}})
        out = r.drift("check", "--tests", "run")
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertIn(f"tests.run didn't write its report: {missing}", out.stderr)

    def test_longer_test_owns_its_failure(self):
        ts = ("// @scenario auth/session: Expired session redirects to login\n"
              "it('rejects', () => {})\nit('never rejects', () => {})\n")
        r = self.stamped(files={"src/session.test.ts": ts})
        r.write("report.xml", '<testsuite><testcase classname="src/session.test.ts" '
                              'name="session &gt; never rejects"><failure/></testcase>'
                              '<testcase classname="src/session.test.ts" '
                              'name="session &gt; rejects"/></testsuite>')
        _, rows = self.check(r, "--tests", "report.xml")
        self.assertEqual((rows["auth/session"]["status"], rows["auth/session"]["chance"]),
                         ("in-sync", 0.0))

    def test_same_relative_path_in_two_packages(self):
        ts = ("// @scenario auth/session: Expired session redirects to login\n"
              "it('signs in', () => {})\n")
        r = self.stamped(files={"apps/web/src/login.test.ts": ts,
                                "apps/admin/src/login.test.ts": "it('signs in', () => {})\n"})
        failing = ('<testsuite><testcase classname="{}" name="signs in"><failure/>'
                   '</testcase></testsuite>')
        for where, status in [("src/login.test.ts", "in-sync"),  # whose? can't tell
                              ("apps/admin/src/login.test.ts", "in-sync"),
                              ("/ci/repo/apps/web/src/login.test.ts", "deps-moved")]:
            with self.subTest(where=where):
                r.write("report.xml", failing.format(where))
                _, rows = self.check(r, "--tests", "report.xml")
                self.assertEqual(rows["auth/session"]["status"], status)

    def test_go_module_in_a_subfolder(self):
        go = ("// @scenario auth/session: Expired session redirects to login\n"
              "func TestExpired(t *testing.T) {}\n")
        r = self.stamped(files={"backend/go.mod": "module example.com/shop\n\ngo 1.22\n",
                                "backend/pkg/auth/session_test.go": go,
                                "backend/root_test.go": go.replace("Expired", "Root")})
        failing = ('<testsuites><testsuite name="{0}"><testcase classname="{0}" name="{1}">'
                   '<failure/></testcase></testsuite></testsuites>')
        for where, name, status in [("example.com/shop/pkg/auth", "TestExpired/past", "deps-moved"),
                                    ("example.com/shop", "TestRoot", "deps-moved"),
                                    ("example.com/shop/pkg/other", "TestExpired", "in-sync")]:
            with self.subTest(where=where):
                r.write("report.xml", failing.format(where, name))
                _, rows = self.check(r, "--tests", "report.xml")
                self.assertEqual(rows["auth/session"]["status"], status)

    def test_rust_cargo_report(self):
        rs = ("pub fn f() {}\n\n#[cfg(test)]\nmod tests {\n"
              "    // @scenario auth/session: Expired session redirects to login\n"
              "    #[test]\n    fn expired() {}\n}\n")
        r = self.stamped(files={"crates/shop/Cargo.toml": '[package]\nname = "shop-core"\n',
                                "crates/shop/src/session.rs": rs})
        failing = '<testsuite><testcase classname="{}" name="{}"><failure/></testcase></testsuite>'
        for where, name, status in [("shop_core", "session::tests::expired", "deps-moved"),
                                    ("shop-core", "session::tests::expired", "deps-moved"),
                                    ("shop_core", "other::tests::expired", "in-sync"),
                                    ("elsewhere", "session::tests::expired", "in-sync")]:
            with self.subTest(where=where, name=name):
                r.write("report.xml", failing.format(where, name))
                _, rows = self.check(r, "--tests", "report.xml")
                self.assertEqual(rows["auth/session"]["status"], status)


class Lockfile(DriftTest):
    """The lockfile signal on the TS workspace fixture, followed by file (no typescript)."""

    def workspace(self, scoring=None):
        r = fakerepo.FakeRepo()
        self.addCleanup(r.close)
        fakerepo.ts_workspace(r)
        if scoring:
            r.update(lambda s: s.setdefault("drift", {}).__setitem__("scoring", scoring))
        r.sync()
        return r

    def bump(self, r, version):
        lock = json.loads(r.read("package-lock.json"))
        lock["packages"]["node_modules/zod"]["version"] = version
        r.write("package-lock.json", json.dumps(lock))

    def rows(self, r):
        out = r.drift("check", "--json")
        self.assertIn(out.returncode, (0, 1), out.stderr)
        return {row["capability"]: row for row in json.loads(out.stdout)}

    # @scenario blueprint/sync: Dependency bumped
    def test_dependency_bumped(self):
        r = self.workspace()
        closure = json.loads(r.read(".blueprint/closure/web/login.json"))
        self.assertEqual(closure["locked"], {"zod": "3.22.0"})
        self.bump(r, "3.23.0")
        rows = self.rows(r)
        login = rows["web/login"]
        self.assertEqual((login["status"], login["chance"]), ("possibly-affected", 0.3))
        self.assertEqual(login["reasons"][0], "zod 3.22.0 → 3.23.0 in the lockfile → 0.3")
        self.assertEqual(rows["web/admin"]["status"], "in-sync")
        r.sync()
        self.assertEqual(self.rows(r)["web/login"]["status"], "in-sync")

    def test_weight_and_older_closures(self):
        r = self.workspace(scoring={"lockfileWeight": 0.6})
        self.bump(r, "4.0.0")
        login = self.rows(r)["web/login"]
        self.assertEqual((login["status"], login["chance"]), ("deps-moved", 0.6))
        # A closure stamped before versions were recorded: no lockfile signal.
        path = r.root / ".blueprint/closure/web/login.json"
        closure = json.loads(path.read_text())
        del closure["locked"]
        path.write_text(json.dumps(closure))
        self.assertEqual(self.rows(r)["web/login"]["status"], "in-sync")

    def test_dropped_from_the_lockfile(self):
        r = self.workspace()
        r.write("package-lock.json", json.dumps({"lockfileVersion": 3, "packages": {}}))
        self.assertEqual(self.rows(r)["web/login"]["reasons"][0],
                         "zod 3.22.0 → not locked in the lockfile → 0.3")


TYPESCRIPT = fakerepo.find_typescript()
NEEDS_TS = unittest.skipUnless(TYPESCRIPT, "no typescript to link: npm install -g typescript, "
                               "or set BLUEPRINT_TEST_TYPESCRIPT to a typescript package folder")


class Transitive(unittest.TestCase):
    """Import closures on the TS workspace fixture: login imports signToken from @company/core
    (no side effects, a barrel), button from @company/ui (side effects only in CSS, a barrel),
    @company/polyfills bare and zod; admin imports old from @company/legacy (no sideEffects)."""

    def workspace(self, typescript=TYPESCRIPT, scoring=None, files=None):
        r = fakerepo.FakeRepo()
        self.addCleanup(r.close)
        fakerepo.ts_workspace(r, typescript)
        for path, text in (files or {}).items():
            r.write(path, text)
        if scoring:
            r.update(lambda s: s.setdefault("drift", {}).__setitem__("scoring", scoring))
        r.sync()
        return r

    def replace(self, r, path, old, new):
        text = r.read(path)
        self.assertIn(old, text)
        r.write(path, text.replace(old, new))

    def check(self, r, env=None):
        out = subprocess.run([sys.executable, str(DRIFT), "check", "--json"], cwd=r.root,
                             capture_output=True, text=True, env=env or fakerepo.ENV)
        self.assertIn(out.returncode, (0, 1), out.stderr)
        return out, {row["capability"]: row for row in json.loads(out.stdout)}

    def closure(self, r, name):
        return json.loads(r.read(f".blueprint/closure/{name}.json"))

    # @scenario blueprint/sync: Closure recorded
    @NEEDS_TS
    def test_closure_recorded(self):
        r = self.workspace(files={"apps/web/src/admin.ts": (
            "import { signToken, hashPassword } from '@company/core';\n\n"
            "export const admin = () => hashPassword(signToken('a'));\n")})
        closure = self.closure(r, "web/admin")
        self.assertEqual(closure["mode"], "symbol")
        symbols = {(s["file"], s["symbol"]): s for s in closure["symbols"]}
        for key in [("packages/core/src/token.ts", "signToken"),
                    ("packages/core/src/password.ts", "hashPassword")]:
            self.assertEqual((symbols[key]["distance"], symbols[key]["via"]),
                             (1, ["@company/core"]))
            self.assertRegex(symbols[key]["hash"], r"^[0-9a-f]{12}$")
        # What signToken references comes along: a private helper in its file, and on.
        self.assertEqual(symbols[("packages/core/src/token.ts", "pad")]["distance"], 1)
        self.assertEqual(symbols[("packages/core/src/secret.ts", "secret")]["distance"], 2)
        self.assertEqual(symbols[("packages/core/src/salt.ts", "salt")]["distance"], 3)
        self.assertNotIn(("packages/core/src/token.ts", "verifyToken"), symbols)
        self.assertNotIn("packages/core/src/index.ts", closure["files"])  # a barrel: transparent
        login = self.closure(r, "web/login")
        self.assertEqual(login["external"], ["zod"])
        self.assertTrue(login["files"]["packages/polyfills/src/fill.ts"]["whole"])

    @NEEDS_TS
    def test_value_and_type_of_one_name_hash_together(self):
        # `const X` and `type X` are one node: its hash is both statements in source order,
        # whichever symbol (the value, the type, a property inside the value) reached it first.
        const = "export const Pad = { id: 'p', key: 'q' };"
        typ = "export type Pad = { id: string; key: string };"
        model = f"{const}\n{typ}\n"
        uses = ("import type { Pad } from './pad';\n\n"
                "export const describe = (p: Pad) => p.id;\n")
        factory = "import { Pad } from './pad';\n\nexport const make = () => Pad;\n"
        reader = "import { make } from './factory';\n\nexport const read = () => make().key;\n"
        expected = hashlib.sha256(f"{const}\n{typ}".encode()).hexdigest()[:12]
        orders = {
            "value first": ("import { Pad } from './pad';\nimport { describe } from './uses';\n\n"
                            "export const admin = () => describe(Pad) + Pad.key;\n"),
            "type first": ("import { describe } from './uses';\nimport { Pad } from './pad';\n\n"
                           "export const admin = () => Pad.key + describe(Pad);\n"),
            "property only": ("import { Pad } from './pad';\n\n"
                              "export const admin = () => Pad.key;\n"),
            # `key` is declared inside `const Pad`: reached before the name itself is.
            "property before name": ("import { read } from './reader';\n\n"
                                     "export const admin = () => read();\n"),
        }
        for label, admin in orders.items():
            with self.subTest(label):
                r = self.workspace(files={"apps/web/src/pad.ts": model,
                                          "apps/web/src/uses.ts": uses,
                                          "apps/web/src/factory.ts": factory,
                                          "apps/web/src/reader.ts": reader,
                                          "apps/web/src/admin.ts": admin})
                symbols = {(s["file"], s["symbol"]): s for s in self.closure(r, "web/admin")["symbols"]}
                self.assertEqual(symbols[("apps/web/src/pad.ts", "Pad")]["hash"], expected)

    # @scenario blueprint/sync: Ignored file left out
    @NEEDS_TS
    def test_ignored_file_left_out(self):
        # Generated, git-ignored types (another checkout won't have them) are not repo code.
        r = self.workspace(files={
            "apps/web/src/gen/.gitignore": "*\n",
            "apps/web/src/gen/types.d.ts": "export interface Api { run(): void }\n",
            "apps/web/src/admin.ts": (
                "import { old } from '@company/legacy';\n"
                "import type { Api } from './gen/types';\n\n"
                "export function admin(api: Api) {\n  api.run();\n  return old();\n}\n")})
        closure = self.closure(r, "web/admin")
        self.assertEqual(closure["mode"], "symbol")
        self.assertFalse([f for f in closure["files"] if "/gen/" in f])
        self.assertFalse([s for s in closure["symbols"] if "/gen/" in s["file"]])
        (r.root / "apps/web/src/gen/types.d.ts").unlink()  # a fresh CI checkout
        out, rows = self.check(r)
        self.assertEqual((out.returncode, rows["web/admin"]["status"]), (0, "in-sync"))

    # @scenario blueprint/sync: Imported symbol changed
    @NEEDS_TS
    def test_imported_symbol_changed(self):
        r = self.workspace(scoring={"packages": {"@company/core": {"weight": 1.0}}})
        self.replace(r, "packages/core/src/token.ts", "pad(user) + secret()", "secret() + pad(user)")
        out, rows = self.check(r)
        self.assertEqual(out.returncode, 1)
        row = rows["web/login"]
        self.assertEqual((row["status"], row["chance"], row["confidence"]),
                         ("deps-moved", 0.5, "medium"))
        self.assertEqual(row["reasons"], [
            "packages/core/src/token.ts signToken changed, 1 import away, "
            "via @company/core (weight 1) → 0.5",
            "confidence medium: no test results given"])
        self.assertNotIn("changed", row)
        self.assertEqual(rows["web/admin"]["status"], "in-sync")

    @NEEDS_TS
    def test_map_follows_imports_like_check(self):
        # graph.py once scored direct changes only, so the map missed imports-moved drift.
        r = self.workspace(scoring={"packages": {"@company/core": {"weight": 1.0}}})
        self.replace(r, "packages/core/src/token.ts", "pad(user) + secret()", "secret() + pad(user)")
        _, rows = self.check(r)
        out = subprocess.run([sys.executable, str(DRIFT.parent / "graph.py"), "--json"], cwd=r.root,
                             capture_output=True, text=True, env=fakerepo.ENV)
        self.assertEqual(out.returncode, 0, out.stderr)
        nodes = {n["id"]: n for n in json.loads(out.stdout)["nodes"]}
        self.assertEqual(nodes["web/login"]["status"], "deps-moved")
        for name, row in rows.items():
            self.assertEqual((nodes[name]["status"], nodes[name]["chance"], nodes[name]["confidence"],
                              nodes[name]["reasons"]),
                             (row["status"], row["chance"], row["confidence"], row["reasons"]))

    # @scenario blueprint/sync: Unused export changed
    @NEEDS_TS
    def test_unused_export_changed(self):
        r = self.workspace()
        self.replace(r, "packages/core/src/token.ts", "token.length > 8", "token.length > 9")
        self.replace(r, "packages/core/src/secret.ts", "unused = 1", "unused = 2")
        self.replace(r, "packages/ui/src/button.ts", "return '*'", "return '+'")
        out, rows = self.check(r)
        self.assertEqual(out.returncode, 0)
        self.assertEqual((rows["web/login"]["status"], rows["web/login"]["chance"]), ("in-sync", 0.0))

    # @scenario blueprint/sync: Distant change below threshold
    @NEEDS_TS
    def test_distant_change_below_threshold(self):
        r = self.workspace()
        self.replace(r, "packages/core/src/salt.ts", "'s'", "'t'")
        out, rows = self.check(r)
        self.assertEqual(out.returncode, 0)
        row = rows["web/login"]
        self.assertEqual((row["status"], row["chance"]), ("possibly-affected", 0.0625))
        self.assertEqual(row["reasons"][0], "packages/core/src/salt.ts salt changed, 3 imports "
                         "away, via @company/core (weight 0.5) → 0.06")
        self.assertIn("possibly-affected web/login  ■□□□□□□□□□ 0.0625 · medium",
                      r.drift("check").stdout)

    # @scenario blueprint/sync: Core package weighted up
    @NEEDS_TS
    def test_core_package_weighted_up(self):
        for scoring, chance in [(None, 0.25),
                                ({"packages": {"@company/core": {"weight": 1.0}}}, 0.5)]:
            with self.subTest(scoring=scoring):
                r = self.workspace(scoring=scoring)
                self.replace(r, "packages/core/src/token.ts", "padEnd(8)", "padEnd(9)")
                _, rows = self.check(r)
                # pad is private to token.ts: it counts through signToken, at the same distance.
                self.assertEqual(rows["web/login"]["chance"], chance)
                self.assertIn("token.ts pad changed, 1 import away", rows["web/login"]["reasons"][0])

    # @scenario blueprint/sync: Two weak signals
    @NEEDS_TS
    def test_two_weak_signals(self):
        r = self.workspace()
        self.replace(r, "packages/core/src/token.ts", "pad(user) + secret()", "secret() + pad(user)")
        self.replace(r, "packages/ui/src/button.ts", "`[${label}]`", "`(${label})`")
        _, rows = self.check(r)
        self.assertEqual((rows["web/login"]["status"], rows["web/login"]["chance"]),
                         ("possibly-affected", 0.4375))

    # @scenario blueprint/sync: Same diff, same number
    @NEEDS_TS
    def test_same_diff_same_number_through_imports(self):
        r = self.workspace()
        self.replace(r, "packages/core/src/salt.ts", "'s'", "'t'")
        self.replace(r, "packages/legacy/src/index.ts", "return 2", "return 3")
        self.assertEqual(self.check(r)[0].stdout, self.check(r)[0].stdout)

    # @scenario blueprint/sync: Side-effect import
    @NEEDS_TS
    def test_side_effect_import(self):
        r = self.workspace()
        self.replace(r, "packages/polyfills/src/fill.ts", "= true", "= 1")
        _, rows = self.check(r)
        self.assertEqual(rows["web/login"]["reasons"][0],
                         "packages/polyfills/src/fill.ts changed (whole file), 2 imports away, "
                         "via @company/polyfills (weight 0.5) → 0.13")

    # @scenario blueprint/sync: Field absent
    @NEEDS_TS
    def test_side_effects_field_absent(self):
        r = self.workspace()
        self.replace(r, "packages/legacy/src/index.ts", "return 2", "return 3")
        _, rows = self.check(r)
        self.assertEqual((rows["web/admin"]["status"], rows["web/admin"]["chance"]),
                         ("possibly-affected", 0.25))
        self.assertIn("legacy/src/index.ts changed (whole file)", rows["web/admin"]["reasons"][0])

    # @scenario blueprint/sync: Override
    @NEEDS_TS
    def test_side_effects_override(self):
        r = self.workspace(scoring={"packages": {"@company/legacy": {"sideEffects": False}}})
        self.replace(r, "packages/legacy/src/index.ts", "return 2", "return 3")
        _, rows = self.check(r)
        self.assertEqual(rows["web/admin"]["status"], "in-sync")
        self.replace(r, "packages/legacy/src/index.ts", "return 1", "return 0")
        _, rows = self.check(r)
        self.assertIn("legacy/src/index.ts old changed", rows["web/admin"]["reasons"][0])

    @NEEDS_TS
    def test_side_effects_glob_counts_the_file_whole(self):
        r = self.workspace(scoring={"packages": {"@company/ui": {"sideEffects": ["src/button.ts"]}}})
        self.replace(r, "packages/ui/src/button.ts", "return '*'", "return '+'")
        _, rows = self.check(r)
        self.assertIn("packages/ui/src/button.ts changed (whole file), 1 import away",
                      rows["web/login"]["reasons"][0])

    # @scenario blueprint/sync: Barrel re-export
    @NEEDS_TS
    def test_barrel_re_export(self):
        r = self.workspace()
        self.replace(r, "packages/ui/src/button.ts", "`[${label}]`", "`(${label})`")
        _, rows = self.check(r)
        self.assertEqual(rows["web/login"]["reasons"][0], "packages/ui/src/button.ts button "
                         "changed, 1 import away, via @company/ui (weight 0.5) → 0.25")

    # @scenario blueprint/sync: No test results
    @NEEDS_TS
    def test_no_test_results(self):
        r = self.workspace()
        _, rows = self.check(r)
        self.assertEqual(rows["web/login"]["confidence"], "medium")
        self.assertEqual(rows["web/login"]["reasons"], ["confidence medium: no test results given"])

    @NEEDS_TS
    def test_test_results_raise_confidence(self):
        r = self.workspace(files={"apps/web/src/login.test.ts": (
            "// @scenario web/login: Signs in\nit('signs in', () => {})\n")})
        for outcome, (confidence, reasons) in {
                "passed": ("high", []),
                "skipped": ("medium", ["confidence medium: no results for its tagged tests in "
                                       "the report"])}.items():
            with self.subTest(outcome=outcome):
                r.write("report.xml", junit(("apps/web/src/login.test.ts", "signs in", outcome)))
                out = subprocess.run([sys.executable, str(DRIFT), "check", "--json", "--tests",
                                      "report.xml"], cwd=r.root, capture_output=True, text=True,
                                     env=fakerepo.ENV)
                row = {x["capability"]: x for x in json.loads(out.stdout)}["web/login"]
                self.assertEqual((row["status"], row["confidence"], row["reasons"]),
                                 ("in-sync", confidence, reasons))

    @NEEDS_TS
    def test_max_depth_cuts_the_closure(self):
        r = self.workspace(scoring={"maxDepth": 2})
        symbols = {s["symbol"] for s in self.closure(r, "web/login")["symbols"]}
        self.assertIn("secret", symbols)
        self.assertNotIn("salt", symbols)

    # @scenario blueprint/sync: CI without node_modules
    @NEEDS_TS
    def test_ci_without_typescript(self):
        r = self.workspace()
        fakerepo.unlink_typescript(r)
        self.replace(r, "packages/core/src/secret.ts", "unused = 1", "unused = 2")
        out, rows = self.check(r)
        row = rows["web/login"]
        self.assertEqual((row["status"], row["confidence"]), ("possibly-affected", "low"))
        self.assertEqual(row["reasons"], [
            "packages/core/src/secret.ts changed, 2 imports away, via @company/core (weight 0.5)"
            " → 0.13",
            "confidence low: typescript not installed, so imports are followed by file"])
        self.assertEqual(out.stderr.count("notice:"), 1)
        self.assertIn("typescript not installed", out.stderr)
        self.assertFalse((r.root / "node_modules/typescript").exists())  # never installed

    def test_node_not_found(self):
        r = self.workspace(typescript=None)
        self.replace(r, "packages/core/src/salt.ts", "'s'", "'t'")
        # A PATH holding git alone: node often shares a folder with git, so none is dropped.
        bin_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, bin_dir)
        (bin_dir / "git").symlink_to(shutil.which("git"))
        env = dict(fakerepo.ENV, PATH=str(bin_dir))
        out = subprocess.run([sys.executable, str(DRIFT), "stamp", "--all"], cwd=r.root,
                             capture_output=True, text=True, env=env)
        self.assertIn("node not found", out.stderr)
        self.assertEqual(self.closure(r, "web/login")["why"], "node not found")

    @NEEDS_NODE
    # @scenario blueprint/sync: Closure one entry per line
    def test_closure_written_one_entry_per_line(self):
        # So a restamp diffs by the entries that moved, and a big closure stays short.
        r = self.workspace(typescript=None)
        text = r.read(".blueprint/closure/web/login.json")
        closure = json.loads(text)
        lines = text.splitlines()
        # Braces, mode, why, symbols ([]), and an opening and closing line for each of files,
        # external and locked, around one line per entry.
        self.assertEqual(len(lines), 11 + len(closure["files"]) + len(closure["external"])
                         + len(closure["locked"]))
        self.assertIn('  "symbols": [],', lines)
        for f, rec in closure["files"].items():
            self.assertIn(f"    {json.dumps(f)}: {json.dumps(rec)}",
                          [line.rstrip(",") for line in lines])
        self.assertEqual(sorted(closure["files"]), list(closure["files"]))
        r.sync()
        self.assertEqual(r.read(".blueprint/closure/web/login.json"), text)  # stable

    def test_stamp_without_typescript_follows_files(self):
        r = self.workspace(typescript=None)
        closure = self.closure(r, "web/login")
        self.assertEqual((closure["mode"], closure["why"], closure["symbols"]),
                         ("file", "typescript not installed", []))
        files = {f: (rec["distance"], rec["via"]) for f, rec in closure["files"].items()}
        # By file, a barrel is a hop of its own, and every file it re-exports comes along.
        self.assertEqual(files["packages/core/src/index.ts"], (1, ["@company/core"]))
        self.assertEqual(files["packages/core/src/token.ts"], (2, ["@company/core"]))
        self.assertEqual(files["packages/core/src/password.ts"], (2, ["@company/core"]))
        self.assertEqual(files["packages/core/src/salt.ts"], (4, ["@company/core"]))
        self.assertEqual(files["packages/polyfills/src/fill.ts"], (2, ["@company/polyfills"]))
        self.assertEqual(files["packages/ui/src/button.ts"], (2, ["@company/ui"]))
        self.assertEqual(closure["external"], ["zod"])
        self.assertTrue(all(rec["whole"] for rec in closure["files"].values()))
        self.replace(r, "packages/core/src/token.ts", "token.length > 8", "token.length > 9")
        _, rows = self.check(r)
        self.assertEqual(rows["web/login"]["reasons"], [
            "packages/core/src/token.ts changed, 2 imports away, via @company/core (weight 0.5)"
            " → 0.13",
            "confidence low: typescript not installed when stamped, so imports are followed by "
            "file"])

    def test_rename_moves_the_closure(self):
        r = self.workspace(typescript=None)
        r.checked_run("drift.py", "rename", "web/login", "web/signin")
        self.assertFalse((r.root / ".blueprint/closure/web/login.json").exists())
        self.assertEqual(self.closure(r, "web/signin")["mode"], "file")
        r.write(".blueprint/closure/web/taken.json", "{}")
        out = r.drift("rename", "web/admin", "web/taken")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("closure already exists", out.stderr)

    def narrowed(self, typescript):
        """web/app anchors login.ts and admin.ts; after its stamp, code both import moves, then
        its anchors narrow to login.ts and prune runs."""
        r = self.workspace(typescript=typescript)
        r.capability("web/app", ["apps/web/src/login.ts", "apps/web/src/admin.ts"])
        r.sync()
        self.replace(r, "packages/legacy/src/index.ts", "return 2", "return 3")
        self.replace(r, "packages/core/src/token.ts", "pad(user) + secret()", "secret() + pad(user)")
        r.update(lambda s: s["specs"]["web/app"].__setitem__("anchors", ["apps/web/src/login.ts"]))
        out = r.checked_run("drift.py", "prune", "web/app")
        self.assertIn("closure re-recorded", out.stdout)
        return r

    def test_prune_re_records_the_closure_keeping_what_moved(self):
        r = self.narrowed(None)
        closure = self.closure(r, "web/app")
        self.assertFalse(any(f.startswith("packages/legacy/") for f in closure["files"]))
        self.assertIn("packages/core/src/token.ts", closure["files"])
        row = self.check(r)[1]["web/app"]
        self.assertTrue(any(x.startswith("packages/core/src/token.ts changed") for x in row["reasons"]))
        self.assertFalse(any("legacy" in x for x in row["reasons"]))
        self.assertEqual(row["status"], "possibly-affected")

    @NEEDS_TS
    def test_prune_re_records_the_closure_by_symbol(self):
        r = self.narrowed(TYPESCRIPT)
        closure = self.closure(r, "web/app")
        self.assertEqual(closure["mode"], "symbol")
        self.assertFalse(any(s["file"].startswith("packages/legacy/") for s in closure["symbols"]))
        row = self.check(r)[1]["web/app"]
        self.assertEqual(row["reasons"][0], "packages/core/src/token.ts signToken changed, 1 "
                         "import away, via @company/core (weight 0.5) → 0.25")
        self.assertFalse(any("legacy" in x for x in row["reasons"]))

    def test_prune_leaves_an_unstamped_closure_alone(self):
        r = self.workspace(typescript=None)
        (r.root / ".blueprint/closure/web/admin.json").unlink()
        r.checked_run("drift.py", "prune", "web/admin")
        self.assertFalse((r.root / ".blueprint/closure/web/admin.json").exists())

    @NEEDS_TS
    def test_prune_keeps_a_closure_whose_mode_would_change(self):
        r = self.workspace()
        before = r.read(".blueprint/closure/web/login.json")
        self.assertEqual(json.loads(before)["mode"], "symbol")
        fakerepo.unlink_typescript(r)
        out = r.checked_run("drift.py", "prune", "web/login")
        self.assertNotIn("closure re-recorded", out.stdout)
        self.assertIn("closure kept as stamped: it was followed by symbol, and now would be by "
                      "file (typescript not installed)", out.stderr)
        self.assertEqual(r.read(".blueprint/closure/web/login.json"), before)

    def test_prune_removes_the_closure_when_no_ts_is_left(self):
        r = self.workspace(typescript=None, files={"apps/web/src/admin.css": "a {}\n",
                                                    "apps/web/src/login.css": "a {}\n"})
        for name in ("web/admin", "web/login"):
            css = f"apps/web/src/{name.split('/')[1]}.css"
            r.update(lambda s: s["specs"][name].__setitem__("anchors", [css]))
            out = r.checked_run("drift.py", "prune", name)
            self.assertIn("closure removed (no TS/JS files left)", out.stdout)
        self.assertFalse((r.root / ".blueprint/closure/web").exists())

    def test_restamp_clears_it(self):
        r = self.workspace(typescript=None)
        self.replace(r, "packages/legacy/src/index.ts", "return 2", "return 3")
        self.assertEqual(self.check(r)[1]["web/admin"]["status"], "possibly-affected")
        r.sync()
        self.assertEqual(self.check(r)[1]["web/admin"]["status"], "in-sync")


class Combine(unittest.TestCase):
    """The formula itself, imported (drift.py only needs to run inside a git repo)."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(DRIFT.parent))
        import drift
        cls.drift = drift

    def test_any_of_these(self):
        self.assertEqual(self.drift.combine([0.25, 0.25]), 0.4375)
        self.assertEqual(self.drift.combine([1.0, 0.3]), 1.0)
        self.assertEqual(self.drift.combine([]), 0.0)

    # @scenario blueprint/sync: Meter in the terminal
    def test_meter(self):
        meter = self.drift.meter
        self.assertEqual(meter(0.5, "medium"), "■■■■■□□□□□ 0.5 · medium")
        self.assertEqual(meter(1.0, "high"), "■■■■■■■■■■ 1 · high")
        self.assertEqual(meter(0.0625, "low"), "■□□□□□□□□□ 0.0625 · low")  # never empty above 0
        self.assertEqual(meter(0.25, "medium"), "■■■□□□□□□□ 0.25 · medium")  # half up
        self.assertEqual(meter(0.5, "low", color=True), "\033[31m■■■■■\033[0m□□□□□ 0.5 · low")
        self.assertEqual(meter(0.5, "high", color=True), "\033[32m■■■■■\033[0m□□□□□ 0.5 · high")

    def test_npm_lockfiles(self):
        v3 = {"lockfileVersion": 3, "packages": {
            "": {"name": "app"}, "node_modules/zod": {"version": "3.22.0"},
            "node_modules/@scope/x": {"version": "1.0.0"},
            "node_modules/a/node_modules/zod": {"version": "3.21.0"},
            "node_modules/@company/core": {"resolved": "packages/core", "link": True}}}
        self.assertEqual(sorted(self.drift.npm_versions(json.dumps(v3))), [
            ("@scope/x", "1.0.0"), ("zod", "3.21.0"), ("zod", "3.22.0")])
        v1 = {"lockfileVersion": 1, "dependencies": {"zod": {"version": "3.0.0", "dependencies": {
            "tslib": {"version": "2.0.0"}}}}}
        self.assertEqual(sorted(self.drift.npm_versions(json.dumps(v1))), [
            ("tslib", "2.0.0"), ("zod", "3.0.0")])
        self.assertEqual(list(self.drift.npm_versions("{not json")), [])

    def test_pnpm_lockfiles(self):
        v9 = ("lockfileVersion: '9.0'\n\nimporters:\n  .:\n    dependencies:\n      zod:\n"
              "        specifier: ^3.22.0\n        version: 3.22.0\n\npackages:\n\n"
              "  zod@3.22.0:\n    resolution: {integrity: sha512-x}\n\n"
              "  '@scope/x@1.0.0(react@18.2.0)':\n    resolution: {integrity: sha512-y}\n\n"
              "snapshots:\n\n  zod@3.22.0: {}\n")
        self.assertEqual(sorted(self.drift.pnpm_versions(v9)), [
            ("@scope/x", "1.0.0"), ("zod", "3.22.0")])
        v6 = "lockfileVersion: '6.0'\n\npackages:\n\n  /zod@3.22.0:\n    dev: false\n"
        self.assertEqual(list(self.drift.pnpm_versions(v6)), [("zod", "3.22.0")])
        v5 = ("lockfileVersion: 5.4\n\npackages:\n\n  /zod/3.22.0:\n    dev: false\n"
              "  /@scope/x/1.0.0_react@18.2.0:\n    dev: false\n")
        self.assertEqual(list(self.drift.pnpm_versions(v5)), [
            ("zod", "3.22.0"), ("@scope/x", "1.0.0")])

    def test_yarn_lockfiles(self):
        classic = ('# yarn lockfile v1\n\n\n"@scope/x@^1.0.0", "@scope/x@^1.0.1":\n'
                   '  version "1.0.2"\n  resolved "https://r/x.tgz"\n  dependencies:\n'
                   '    version "9"\n\nzod@^3.22.0:\n  version "3.22.4"\n')
        self.assertEqual(list(self.drift.yarn_versions(classic)), [
            ("@scope/x", "1.0.2"), ("zod", "3.22.4")])
        berry = ('__metadata:\n  version: 6\n\n"zod@npm:^3.22.0":\n  version: 3.22.4\n'
                 '  resolution: "zod@npm:3.22.4"\n')
        self.assertEqual(list(self.drift.yarn_versions(berry)), [("zod", "3.22.4")])

    def test_report_locators(self):
        locates = self.drift.locates
        self.assertTrue(locates("tests.test_session", "tests/test_session.py"))
        self.assertTrue(locates("test_session.TestLogin", "tests/test_session.py"))
        self.assertTrue(locates("/ci/repo/src/a.test.ts", "src/a.test.ts"))
        self.assertTrue(locates("example.com/shop/pkg/auth", "pkg/auth/x_test.go"))
        self.assertFalse(locates("tests.test_other", "tests/test_session.py"))
        self.assertFalse(locates("", "a.py"))

    def test_report_names(self):
        match = self.drift.names_match
        self.assertTrue(match("session > rejects", "rejects"))
        self.assertTrue(match("session > rejects", "session"))
        self.assertTrue(match("test_x[1-2]", "test_x"))
        self.assertTrue(match("TestX/sub", "TestX"))
        self.assertFalse(match("test_xy", "test_x"))
        self.assertFalse(match("rejects later", "rejects"))

    def test_longer_declared_test_owns_the_case(self):
        claims = self.drift.claims
        self.assertFalse(claims("never rejects", "rejects", {"rejects", "never rejects"}))
        self.assertTrue(claims("never rejects", "rejects", {"rejects"}))  # jest: "describe test"
        self.assertTrue(claims("session > rejects", "session", {"session", "rejects"}))
        self.assertTrue(claims("tests::expired", "expired", {"expired"}))

    def test_cfg_test_is_not_a_test_attribute(self):
        text = ("// @scenario a/b: X\n#[cfg_attr(test, derive(Debug))]\nfn helper() {}\n"
                "// @scenario a/b: Y\n#[rstest]\nfn cases() {}\n")
        self.assertEqual([t[3] for t in self.drift.scan_tags(text)], [None, "cases"])
        self.assertEqual(self.drift.declared_tests(text), {"cases"})

    def test_node_builtins_are_no_package(self):
        resolve = self.drift.resolve_import
        self.assertIsNone(resolve("events", "src/a.ts", set(), {}, {}))
        self.assertEqual(resolve("zod", "src/a.ts", set(), {}, {}), ("external", "zod"))
        settings = self.drift.scoring({})
        old = {"mode": "file", "locked": {"events": "3.3.0", "zod": "3.22.0"}}
        self.assertEqual([r for _, r in self.drift.lock_signals(
            old, {"events": "3.3.1", "zod": "3.22.0"}, settings)], [])
        symbol = dict(old, mode="symbol")  # resolved by typescript into node_modules/events
        self.assertEqual(len(self.drift.lock_signals(symbol, {"events": "3.3.1", "zod": "3.22.0"},
                                                     settings)), 1)

    def test_defaults(self):
        self.assertEqual(self.drift.scoring({}), {
            "decay": 0.5, "packageWeight": 0.5, "lockfileWeight": 0.3, "threshold": 0.5,
            "maxDepth": 6, "packages": {}})


if __name__ == "__main__":
    unittest.main()
