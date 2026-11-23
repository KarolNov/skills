#!/usr/bin/env python3
"""End-to-end tests for the drift-guard workflow template /blueprint-setup copies into a repo.

    python3 skills/blueprint/scripts/e2e/test_drift_workflow.py

Each test builds a FakeRepo with `.blueprint/drift.py` in it, as setup leaves a repo, and runs
the workflow's own steps, read from skills/blueprint-setup/templates/blueprint-drift.yml: every
`run:` script goes through bash the way a GitHub-hosted runner runs it, with `${{ }}` filled in,
`if:` conditions evaluated and $GITHUB_OUTPUT read back into steps.<id>.outputs. A fake `gh` on
PATH keeps the PR's comments in a JSON file and records each call; it answers comment writes
with a 403 when the test plays a fork PR. The test then reads the annotations, the comments and
whether the job passed.

Needs bash, jq (gh's --jq is handed to it) and PyYAML to read the workflow; skips without them.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fakerepo import ENV, SCRIPTS, FakeRepo

try:
    import yaml
except ImportError:  # only this test needs it; nothing in the skill does
    yaml = None

WORKFLOW = SCRIPTS.parent.parent / "blueprint-setup/templates/blueprint-drift.yml"
MARKER = "<!-- blueprint-drift -->"
REPO, PR = "acme/shop", "7"

FAKE_GH = r'''
import json, os, re, subprocess, sys

state_path = os.environ["FAKE_GH_STATE"]
state = json.load(open(state_path))
args = sys.argv[1:]
state["calls"].append(args)


def save():
    json.dump(state, open(state_path, "w"), indent=2)


def opt(name):
    return args[args.index(name) + 1] if name in args else None


assert args[0] == "api", args
method = opt("-X") or "GET"
endpoint = next(a for a in args[1:] if a.startswith("repos/"))
body = opt("-F")
if body is not None:
    key, _, src = body.partition("=")
    assert key == "body" and src.startswith("@"), body
    body = open(src[1:]).read()
m_list = re.fullmatch(r"repos/[^/]+/[^/]+/issues/(\d+)/comments", endpoint)
m_one = re.fullmatch(r"repos/[^/]+/[^/]+/issues/comments/(\d+)", endpoint)
if method != "GET" and os.environ.get("FAKE_GH_FORK") == "1":
    save()
    sys.exit("gh: Resource not accessible by integration (HTTP 403)")
if method == "GET" and m_list:
    out = json.dumps([c for c in state["comments"] if c["pr"] == m_list.group(1)])
    if opt("--jq"):
        out = subprocess.run(["jq", "-r", opt("--jq")], input=out, capture_output=True,
                             text=True, check=True).stdout
    sys.stdout.write(out)
elif method == "POST" and m_list:
    state["next"] += 1
    c = {"id": state["next"], "pr": m_list.group(1), "body": body}
    state["comments"].append(c)
    print(json.dumps(c))
elif method == "PATCH" and m_one:
    c = next((c for c in state["comments"] if c["id"] == int(m_one.group(1))), None)
    if c is None:
        save()
        sys.exit("gh: Not Found (HTTP 404)")
    c["body"] = body
    print(json.dumps(c))
else:
    save()
    sys.exit(f"fake gh: unexpected {method} {endpoint}")
save()
'''


NAME = re.compile(r"[A-Za-z_][\w-]*(?:\.[A-Za-z_][\w-]*)*")


def lookup(tok, ctx):
    """A dotted context name. Anything else (||, !, always(), ...) raises: this simulator can't
    evaluate it, and guessing would test something other than what GitHub runs."""
    if not NAME.fullmatch(tok):
        raise ValueError(f"workflow expression the test can't evaluate: {tok!r}")
    cur = ctx
    for part in tok.split("."):
        cur = cur.get(part, "") if isinstance(cur, dict) else ""
    return cur


def expression(text, ctx):
    """A GitHub expression of the kind the template uses: dotted names, 'strings', == != &&.
    Status functions (always(), failure()) raise, so steps after a failure are always skipped."""
    def value(tok):
        tok = tok.strip()
        if re.fullmatch(r"'[^']*'", tok):
            return tok[1:-1]
        return lookup(tok, ctx)

    result = True
    for clause in text.split("&&"):
        m = re.fullmatch(r"\s*(.+?)\s*(==|!=)\s*(.+?)\s*", clause)
        if m:
            a, op, b = value(m.group(1)), m.group(2), value(m.group(3))
            ok = (str(a) == str(b)) if op == "==" else (str(a) != str(b))
        else:
            ok = bool(value(clause))
        result = result and ok
    return result


def fill(text, ctx):
    return re.sub(r"\$\{\{\s*(.+?)\s*\}\}", lambda m: str(expression_value(m.group(1), ctx)), text)


def expression_value(text, ctx):
    return lookup(text.strip(), ctx)


class Run:
    """One workflow run's result."""

    def __init__(self, steps, output, comments, calls):
        self.steps = steps          # {step name: "success" | "failure" | "skipped"}
        self.output = output        # everything the steps printed
        self.comments = comments    # the PR's comments after the run
        self.calls = calls          # gh calls, as argv lists
        self.passed = "failure" not in steps.values()

    def annotations(self, kind):
        return [ln for ln in self.output.splitlines() if ln.startswith(f"::{kind} ")
                or ln.startswith(f"::{kind}::")]

    def drift_comments(self):
        return [c for c in self.comments if c["body"].startswith(MARKER)]

    def writes(self, method):
        return [c for c in self.calls if "-X" in c and c[c.index("-X") + 1] == method]


@unittest.skipUnless(yaml and shutil.which("bash") and shutil.which("jq"),
                     "needs PyYAML, bash and jq")
class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.r = FakeRepo()
        self.addCleanup(self.r.close)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        (self.tmp / "bin").mkdir()
        gh = self.tmp / "bin/gh"
        gh.write_text(f"#!{sys.executable}\n{FAKE_GH}")
        gh.chmod(0o755)
        self.state = self.tmp / "gh.json"
        # A reviewer's comment is already on the PR; the workflow must leave it alone.
        self.state.write_text(json.dumps({"next": 100, "calls": [], "comments": [
            {"id": 100, "pr": PR, "body": "Looks good, one nit."}]}))
        self.workflow = yaml.safe_load(WORKFLOW.read_text())
        # The repo as /blueprint-setup leaves it: drift.py copied into .blueprint/.
        r = self.r
        r.write(".blueprint/drift.py", (SCRIPTS / "drift.py").read_text())
        r.capability("orders/checkout", ["src/checkout/**"], {"Pay": ["Card declined"]})
        r.capability("orders/cart", ["src/cart/**"], {"Basket": ["Empty basket"]})
        r.write("src/checkout/pay.ts", "export const pay = 1;\n")
        r.write("src/checkout/total.ts", "export const total = 1;\n")
        r.write("src/cart/basket.ts", "export const basket = 1;\n")
        r.sync()
        r.artifact("checkout-figma", "webpage", "https://figma.com/file/checkout_(v2)",
                   "Checkout flow design", "orders/checkout")
        r.commit("artifact")

    def push(self, path, message="pr change"):
        """A PR commit that changes code without a sync."""
        self.r.edit(path)
        self.r.commit(message)

    def run_workflow(self, fork=False, strict=None):
        """Runs the job's steps in order, as a runner would; returns a Run."""
        wf = self.workflow
        env = dict(wf.get("env", {}))
        if strict is not None:  # what a team edits in its copy
            env["BLUEPRINT_DRIFT_FAIL"] = strict
        runner_temp = self.tmp / f"runner-{len(list(self.tmp.glob('runner-*')))}"
        runner_temp.mkdir()
        ctx = {"github": {"token": "fake-token", "event": {"pull_request": {"number": PR}}},
               "env": env, "steps": {}}
        steps, output, failed = {}, [], False
        for i, step in enumerate(wf["jobs"]["drift"]["steps"]):
            name = step.get("name") or step.get("uses")
            if "uses" in step:
                # actions/checkout: the FakeRepo is the checkout.
                self.assertTrue(step["uses"].startswith("actions/checkout@"), step["uses"])
                steps[name] = "success"
                continue
            if failed or ("if" in step and not expression(step["if"], ctx)):
                steps[name] = "skipped"
                continue
            out_file = runner_temp / f"output-{i}"
            out_file.touch()
            script = runner_temp / f"step-{i}.sh"
            script.write_text(fill(step["run"], ctx))
            step_env = dict(ENV, **{k: str(v) for k, v in env.items()},
                            **{k: fill(str(v), ctx) for k, v in step.get("env", {}).items()},
                            PATH=f"{self.tmp / 'bin'}{os.pathsep}{ENV['PATH']}",
                            RUNNER_TEMP=str(runner_temp), GITHUB_OUTPUT=str(out_file),
                            GITHUB_REPOSITORY=REPO, FAKE_GH_STATE=str(self.state),
                            FAKE_GH_FORK="1" if fork else "0")
            # GitHub's default shell for `run:` on Linux runners.
            done = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)],
                                  cwd=self.r.root, env=step_env, capture_output=True, text=True)
            output.append(done.stdout + done.stderr)
            outputs = {}
            for ln in out_file.read_text().splitlines():
                # Only name=value lines; a name<<EOF block would be misread, so it raises.
                if not re.fullmatch(r"[\w-]+=.*", ln):
                    raise ValueError(f"$GITHUB_OUTPUT line the test can't read: {ln!r}")
                k, v = ln.split("=", 1)
                outputs[k] = v
            if "id" in step:
                ctx["steps"][step["id"]] = {"outputs": outputs}
            steps[name] = "success" if done.returncode == 0 else "failure"
            failed = failed or done.returncode != 0
        state = json.loads(self.state.read_text())
        return Run(steps, "".join(output), state["comments"], state["calls"])

    def assertNoReviewerCommentTouched(self, run):
        self.assertIn({"id": 100, "pr": PR, "body": "Looks good, one nit."}, run.comments)


class OnAPullRequest(WorkflowTest):
    # @scenario blueprint/setup: Drift on a PR
    def test_drift_gets_one_comment_a_warning_and_a_passing_check(self):
        self.push("src/checkout/pay.ts")
        run = self.run_workflow()
        self.assertTrue(run.passed, run.output)
        self.assertEqual(run.steps["Fail on drift"], "skipped")
        [comment] = run.drift_comments()
        body = comment["body"]
        self.assertIn("1 capability drifted since its spec was last synced:", body)
        self.assertRegex(body, r"- \*\*`orders/checkout`\*\* \(since `[0-9a-f]{9}`\): "
                               r"🟥🟥🟥🟥🟥🟥🟥🟥🟥🟥 1 · low\n"
                               r"  - src/checkout/pay\.ts edited \(anchored\) → 1\n"
                               r"  - confidence low: typescript not installed when stamped, "
                               r"so imports are followed by file")
        self.assertNotIn("orders/cart", body)
        self.assertNotIn("#### Possibly affected", body)
        # Imports were followed by file only (no node_modules here), so the Node step would help.
        self.assertIn("commented-out Node step raises it", body)
        [warning] = [w for w in run.annotations("warning") if "Blueprint drift" in w]
        self.assertRegex(warning, r"^::warning title=Blueprint drift::orders/checkout: 1 anchored "
                                  r"file\(s\) changed since [0-9a-f]{9} \(chance 1 · confidence "
                                  r"low\): src/checkout/pay\.ts$")
        self.assertEqual(len(run.writes("POST")), 1)
        self.assertNoReviewerCommentTouched(run)

    # @scenario blueprint/setup: Stale artifact on a PR
    def test_stale_webpage_artifact_is_listed_with_its_link_and_description(self):
        self.push("src/checkout/total.ts")
        run = self.run_workflow()
        self.assertTrue(run.passed, run.output)
        [comment] = run.drift_comments()
        body = comment["body"]
        section = body[body.index("#### Artifacts that may need an update"):]
        self.assertIn("- **`checkout-figma`** (webpage) "
                      "[https://figma.com/file/checkout\\_(v2)](<https://figma.com/file/checkout_(v2)>): "
                      "Checkout flow design", section)
        self.assertIn("covers `orders/checkout`; changed: `src/checkout/total.ts`", section)
        self.assertIn("::warning title=Blueprint artifact::checkout-figma "
                      "(https://figma.com/file/checkout_(v2)): 1 file(s) changed",
                      run.annotations("warning"))

    # @scenario blueprint/setup: Second push
    def test_a_later_push_updates_the_same_comment(self):
        self.push("src/checkout/pay.ts")
        first = self.run_workflow()
        [c1] = first.drift_comments()
        self.push("src/cart/basket.ts", "second push")
        second = self.run_workflow()
        [c2] = second.drift_comments()
        self.assertEqual(c2["id"], c1["id"])
        self.assertNotEqual(c2["body"], c1["body"])
        self.assertIn("**`orders/cart`**", c2["body"])
        self.assertIn("2 capabilities drifted since their specs were last synced", c2["body"])
        self.assertEqual(len(second.writes("POST")), 1)  # still only the first run's
        self.assertEqual(len(second.writes("PATCH")), 1)
        self.assertNoReviewerCommentTouched(second)

    # @scenario blueprint/setup: Back in sync
    def test_resync_marks_the_same_comment_back_in_sync(self):
        self.push("src/checkout/pay.ts")
        [c1] = self.run_workflow().drift_comments()
        self.r.sync("orders/checkout")
        self.r.checked_run("drift.py", "artifacts", "checked", "checkout-figma")
        self.r.commit("artifact checked")
        run = self.run_workflow()
        self.assertTrue(run.passed, run.output)
        [c2] = run.drift_comments()
        self.assertEqual(c2["id"], c1["id"])
        self.assertIn("Back in sync: no capability's code or imported code moved since its "
                      "spec was synced, and no artifact needs a check.", c2["body"])
        self.assertNotIn("Artifacts that may need an update", c2["body"])
        self.assertEqual(run.annotations("warning"), [])

    def test_nothing_to_say_posts_nothing(self):
        run = self.run_workflow()
        self.assertTrue(run.passed, run.output)
        self.assertEqual(run.drift_comments(), [])
        self.assertEqual(run.writes("POST") + run.writes("PATCH"), [])


class Fork(WorkflowTest):
    # @scenario blueprint/setup: Fork PR
    def test_fork_pr_still_gets_the_warnings_and_the_job_passes(self):
        self.push("src/checkout/pay.ts")
        run = self.run_workflow(fork=True)
        self.assertTrue(run.passed, run.output)
        self.assertEqual(run.steps["Comment on the PR"], "success")
        self.assertEqual(run.drift_comments(), [])
        self.assertEqual(len(run.writes("POST")), 1)  # tried, and was refused
        warnings = run.annotations("warning")
        self.assertTrue(any(w.startswith("::warning title=Blueprint drift::orders/checkout:")
                            for w in warnings), warnings)
        self.assertTrue(any(w.startswith("::warning title=Blueprint artifact::checkout-figma")
                            for w in warnings), warnings)
        self.assertIn("::notice::Could not comment on the PR (fork PRs can't comment); "
                      "see the warnings above.", run.annotations("notice"))

    def test_fork_push_after_an_earlier_comment_cannot_update_it(self):
        self.push("src/checkout/pay.ts")
        [before] = self.run_workflow().drift_comments()
        self.push("src/cart/basket.ts")
        run = self.run_workflow(fork=True)
        self.assertTrue(run.passed, run.output)
        self.assertEqual(run.drift_comments(), [before])
        self.assertIn("::notice::Could not update the drift comment (fork PRs can't comment); "
                      "see the warnings above.", run.annotations("notice"))


class Strict(WorkflowTest):
    # @scenario blueprint/setup: Strict mode
    def test_strict_mode_fails_the_job_on_drift(self):
        self.push("src/checkout/pay.ts")
        run = self.run_workflow(strict="true")
        self.assertFalse(run.passed)
        self.assertEqual(run.steps["Fail on drift"], "failure")
        self.assertEqual(run.steps["Comment on the PR"], "success")  # the comment still goes up
        self.assertEqual(len(run.drift_comments()), 1)
        self.assertIn('::error::1 capability(ies) drifted; BLUEPRINT_DRIFT_FAIL is "true".',
                      run.annotations("error"))

    # @scenario blueprint/setup: Strict mode, stale artifact only
    def test_strict_mode_passes_when_only_an_artifact_is_stale(self):
        self.push("src/checkout/pay.ts")
        self.r.sync("orders/checkout")  # the spec caught up; the artifact wasn't checked
        run = self.run_workflow(strict="true")
        self.assertTrue(run.passed, run.output)
        self.assertEqual(run.steps["Fail on drift"], "skipped")
        [comment] = run.drift_comments()
        self.assertNotIn("drifted since", comment["body"])
        self.assertIn("- **`checkout-figma`** (webpage)", comment["body"])
        self.assertEqual(run.annotations("error"), [])

    def test_anything_but_true_only_reports(self):
        self.push("src/checkout/pay.ts")
        run = self.run_workflow(strict="yes")
        self.assertTrue(run.passed, run.output)
        self.assertEqual(run.steps["Fail on drift"], "skipped")


class OlderDriftPy(WorkflowTest):
    def older(self):
        """This drift.py as it was before artifacts: the same script without that command."""
        text = (SCRIPTS / "drift.py").read_text()
        older = text.replace('"artifacts": cmd_artifacts', "")
        self.assertNotEqual(older, text)
        self.r.write(".blueprint/drift.py", older)
        self.r.commit("older drift.py")
        said = subprocess.run([sys.executable, ".blueprint/drift.py", "artifacts"], cwd=self.r.root,
                              capture_output=True, text=True, env=ENV)
        self.assertEqual((said.returncode, said.stderr), (1, "unknown command: artifacts\n"))

    # @scenario blueprint/setup: Older
    def test_older_drift_py_reports_drift_and_skips_artifacts_with_a_notice(self):
        self.older()
        self.push("src/checkout/pay.ts")
        run = self.run_workflow()
        self.assertTrue(run.passed, run.output)
        [comment] = run.drift_comments()
        self.assertIn("**`orders/checkout`**", comment["body"])
        self.assertIn("  - src/checkout/pay.ts edited (anchored) → 1", comment["body"])
        self.assertNotIn("Artifacts that may need an update", comment["body"])
        self.assertIn("Artifacts skipped: `.blueprint/drift.py` predates them.", comment["body"])
        self.assertTrue(any(n.startswith("::notice title=Blueprint artifacts::.blueprint/drift.py "
                                         "predates artifacts; skipping")
                            for n in run.annotations("notice")), run.output)
        warnings = run.annotations("warning")
        self.assertTrue(any("Blueprint drift::orders/checkout" in w for w in warnings), warnings)
        self.assertFalse(any("Blueprint artifact::" in w for w in warnings), warnings)

    def test_older_and_in_sync_says_so_without_the_artifact_clause(self):
        self.push("src/checkout/pay.ts")
        [c1] = self.run_workflow().drift_comments()
        self.older()
        self.r.sync("orders/checkout")
        run = self.run_workflow()
        [c2] = run.drift_comments()
        self.assertEqual(c2["id"], c1["id"])
        self.assertIn("Back in sync: no capability's code or imported code moved since its "
                      "spec was synced.\n", c2["body"])


class Failures(WorkflowTest):
    def test_a_broken_drift_py_fails_the_job_with_an_error(self):
        self.r.write(".blueprint/drift.py", "import sys\nsys.exit(3)\n")
        self.r.commit("broken")
        run = self.run_workflow()
        self.assertFalse(run.passed)
        self.assertEqual(run.steps["Check drift"], "failure")
        self.assertEqual(run.steps["Comment on the PR"], "skipped")
        self.assertIn("::error::drift.py check failed (exit 3)", run.annotations("error"))


# check --json rows as drift.py reports them once imports are followed (group 2 of transitive
# drift produces them); stubbed here so the comment and annotations are tested on their own.
IN_SYNC = {"status": "in-sync", "chance": 0.0, "confidence": "medium",
           "reasons": ["confidence medium: no test results given"]}
DEPS_MOVED = {"capability": "orders/checkout", "status": "deps-moved", "chance": 0.5,
              "confidence": "medium", "reasons": [
                  "packages/core/src/token.ts signToken changed, 1 import away, "
                  "via @company/core (weight 1) → 0.5",
                  "confidence medium: no test results given"]}
POSSIBLE = {"capability": "orders/cart", "status": "possibly-affected", "chance": 0.0625,
            "confidence": "medium", "reasons": [
                "packages/core/src/money.ts round_cents changed, 3 imports away, "
                "via @company/core (weight 0.5) → 0.0625",
                "confidence medium: no test results given"]}


def in_sync(cap):
    return dict(IN_SYNC, capability=cap)


class Scored(WorkflowTest):
    def stub(self, report):
        """Replaces .blueprint/drift.py with one whose `check --json` prints this report, with
        drift.py's exit rule, and whose `artifacts` lists nothing."""
        code = 1 if any(r["status"] in ("code-moved", "deps-moved") for r in report) else 0
        self.r.write(".blueprint/drift.py",
                     "import sys\n"
                     "if sys.argv[1] == 'check':\n"
                     f"    print({json.dumps(json.dumps(report))})\n"
                     f"    sys.exit({code})\n"
                     "print('[]')\n")
        self.r.commit("stub drift.py")

    # @scenario blueprint/setup: Possibly affected on a PR
    def test_possibly_affected_is_listed_with_its_chance_and_reasons_but_no_annotation(self):
        self.stub([in_sync("orders/checkout"), POSSIBLE])
        run = self.run_workflow(strict="true")
        self.assertTrue(run.passed, run.output)  # never fails the job, even in strict mode
        self.assertEqual(run.steps["Fail on drift"], "skipped")
        [comment] = run.drift_comments()
        body = comment["body"]
        self.assertIn("#### Possibly affected\n\nCode these import changed, below the drift "
                      "threshold: worth a look, not counted as drift:\n\n"
                      "- **`orders/cart`**: 🟨⬜⬜⬜⬜⬜⬜⬜⬜⬜ 0.0625 · medium\n"
                      "  - packages/core/src/money.ts round\\_cents changed, 3 imports away, "
                      "via `@company/core` (weight 0.5) → 0.0625\n"
                      "  - confidence medium: no test results given\n", body)
        self.assertNotIn("drifted since", body)
        self.assertNotIn("orders/checkout", body)
        self.assertNotIn("Node step", body)  # nothing low confidence
        self.assertIn("Squares fill with the drift chance (0 to 1) and are colored by "
                      "confidence: 🟩 high, 🟨 medium, 🟥 low.", body)
        self.assertEqual(run.annotations("warning"), [])
        self.assertEqual(len(run.writes("POST")), 1)

    def test_deps_moved_is_drifted_with_its_chance_reasons_and_a_warning(self):
        self.stub([DEPS_MOVED, in_sync("orders/cart")])
        run = self.run_workflow(strict="true")
        self.assertFalse(run.passed)
        self.assertEqual(run.steps["Fail on drift"], "failure")
        [comment] = run.drift_comments()
        self.assertIn("1 capability drifted since its spec was last synced:\n\n"
                      "- **`orders/checkout`** (imported code moved): 🟨🟨🟨🟨🟨⬜⬜⬜⬜⬜ 0.5 · "
                      "medium\n"
                      "  - packages/core/src/token.ts signToken changed, 1 import away, "
                      "via `@company/core` (weight 1) → 0.5\n"
                      "  - confidence medium: no test results given\n", comment["body"])
        self.assertNotIn("#### Possibly affected", comment["body"])
        self.assertEqual(run.annotations("warning"), [
            "::warning title=Blueprint drift::orders/checkout: imported code moved (chance 0.5 · "
            "confidence medium): packages/core/src/token.ts signToken changed, 1 import away, "
            "via @company/core (weight 1) → 0.5"])

    def test_drifted_comes_before_possibly_affected_and_only_drifted_is_annotated(self):
        self.stub([DEPS_MOVED, POSSIBLE])
        run = self.run_workflow()
        self.assertTrue(run.passed, run.output)
        [comment] = run.drift_comments()
        body = comment["body"]
        self.assertLess(body.index("**`orders/checkout`**"), body.index("#### Possibly affected"))
        self.assertLess(body.index("#### Possibly affected"), body.index("**`orders/cart`**"))
        [warning] = run.annotations("warning")
        self.assertIn("orders/checkout", warning)

    # @scenario blueprint/setup: Back in sync
    def test_possibly_affected_then_in_sync_marks_the_same_comment_back_in_sync(self):
        self.stub([in_sync("orders/checkout"), POSSIBLE])
        [c1] = self.run_workflow().drift_comments()
        self.stub([in_sync("orders/checkout"), in_sync("orders/cart")])
        run = self.run_workflow()
        [c2] = run.drift_comments()
        self.assertEqual(c2["id"], c1["id"])
        self.assertIn("Back in sync:", c2["body"])
        self.assertNotIn("#### Possibly affected", c2["body"])

    def test_imports_followed_by_file_point_at_the_node_step(self):
        self.stub([dict(DEPS_MOVED, confidence="low", reasons=[
            "packages/core/src/token.ts changed, 1 import away → 0.5",
            "confidence low: no node_modules, so imports are followed by file"])])
        [comment] = self.run_workflow().drift_comments()
        self.assertIn("the workflow's commented-out Node step raises it", comment["body"])

    def test_deps_moved_with_only_a_confidence_reason_has_no_dangling_colon(self):
        self.stub([dict(DEPS_MOVED, reasons=["confidence medium: no test results given"])])
        [warning] = self.run_workflow().annotations("warning")
        self.assertTrue(warning.endswith("imported code moved (chance 0.5 · confidence medium)"),
                        warning)

    def test_annotations_escape_percent_signs(self):
        self.stub([dict(DEPS_MOVED, reasons=["src/fee.ts rate changed to 5%, 1 import away → 0.5"])])
        run = self.run_workflow()
        [warning] = run.annotations("warning")
        self.assertTrue(warning.endswith("rate changed to 5%25, 1 import away → 0.5"), warning)

    def test_drift_py_before_scores_lists_the_changed_files(self):
        self.stub([{"capability": "orders/checkout", "status": "code-moved",
                    "syncedCommit": "abcdef1234567", "changed": ["src/checkout/pay.ts"]},
                   {"capability": "orders/cart", "status": "in-sync"}])
        run = self.run_workflow()
        [comment] = run.drift_comments()
        self.assertIn("- **`orders/checkout`** (since `abcdef123`)\n  - `src/checkout/pay.ts`\n",
                      comment["body"])
        self.assertEqual(run.annotations("warning"), [
            "::warning title=Blueprint drift::orders/checkout: 1 anchored file(s) changed since "
            "abcdef123: src/checkout/pay.ts"])


class NodeStep(unittest.TestCase):
    def test_node_install_step_is_offered_commented_out(self):
        text = WORKFLOW.read_text()
        self.assertIn("      # - name: Set up Node\n      #   uses: actions/setup-node@v4\n", text)
        self.assertIn("      # - name: Install dependencies\n      #   run: npm ci\n", text)
        if yaml:
            steps = yaml.safe_load(text)["jobs"]["drift"]["steps"]
            self.assertFalse(any("setup-node" in s.get("uses", "") for s in steps), steps)


if __name__ == "__main__":
    unittest.main()
