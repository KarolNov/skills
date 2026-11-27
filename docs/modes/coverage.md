# Coverage

```
/blueprint coverage [capability | suggest [capability]] [--strict[=all]]
```

Coverage traces each spec scenario to the tests that claim it, and names the scenarios that no test claims.

## Scenario tags

A test claims a scenario with a comment on the line above it, in the file's own comment syntax: `// @scenario auth/session: Expired session redirects to login` above a TypeScript test, or `# @scenario billing/invoices: Late fee after 30 days` above a Python one. This is how `suggest` shows a tag it proposes:

```diff
+  // @scenario auth/session: Expired session redirects to login
   it("redirects to login when the session expired", async () => {
```

The name matches the scenario case-insensitively, with whitespace collapsed. Coverage is **static**: nothing is run, so a scenario is *claimed*, never *passing*.

## Kinds

On the first run, coverage proposes **kinds** of tests (unit, e2e, contract…), each with the globs that find its files, and writes them to `blueprint.json` on your yes:

```json
"tests": { "kinds": { "e2e": ["e2e/**"], "unit": ["**/*.test.ts"] } }
```

## The report

- **Summary**: scenarios claimed out of the total, overall, per kind and per capability.
- **Uncovered**: the scenarios no test claims, grouped by requirement.
- **Problems**: *orphan* tags that point at nothing (with the nearest scenario name), tags in files no kind matches, and scenario names used twice in one capability.

`suggest` reads the untagged tests near a capability's code and proposes tags as a diff, for the tests that clearly check a scenario. It only ever adds comment lines.

## In CI

`--strict` exits non-zero on orphans, unclassified tags and duplicates. `--strict=all` also fails on uncovered scenarios. This lets you turn on the gate before everything is tagged.

The [map](/modes/map) shows the same coverage per scenario, and [Apply](/modes/apply) uses the tags as its evidence that each requirement is built.
