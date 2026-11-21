# Coverage

Trace each spec scenario to the tests that claim it, by kind, and name the scenarios no test claims and the tags that point at nothing. It reads only the repo (`blueprint.json`, `baseline/`, the test files) and runs nothing: a tag means a test **claims** a scenario, so say "claimed", never "verified", "tested" or "passing". The tag syntax and the `tests` key are in [formats.md](formats.md).

Arguments: `coverage` alone reports every capability; `coverage <capability>` reports one; `coverage suggest [capability]` goes straight to step 4 after the report.

## 1. Kinds

Read `tests.kinds` from `.blueprint/blueprint.json`. When it is there, go to step 2.

When it is missing, propose it; never guess silently, and never run the report without it. Survey the repo's test files (`git ls-files`, then the test runner configs: `playwright.config.*`, `vitest`/`jest` config, `Cargo.toml`, `go.mod`, `pytest.ini`/`pyproject.toml`) and propose one kind per kind of test the repo actually has, each with the globs that find its files, the most specific first, since a file gets the first kind that matches:

```json
"tests": { "kinds": { "e2e": ["e2e/**"], "unit": ["**/*.test.ts"] } }
```

Name the files each kind would match (a count and two examples) and any test file no kind would match. Kinds are free-form (`contract`, `visual`) when the repo has them. Rust's inline `#[cfg(test)]` modules sit in the code's own files: propose `src/**/*.rs` as `unit` after the more specific kinds, or leave them unclassified, and say which. Write the key to `blueprint.json` on the user's yes (no format version change), then continue.

## 2. Report

From anywhere inside the repo:

```bash
python3 <this skill>/scripts/coverage.py [capability]
```

Run the skill's own `coverage.py`, never a copy in the repo: it imports `drift.py` from next to it, like `graph.py`. `--json` prints the same data, which is the quickest way to answer a question about it. It writes nothing. It exits 2 when `tests.kinds` is missing (go back to step 1) or a filter names no capability; show any other error and stop, never hand-build the report.

Report in a few lines, from its output:

- **Summary**: scenarios claimed of total, overall and per kind, and per capability when there are several.
- **Uncovered**: the scenarios no tag claims, grouped by capability, then requirement.
- **Problems**, each with its fix: an **orphan** tag (its file and line, and the nearest scenario name it gives: propose rewriting the tag to it, or say the scenario is gone); an **unclassified** tag (propose a glob for its file under a kind); a **duplicate** scenario name within a capability (both requirements named: rename one through a blueprint, since specs change only through a delta or sync); tags for a capability with **no spec yet** (nothing to fix until it has a baseline).

Offer `suggest` when there are uncovered scenarios, and fix orphans or unclassified tags only on the user's yes (tags as below; globs in `tests.kinds`).

## 3. Gate

For CI, `--strict` exits 1 on orphans, unclassified tags and duplicates, and `--strict=all` also on uncovered scenarios, so a repo can turn the gate on before everything is tagged. Mention it once when the report has no problems; adding it to a workflow is the user's call.

## 4. Suggest

For the capability named, or each with uncovered scenarios (largest first, one capability per round when there are several): read its scenarios from `baseline/<capability>.md` and the untagged tests likely to exercise it (test files near its anchors, files that import its anchored code, tests whose names echo a scenario). For each test that clearly checks a scenario's WHEN and THEN, propose a tag; skip the ones you would have to stretch. Show the proposals as one diff:

```diff
+  // @scenario auth/session: Expired session redirects to login
   it("redirects to login when the session expired", async () => {
```

Use the file's own line-comment syntax, indented like the test, right above the test (above its attributes or decorators: `#[test]`, `@pytest.mark…`). Write on the user's yes, adding comment lines only: never change a test's code, names or other comments. Then rerun the report and give the new summary. Scenarios still uncovered after `suggest` need tests, which is the user's work to plan (often a blueprint), not this mode's.
