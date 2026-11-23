## Purpose

Traces each spec scenario to the tests that claim it, by kind, and reports scenarios no test claims and tags that point at nothing.

## Requirements

### Requirement: Scenario tags

A test SHALL claim a scenario with a comment line `@scenario <capability>: <scenario name>` placed in any line comment (`//`, `#`, `--`, `/* */`, `*`, `<!-- -->`). Several tags MAY sit on one test, and many tests MAY claim one scenario. Scenario names SHALL be matched case-insensitively with whitespace collapsed.

- **Scenario: Tag in a Rust test**
  - **GIVEN** `// @scenario auth/session: Expired session redirects to login` above a `#[test]` function
  - **WHEN** coverage runs
  - **THEN** that scenario is claimed by the test's file and line
- **Scenario: Tag in a Python test**
  - **GIVEN** `# @scenario auth/session: Expired session redirects to login` above a pytest function
  - **WHEN** coverage runs
  - **THEN** the scenario is claimed the same way

### Requirement: Unique scenario names

Scenario names SHALL be unique within a capability. Coverage SHALL report any duplicate as a problem naming both requirements.

- **Scenario: Same name twice**
  - **GIVEN** two requirements in `auth/session` each with a scenario `Expired token`
  - **WHEN** coverage runs
  - **THEN** it reports the duplicate with both requirement names

### Requirement: Test kinds

`tests.kinds` in `blueprint.json` SHALL map each kind name to globs, and each claiming test SHALL get the first kind whose globs match its file. Coverage SHALL NOT guess kinds: when `tests.kinds` is absent, `coverage.py` SHALL exit 2 naming the missing key and write nothing. A tag in a file no kind matches SHALL still count as a claim and SHALL be reported as unclassified.

- **Scenario: Custom kind**
  - **GIVEN** `tests.kinds` has `contract: ["pact/**"]` first
  - **WHEN** a tag sits in `pact/user.test.ts`
  - **THEN** the claim's kind is `contract`
- **Scenario: Kinds not configured**
  - **GIVEN** `blueprint.json` has no `tests.kinds`
  - **WHEN** `coverage.py` runs
  - **THEN** it exits 2 saying `tests.kinds` is required, and reports nothing
- **Scenario: Tag outside every kind**
  - **GIVEN** `tests.kinds` covers only `e2e/**` and a tag sits in `src/session.rs`
  - **WHEN** coverage runs
  - **THEN** the scenario counts as claimed and the tag is listed as unclassified

### Requirement: Coverage report

`coverage.py` SHALL report, for each capability with a baseline, every requirement and scenario with its claiming tests (`file:line`, kind), and a summary of scenarios claimed of total, per kind. `--json` SHALL print the same data, `<capability>` SHALL limit it to one capability, and nothing SHALL be written. The report SHALL say "claimed", never "verified" or "passing".

- **Scenario: Untested requirement**
  - **GIVEN** a requirement whose two scenarios have no tags
  - **WHEN** coverage runs
  - **THEN** both scenarios are listed as uncovered under their requirement

### Requirement: Orphan tags

A tag whose capability is not in `specs`, or whose scenario is not in that capability's baseline or the `--delta` file, SHALL be reported as an orphan with its file and line, and the closest scenario name when one is near. Tags for a capability with no baseline SHALL be reported as having no spec yet.

- **Scenario: Scenario reworded**
  - **GIVEN** a tag for `Expired session redirects` and the spec now says `Expired session redirects to login`
  - **WHEN** coverage runs
  - **THEN** the tag is an orphan, with `Expired session redirects to login` suggested

### Requirement: Pending scenarios from a delta

`coverage.py --delta FILE` SHALL read a brief's Spec delta and treat its ADDED and MODIFIED scenarios as known, marked pending, and its REMOVED requirements' scenarios as gone.

- **Scenario: New scenario during apply**
  - **GIVEN** a tag for a scenario that exists only in the brief's delta
  - **WHEN** coverage runs with `--delta` on that brief
  - **THEN** the scenario is claimed and marked pending, not orphaned

### Requirement: CI gate

`--strict` SHALL exit 1 when there are orphans, unclassified tags or duplicates. `--strict=all` SHALL also exit 1 when any scenario is uncovered.

- **Scenario: Partly tagged repo**
  - **GIVEN** uncovered scenarios but no orphans
  - **WHEN** `coverage.py --strict` runs
  - **THEN** it exits 0

### Requirement: Coverage mode

`/blueprint coverage [capability]` SHALL first check for `tests.kinds`; when it is missing, it SHALL propose kinds and globs from the repo's test files and write them to `blueprint.json` only after the user's yes. It SHALL then run the script and report the summary, the uncovered scenarios grouped by capability, and the orphans with a suggested fix. It SHALL offer `suggest`, in which the agent reads untagged test files alongside the scenarios and proposes tags as a diff; tags SHALL be written only after the user's yes, and only as added comment lines.

- **Scenario: Bootstrapping an untagged repo**
  - **GIVEN** a repo with tests and no tags
  - **WHEN** the user accepts `suggest` for `auth/session`
  - **THEN** a diff of `@scenario` comments is shown, and written to the test files after the user's yes, with no other change to them
- **Scenario: First run without kinds**
  - **GIVEN** a repo with `e2e/` Playwright tests and `*.test.ts` files beside the code, and no `tests.kinds`
  - **WHEN** the user runs `/blueprint coverage`
  - **THEN** it proposes `e2e: ["e2e/**"]` and `unit: ["**/*.test.ts"]`, writes them on a yes, and then reports

### Requirement: Test names for tags

Coverage SHALL record, for each tag, the name of the test declared on the first test declaration below it (`test`, `it` or `describe` calls in JS/TS, `def test_…` in Python, the `fn` after `#[test]` in Rust, `func Test…` in Go), and `--json` SHALL include it. A tag with no test declaration below it SHALL be recorded without a name.

- **Scenario: Named Vitest test**
  - **GIVEN** `// @scenario auth/session: Expired token` above `it('rejects an expired token', …)`
  - **WHEN** `coverage.py --json` runs
  - **THEN** the claim carries the test name `rejects an expired token`
