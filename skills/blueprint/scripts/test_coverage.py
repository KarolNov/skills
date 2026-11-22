#!/usr/bin/env python3
"""Tests for coverage.py: each runs the script in a throwaway git repo.

    python3 skills/blueprint/scripts/test_coverage.py

Fixture tags are built with tag() so this file's own lines never read as tags.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

COVERAGE = Path(__file__).resolve().parent / "coverage.py"
# Ignore the developer's git config (signing, hooks, templates) in the throwaway repos.
ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
AT = "@" + "scenario"


def tag(comment, ref, close=""):
    return f"{comment} {AT} {ref}{close}\n"


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

    def run(self, *args):
        return subprocess.run([sys.executable, str(COVERAGE), *args], cwd=self.root,
                              capture_output=True, text=True, env=ENV)

    def data(self, *args):
        out = self.run("--json", *args)
        assert out.returncode in (0, 1), out.stderr
        return json.loads(out.stdout)

    def close(self):
        self._tmp.cleanup()


SESSION_MD = """## Purpose

Keeps users signed in.

## Requirements

### Requirement: Session expiry

A session SHALL expire after an hour.

- **Scenario: Expired session redirects to login**
  - **GIVEN** a session older than an hour
  - **WHEN** the user opens a page
  - **THEN** they land on the login page
- **Scenario: Fresh session stays**
  - **WHEN** the session is new
  - **THEN** the page opens

### Requirement: Logout

Logout SHALL end the session.

- **Scenario: Logout clears cookie**
  - **WHEN** the user logs out
  - **THEN** the cookie is gone
- **Scenario: Logout redirects home**
  - **WHEN** the user logs out
  - **THEN** they land on the home page
"""

KINDS = {"contract": ["pact/**"], "unit": ["**/*.test.ts", "**/*.rs", "tests/**"],
         "e2e": ["e2e/**"]}


def state(kinds=KINDS, **specs):
    specs = specs or {"auth/session": {"ref": "page", "anchors": ["src/**"]}}
    out = {"version": 2, "specs": specs}
    if kinds is not None:
        out["tests"] = {"kinds": kinds}
    return out


def scenarios(data, cap="auth/session"):
    c = next(c for c in data["capabilities"] if c["name"] == cap)
    return {s["name"]: s for r in c["requirements"] for s in r["scenarios"]}


class TestCase(unittest.TestCase):
    def repo(self, files, st=None):
        files = {".blueprint/baseline/auth/session.md": SESSION_MD, **files}
        r = Repo(files, state() if st is None else st)
        self.addCleanup(r.close)
        return r


class ScenarioTags(TestCase):
    def test_tag_in_a_rust_test(self):
        # @scenario blueprint/coverage: Tag in a Rust test
        r = self.repo({"src/session.rs": "mod t {\n"
                       + tag("    //", "auth/session: Expired session redirects to login")
                       + "    #[test]\n    fn expired() {}\n}\n"})
        claims = scenarios(r.data())["Expired session redirects to login"]["claims"]
        self.assertEqual(claims, [{"file": "src/session.rs", "line": 2, "kind": "unit"}])

    def test_tag_in_a_python_test(self):
        # @scenario blueprint/coverage: Tag in a Python test
        r = self.repo({"tests/test_session.py":
                       tag("#", "auth/session: Expired session redirects to login")
                       + "def test_expired():\n    pass\n"})
        claims = scenarios(r.data())["Expired session redirects to login"]["claims"]
        self.assertEqual(claims, [{"file": "tests/test_session.py", "line": 1, "kind": "unit"}])

    def test_every_comment_style_and_loose_matching(self):
        r = self.repo({"tests/a.sql": tag("--", "auth/session:   expired SESSION  redirects to login"),
                       "tests/b.ts": tag("/*", "auth/session: Fresh session stays", " */")
                       + " /**\n" + tag("  *", "auth/session: Logout clears cookie") + "  */\n",
                       "tests/c.html": tag("<!--", "auth/session: Logout redirects home", " -->")})
        sc = scenarios(r.data())
        self.assertEqual(sc["Expired session redirects to login"]["claims"][0]["file"], "tests/a.sql")
        self.assertEqual(sc["Fresh session stays"]["claims"][0]["file"], "tests/b.ts")
        self.assertEqual(sc["Logout clears cookie"]["claims"][0]["line"], 3)
        self.assertEqual(sc["Logout redirects home"]["claims"][0]["file"], "tests/c.html")
        self.assertEqual(r.data()["orphans"], [])

    def test_several_tags_and_many_tests(self):
        both = (tag("//", "auth/session: Logout clears cookie")
                + tag("//", "auth/session: Logout redirects home") + "it('logs out')\n")
        r = self.repo({"src/a.test.ts": both, "e2e/logout.spec.ts": both})
        sc = scenarios(r.data())
        self.assertEqual([c["kind"] for c in sc["Logout clears cookie"]["claims"]], ["e2e", "unit"])
        self.assertEqual(len(sc["Logout redirects home"]["claims"]), 2)

    def test_tag_mid_line_or_in_a_string_is_not_a_tag(self):
        r = self.repo({"tests/x.py": f'x = "{AT} auth/session: Logout clears cookie"\n'
                       f"y = 1  # see {AT} auth/session: Fresh session stays\n"})
        self.assertEqual(r.data()["summary"]["claimed"], 0)

    def test_blueprint_folder_skipped_and_untracked_files_scanned(self):
        r = self.repo({".blueprint/notes.md": tag("<!--", "auth/session: Logout clears cookie", " -->")})
        r.write("tests/new.py", tag("#", "auth/session: Fresh session stays"))
        sc = scenarios(r.data())
        self.assertEqual(sc["Logout clears cookie"]["claims"], [])
        self.assertEqual(sc["Fresh session stays"]["claims"][0]["file"], "tests/new.py")


class TestKinds(TestCase):
    def test_custom_kind(self):
        # @scenario blueprint/coverage: Custom kind
        r = self.repo({"pact/user.test.ts": tag("//", "auth/session: Fresh session stays")})
        self.assertEqual(scenarios(r.data())["Fresh session stays"]["claims"][0]["kind"], "contract")
        self.assertEqual(r.data()["kinds"], ["contract", "unit", "e2e"])

    def test_kinds_not_configured(self):
        # @scenario blueprint/coverage: Kinds not configured
        r = self.repo({"tests/a.py": tag("#", "auth/session: Fresh session stays")},
                      state(kinds=None))
        out = r.run()
        self.assertEqual(out.returncode, 2)
        self.assertEqual(out.stdout, "")
        self.assertIn("tests.kinds is required", out.stderr)
        self.assertEqual(r.run("--json").stdout, "")

    def test_malformed_kinds(self):
        r = self.repo({}, state(kinds={"unit": "tests/**"}))
        out = r.run()
        self.assertEqual(out.returncode, 2)
        self.assertIn("tests.kinds must map", out.stderr)

    def test_tag_outside_every_kind(self):
        # @scenario blueprint/coverage: Tag outside every kind
        r = self.repo({"src/session.go": tag("//", "auth/session: Fresh session stays")},
                      state(kinds={"e2e": ["e2e/**"]}))
        data = r.data()
        self.assertEqual(scenarios(data)["Fresh session stays"]["claims"],
                         [{"file": "src/session.go", "line": 1, "kind": None}])
        self.assertEqual(data["summary"]["claimed"], 1)
        self.assertEqual([u["file"] for u in data["unclassified"]], ["src/session.go"])
        self.assertIn("Unclassified tags", r.run().stdout)


class Report(TestCase):
    def test_untested_requirement(self):
        # @scenario blueprint/coverage: Untested requirement
        r = self.repo({"tests/a.py": tag("#", "auth/session: Fresh session stays")})
        out = r.run()
        self.assertEqual(out.returncode, 0)
        logout = out.stdout.split("  Logout\n")[1]
        self.assertIn("uncovered  Logout clears cookie", logout)
        self.assertIn("uncovered  Logout redirects home", logout)
        self.assertIn("claimed    Fresh session stays", out.stdout)
        self.assertIn("tests/a.py:1 (unit)", out.stdout)
        self.assertIn("1 of 4 scenarios claimed (contract 0, unit 1, e2e 0)", out.stdout)

    def test_says_claimed_never_verified(self):
        r = self.repo({"tests/a.py": tag("#", "auth/session: Fresh session stays")})
        for out in (r.run().stdout, r.run("--json").stdout):
            self.assertNotIn("verified", out.lower())
            self.assertNotIn("passing", out.lower())

    def test_json_summary_per_kind(self):
        r = self.repo({"tests/a.py": tag("#", "auth/session: Fresh session stays"),
                       "e2e/a.ts": tag("//", "auth/session: Fresh session stays")
                       + tag("//", "auth/session: Logout clears cookie")})
        self.assertEqual(r.data()["summary"],
                         {"claimed": 2, "total": 4, "byKind": {"contract": 0, "unit": 1, "e2e": 2}})

    def test_capability_filter(self):
        other = "## Purpose\n\nX.\n\n## Requirements\n\n### Requirement: Y\n\nY.\n\n- **Scenario: Z**\n  - **THEN** z\n"
        st = state(**{"auth/session": {"ref": "p", "anchors": []}, "billing": {"ref": "p", "anchors": []}})
        r = self.repo({".blueprint/baseline/billing.md": other,
                       "tests/a.py": tag("#", "billing: Nope")}, st)
        self.assertEqual([c["name"] for c in r.data()["capabilities"]], ["auth/session", "billing"])
        only = r.data("auth/session")
        self.assertEqual([c["name"] for c in only["capabilities"]], ["auth/session"])
        self.assertEqual(only["summary"]["total"], 4)
        self.assertEqual(only["orphans"], [])
        self.assertEqual(len(r.data("billing")["orphans"]), 1)
        out = r.run("auth/sesion")
        self.assertEqual(out.returncode, 2)
        self.assertIn("did you mean auth/session", out.stderr)

    def test_writes_nothing(self):
        r = self.repo({"tests/a.py": tag("#", "auth/session: Fresh session stays")})
        r.run("--strict=all")
        status = subprocess.run(["git", "-C", str(r.root), "status", "--porcelain"],
                                capture_output=True, text=True, env=ENV).stdout
        self.assertEqual(status, "")


class Problems(TestCase):
    def test_scenario_reworded(self):
        # @scenario blueprint/coverage: Scenario reworded
        r = self.repo({"tests/a.py": "\n" + tag("#", "auth/session: Expired session redirects")})
        [o] = r.data()["orphans"]
        self.assertEqual((o["file"], o["line"], o["reason"]), ("tests/a.py", 2, "unknown scenario"))
        self.assertEqual(o["suggestion"], "Expired session redirects to login")
        self.assertIn("nearest: Expired session redirects to login", r.run().stdout)

    def test_unknown_capability_and_malformed_tag(self):
        r = self.repo({"tests/a.py": tag("#", "auth/sessions: Fresh session stays")
                       + tag("#", "no colon here")})
        orphans = r.data()["orphans"]
        self.assertEqual([(o["reason"], o["suggestion"]) for o in orphans],
                         [("unknown capability", "auth/session"), ("malformed tag", None)])

    def test_no_spec_yet(self):
        st = state(**{"auth/session": {"ref": "p", "anchors": []}, "billing": {"ref": None, "anchors": []}})
        r = self.repo({"tests/a.py": tag("#", "billing: Charges card")}, st)
        data = r.data()
        self.assertEqual(data["orphans"], [])
        self.assertEqual([t["capability"] for t in data["noSpec"]], ["billing"])
        self.assertNotIn("billing", [c["name"] for c in data["capabilities"]])
        self.assertEqual(r.run("--strict").returncode, 0)

    def test_same_name_twice(self):
        # @scenario blueprint/coverage: Same name twice
        dup = SESSION_MD.replace("Logout redirects home", "Expired session redirects to login")
        r = self.repo({".blueprint/baseline/auth/session.md": dup})
        [d] = r.data()["duplicates"]
        self.assertEqual(d["requirements"], ["Session expiry", "Logout"])
        self.assertIn("(in Session expiry and Logout)", r.run().stdout)
        self.assertEqual(r.run("--strict").returncode, 1)


class Gate(TestCase):
    def test_partly_tagged_repo(self):
        # @scenario blueprint/coverage: Partly tagged repo
        r = self.repo({"tests/a.py": tag("#", "auth/session: Fresh session stays")})
        self.assertEqual(r.run("--strict").returncode, 0)
        self.assertEqual(r.run("--strict=all").returncode, 1)
        self.assertEqual(r.run().returncode, 0)

    def test_strict_fails_on_orphans_and_unclassified(self):
        r = self.repo({"tests/a.py": tag("#", "auth/session: Gone")})
        self.assertEqual(r.run("--strict").returncode, 1)
        r = self.repo({"src/a.go": tag("//", "auth/session: Fresh session stays")},
                      state(kinds={"e2e": ["e2e/**"]}))
        self.assertEqual(r.run("--strict").returncode, 1)

    def test_all_covered(self):
        tags = "".join(tag("#", f"auth/session: {n}") for n in (
            "Expired session redirects to login", "Fresh session stays",
            "Logout clears cookie", "Logout redirects home"))
        r = self.repo({"tests/a.py": tags})
        self.assertEqual(r.run("--strict=all").returncode, 0)

    def test_bad_options(self):
        r = self.repo({})
        self.assertEqual(r.run("--strict=some").returncode, 2)
        self.assertEqual(r.run("--nope").returncode, 2)
        self.assertEqual(r.run("--delta").returncode, 2)
        self.assertEqual(r.run("--delta", "missing.md").returncode, 2)
        out = r.run("--delta", "--json")
        self.assertEqual(out.returncode, 2)
        self.assertIn("--delta needs a file", out.stderr)

    def test_filter_keeps_typos_aimed_at_the_capability(self):
        r = self.repo({"tests/a.py": tag("#", "auth/sessions: Fresh session stays")})
        self.assertEqual(r.run("auth/session", "--strict").returncode, 1)

    def test_spec_without_baseline_is_a_setup_error(self):
        st = state(**{"auth/session": {"ref": "p", "anchors": []}, "billing": {"ref": "p", "anchors": []}})
        out = self.repo({"tests/a.py": tag("#", "billing: Wrong")}, st).run("--strict")
        self.assertEqual(out.returncode, 2)
        self.assertIn("sync it first", out.stderr)

    def test_bom_form_feed_and_backticked_capability(self):
        r = self.repo({})
        (r.root / "tests").mkdir()
        (r.root / "tests/a.py").write_bytes(
            b"\xef\xbb\xbf" + tag("#", "auth/session: Fresh session stays").encode()
            + b"\x0c\n" + tag("#", "`auth/session`: Logout clears cookie").encode())
        data = r.data()
        sc = scenarios(data)
        self.assertEqual(sc["Fresh session stays"]["claims"][0]["line"], 1)
        self.assertEqual(sc["Logout clears cookie"]["claims"][0]["line"], 3)
        self.assertEqual(data["orphans"], [])


BRIEF = """# A brief

## Spec delta

### auth/session · ADDED

#### Requirement: Remember me

A session MAY last a month.

- **Scenario: Remembered session lasts a month**
  - **THEN** it lasts

### auth/session · MODIFIED

#### Requirement: Session expiry

A session SHALL expire after a day.

- **Scenario: Expired session redirects to login**
  - **THEN** login
- **Scenario: Day-old session expires**
  - **THEN** gone

### auth/session · REMOVED

- **Logout**: replaced by sign-out

### billing · ADDED

**Purpose**: Charges.

#### Requirement: Charge

- <b>Scenario: Charges card</b>
  - <b>THEN</b> charged

## Tasks

- [ ] 1. build
"""


class Delta(TestCase):
    def test_new_scenario_during_apply(self):
        # @scenario blueprint/coverage: New scenario during apply
        r = self.repo({"BRIEF.md": BRIEF,
                       "tests/a.py": tag("#", "auth/session: Remembered session lasts a month")})
        self.assertEqual(r.data()["orphans"][0]["reason"], "unknown scenario")
        data = r.data("--delta", "BRIEF.md")
        self.assertEqual(data["orphans"], [])
        sc = scenarios(data)
        self.assertTrue(sc["Remembered session lasts a month"]["pending"])
        self.assertEqual(len(sc["Remembered session lasts a month"]["claims"]), 1)
        self.assertIn("(pending)", r.run("--delta", "BRIEF.md").stdout)

    def test_modified_replaces_block_and_removed_is_gone(self):
        r = self.repo({"BRIEF.md": BRIEF,
                       "tests/a.py": tag("#", "auth/session: Fresh session stays")
                       + tag("#", "auth/session: Logout clears cookie")})
        data = r.data("--delta", "BRIEF.md")
        sc = scenarios(data)
        self.assertEqual(set(sc), {"Expired session redirects to login", "Day-old session expires",
                                   "Remembered session lasts a month"})
        self.assertFalse(sc["Expired session redirects to login"]["pending"])
        self.assertTrue(sc["Day-old session expires"]["pending"])
        self.assertEqual(sorted(o["scenario"] for o in data["orphans"]),
                         ["Fresh session stays", "Logout clears cookie"])

    def test_new_capability_from_delta_in_notion_markup(self):
        r = self.repo({"BRIEF.md": BRIEF, "tests/a.py": tag("#", "billing: charges card")})
        self.assertEqual(r.data()["orphans"][0]["reason"], "unknown capability")
        data = r.data("--delta", "BRIEF.md")
        self.assertEqual(data["orphans"], [])
        self.assertTrue(scenarios(data, "billing")["Charges card"]["pending"])

    def test_delta_with_notion_escapes_and_entities(self):
        brief = ("## Spec delta\n\n### auth/session · ADDED\n\n#### Requirement: Extra\n\n"
                 "- <b>Scenario: Day\\-old &amp; stale session expires</b>\n  - <b>THEN</b> gone\n")
        r = self.repo({"BRIEF.md": brief,
                       "tests/a.py": tag("#", "auth/session: Day-old & stale session expires")})
        data = r.data("--delta", "BRIEF.md")
        self.assertEqual(data["orphans"], [])

    def test_delta_without_spec_delta_is_an_error(self):
        r = self.repo({"BRIEF.md": "# Just a note\n"})
        out = r.run("--delta", "BRIEF.md")
        self.assertEqual(out.returncode, 2)
        self.assertIn("no Spec delta", out.stderr)

    def test_renamed_requirement_keeps_scenarios(self):
        brief = "## Spec delta\n\n### auth/session · RENAMED\n\n- Logout → Sign out\n"
        r = self.repo({"BRIEF.md": brief})
        names = [q["name"] for q in r.data("--delta", "BRIEF.md")["capabilities"][0]["requirements"]]
        self.assertEqual(names, ["Session expiry", "Sign out"])


if __name__ == "__main__":
    unittest.main()
