## Purpose

Code-side drift detection and spec sync: finds capabilities whose anchored code moved since their spec was last synced, and updates the specs to describe what the code now does. The code is right; the spec moves.

## Requirements

### Requirement: Code drift detection

`drift.py check` SHALL report each capability as `in-sync`, `code-moved` (listing the anchored files added, removed or edited since the last stamp), `deps-moved` (its drift chance reached the threshold through code it imports or failing tests, with no anchored file changed), `possibly-affected` (a drift chance above 0 and below the threshold), `no-spec` or `no-anchors`, using only git, file hashes and the stamped closure. Each capability SHALL carry its drift chance, its confidence and the reasons for both. It SHALL exit 1 when any capability is `code-moved` or `deps-moved`, and 0 otherwise.

- **Scenario: Anchored file edited**
  - **GIVEN** a capability was stamped
  - **WHEN** one of its anchored files changes
  - **THEN** check lists that capability as `code-moved` with that file and a drift chance of 1.0, and exits 1
- **Scenario: Imported symbol changed**
  - **GIVEN** an anchored file does `import { signToken } from '@company/core'`, a package with `"sideEffects": false` and package weight 1.0
  - **WHEN** `signToken`'s body changes
  - **THEN** check lists the capability as `deps-moved` with chance 0.5, a reason naming `signToken` one import away, and exits 1
- **Scenario: Unused export changed**
  - **GIVEN** the same import of `signToken` only
  - **WHEN** only another export of `@company/core` that `signToken` doesn't use changes
  - **THEN** the capability stays `in-sync`
- **Scenario: Distant change below threshold**
  - **GIVEN** default scoring
  - **WHEN** a symbol three imports away, across one package boundary, changes
  - **THEN** check lists the capability as `possibly-affected` with its chance and reason, and exits 0

### Requirement: Stamping

`drift.py stamp` SHALL record a content hash per anchored file and the commit holding the synced code. For a capability with TS/JS anchored files, it SHALL also record its import closure in `.blueprint/closure/<capability>.json`: each reachable file or symbol with its distance, the packages crossed, and a content hash, plus the locked version of each external dependency it imports. It SHALL warn when anchored files are uncommitted.

- **Scenario: Uncommitted code**
  - **WHEN** stamp runs while anchored files have uncommitted changes
  - **THEN** it warns that `syncedCommit` would predate that code
- **Scenario: Closure recorded**
  - **GIVEN** a TS capability whose anchored file imports two symbols from a workspace package
  - **WHEN** stamp runs
  - **THEN** `.blueprint/closure/<capability>.json` lists both symbols, their distance and hashes

### Requirement: Anchor helpers

`drift.py files <capability> [anchor…]` SHALL list the files a capability's anchors match, or the given anchors instead, writing nothing. `drift.py unanchored [--since REF]` SHALL list changed files that no capability covers. `drift.py overlaps [--json]` SHALL list files matched by two or more capabilities, with the capabilities and the anchors that match. `drift.py rename <old> <new>` SHALL move a capability's key, baseline file and closure file, keeping its stamps, rewrite `@scenario <old>:` tags to the new name, and refuse when a baseline or closure file already sits at the new name. `drift.py prune <capability>` SHALL drop the stamps of files its anchors no longer match, keeping the rest, and re-record its closure. `drift.py version` SHALL print the format version of `blueprint.json`, 1 when absent. Anchors SHALL be git-style globs with `**` and `!` exclusions.

- **Scenario: Excluded tests**
  - **GIVEN** anchors `["src/auth/**", "!**/*.test.ts"]`
  - **WHEN** files are listed
  - **THEN** test files under `src/auth/` are not included
- **Scenario: Overlap listed**
  - **GIVEN** two capabilities whose anchors both match `worker/index.ts`
  - **WHEN** `drift.py overlaps` runs
  - **THEN** `worker/index.ts` is listed once with both capabilities
- **Scenario: Rename rewrites tags**
  - **GIVEN** tests tagged `@scenario search: Empty query`
  - **WHEN** `drift.py rename search catalog/search` runs
  - **THEN** those tags read `@scenario catalog/search: Empty query`

### Requirement: Status table

Sync and drift SHALL both start from one status table that combines the code side (`drift.py check`) with the spec side (the backend's version marker compared with `specVersion`). The table SHALL suggest drift or sync depending on which side is right.

- **Scenario: Both moved**
  - **WHEN** both the code and the spec of a capability moved
  - **THEN** the table suggests running drift first, then sync

### Requirement: Spec edits wait for drift

Sync SHALL leave out any capability whose spec moved, and name it as one for `blueprint-drift` first, so intent edits are never overwritten.

- **Scenario: Teammate edited the spec**
  - **WHEN** sync runs on a capability whose spec moved
  - **THEN** it skips that capability and points to `blueprint-drift`

### Requirement: Behavior versus internal changes

Sync SHALL sort each code change into behavior or internal. Internal changes SHALL never touch the spec. A behavior change that contradicts a requirement with nothing saying it was intended SHALL be put to the user, not written.

- **Scenario: Refactor**
  - **WHEN** the only change is a rename with no contract change
  - **THEN** the spec is left alone and the capability is restamped

### Requirement: Spec written from code

For a capability with no spec, sync SHALL draft the whole spec from its anchored code, mark accidental-looking behavior with `<!-- verify: … -->`, create the page after approval (inside its domain when its name has one), link it from that domain overview's Capabilities list, and do the bookkeeping.

- **Scenario: no-spec capability named**
  - **WHEN** the user runs `/blueprint-sync <capability>` on a capability with `"ref": null`
  - **THEN** a full spec is drafted from the code and shown for approval

### Requirement: Bookkeeping after every agreement

Whenever a spec and its code are known to agree, the normalized spec SHALL be saved as `baseline/<capability>.md`, `specVersion` recorded from a read-back, and the capability stamped. A capability with a known disagreement SHALL NOT be recorded.

- **Scenario: Known gap left**
  - **WHEN** a capability still has a disagreement the user didn't resolve
  - **THEN** it is not stamped, so the next status shows it again

### Requirement: Tidy nudge

After a sync, the skill SHALL run `drift.py hint` and show its line when there is one: when more than 10 capabilities have no domain, or 3 or more capabilities without a domain share a top-level anchor folder. It SHALL never restructure anything itself.

- **Scenario: Growing flat list**
  - **GIVEN** 11 capabilities and no domains
  - **WHEN** a sync finishes
  - **THEN** its report ends with one line suggesting `/blueprint-tidy`

### Requirement: Baselines stay in the repo

Baselines SHALL live in `.blueprint/baseline/` and be committed with the code they describe, never moved to the backend or out of git. When two branches change the same spec, their baselines SHALL conflict in git; that conflict is intended, and it SHALL be resolved by syncing the merged code against the current spec, never by picking one side's baseline.

- **Scenario: Two PRs change one spec**
  - **GIVEN** two open PRs that each synced `auth/session`
  - **WHEN** the second is merged after the first
  - **THEN** git reports a conflict in `baseline/auth/session.md`, and it is resolved by running `/blueprint-sync auth/session` on the merged code

### Requirement: Artifacts

`blueprint.json` MAY hold a top-level `artifacts` map from a kebab-case id to `{type, value, description, capabilities, checkedFiles}`. `type` SHALL be one of `webpage`, `notion`, `confluence`, `linear`, `github` (value a URL), `file` (value `<repo>:<path>`), `obsidian` or `markdown` (value a path to the note). `capabilities` SHALL name capabilities or domains, where a domain stands for every capability in it at check time. `drift.py artifacts add` SHALL add one and stamp it as checked. `drift.py artifacts checked <id>… | --all` SHALL record a hash per file its capabilities' anchors match, and SHALL refuse an artifact whose `capabilities` name something that is no longer a capability or a domain. `drift.py artifacts remove <id>` SHALL drop one. `drift.py artifacts [--json] [--] [capability|domain…]` SHALL list each artifact whose files were added, removed or edited since it was checked, with those files, and, under any filter, each artifact whose `capabilities` name something that is no longer a capability or a domain, marked unknown. It SHALL exit 0, unless a filter names no capability or domain. `drift.py rename` SHALL rename the capability in every artifact that names it, and `drift.py prune` SHALL trim the dropped files from the `checkedFiles` of artifacts over that capability, unless another capability they cover still matches them.

- **Scenario: Code changes after a check**
  - **GIVEN** an artifact covering `billing/invoices`, checked
  - **WHEN** a file anchored by `billing/invoices` changes
  - **THEN** `drift.py artifacts` lists that artifact with the file
- **Scenario: Spec synced, artifact not checked**
  - **GIVEN** a stale artifact
  - **WHEN** its capability is synced and stamped, but the artifact is not marked checked
  - **THEN** the artifact is still listed
- **Scenario: Domain-wide artifact**
  - **GIVEN** an artifact covering the domain `billing`
  - **WHEN** a capability is added to `billing` and its code later changes
  - **THEN** the artifact is listed
- **Scenario: Unknown type**
  - **WHEN** `drift.py artifacts add` is given a type not in that list, or a value of the wrong shape for its type
  - **THEN** it refuses and writes nothing
- **Scenario: Page in the same backend**
  - **GIVEN** a repo whose backend is Notion
  - **WHEN** an artifact of type `notion` is added with another page's URL
  - **THEN** it is stored with type `notion` and listed like any other artifact
- **Scenario: Capability removed by hand**
  - **GIVEN** an artifact naming `billing/old`, which is no longer a capability
  - **WHEN** `drift.py artifacts billing/invoices` runs
  - **THEN** the artifact is listed, marked unknown, and `drift.py artifacts checked` refuses it

### Requirement: Sync asks about stale artifacts

After the bookkeeping, sync SHALL list the stale artifacts of the capabilities it synced and ask, for each, whether it was updated, is still accurate, or is left for later. It SHALL mark the first two checked and leave the third stale. An artifact that names an unknown capability SHALL be added again with the corrected names, and only when the user says it was updated or is still accurate. Sync SHALL never edit an artifact.

- **Scenario: Article left for later**
  - **WHEN** the user says a stale support article will be updated later
  - **THEN** sync leaves it stale, so the next CI run lists it again

### Requirement: Drift chance

The drift chance SHALL be computed by a fixed formula, so the same stamped state, working tree, settings and test results always give the same number. A changed anchored file SHALL score 1.0. A changed file or symbol reached through imports SHALL score `decay` raised to its distance in import edges, multiplied by the weight of each workspace package the path enters. A changed locked version of an external dependency the closure imports SHALL score `lockfileWeight`. A failing test tagged with one of the capability's scenarios SHALL set the chance to 1.0. Several signals SHALL combine as one minus the product of one minus each.

- **Scenario: Same diff, same number**
  - **WHEN** check runs twice on the same tree with the same settings and test results
  - **THEN** every capability gets the same chance, confidence and reasons both times
- **Scenario: Two weak signals**
  - **GIVEN** two changed symbols, each scoring 0.25
  - **WHEN** check runs
  - **THEN** the capability's chance is 0.4375
- **Scenario: Dependency bumped**
  - **GIVEN** a capability whose closure imports `zod`, and default scoring
  - **WHEN** the lockfile moves `zod` to another version
  - **THEN** the capability's chance includes 0.3 with a reason naming `zod` and both versions

### Requirement: Side effects decide what an import depends on

A named import from a package without side effects SHALL depend only on the imported symbols and the declarations they reference, followed through re-exports and across files and packages. A bare import, or any import from a package with side effects, SHALL depend on every file of that package the closure reaches. A package's side effects SHALL come from its `package.json` `sideEffects` field: `false` means none; a list of globs means the matching files have side effects and the rest do not; an absent field means it has side effects. `drift.scoring.packages.<name>.sideEffects` SHALL override the field.

- **Scenario: Side-effect import**
  - **GIVEN** an anchored file with `import '@company/polyfills'`
  - **WHEN** any file of `@company/polyfills` changes
  - **THEN** the capability's chance includes that change
- **Scenario: Field absent**
  - **GIVEN** `@company/legacy` has no `sideEffects` field and no override
  - **WHEN** an export the capability doesn't import changes
  - **THEN** the change still counts toward the capability's chance
- **Scenario: Override**
  - **GIVEN** `drift.scoring.packages["@company/legacy"].sideEffects` is `false`
  - **WHEN** an export the capability doesn't import changes
  - **THEN** the change does not count
- **Scenario: Barrel re-export**
  - **GIVEN** `import { a } from '@company/ui'`, where `@company/ui`'s index does `export * from './button'` and `a` is defined in `button.ts`
  - **WHEN** `a` changes
  - **THEN** the reason names `a` in `button.ts`, not the index file

### Requirement: Scoring settings

`blueprint.json` MAY hold `drift.scoring` with `decay`, `packageWeight`, `lockfileWeight`, `threshold`, `maxDepth` and `packages` (per package name: `weight`, `sideEffects`). Each key SHALL default when absent: `decay` 0.5, `packageWeight` 0.5, `lockfileWeight` 0.3, `threshold` 0.5, `maxDepth` 6. A package's `weight` SHALL replace `packageWeight` for paths entering that package. Check SHALL refuse a value outside 0 to 1 (or a `maxDepth` below 1), naming the key, and report nothing.

- **Scenario: Core package weighted up**
  - **GIVEN** `packages["@company/core"].weight` is 1.0
  - **WHEN** a symbol one import away in `@company/core` changes
  - **THEN** it scores 0.5, not 0.25
- **Scenario: Bad setting**
  - **WHEN** `drift.scoring.decay` is 2
  - **THEN** check exits 2 naming `drift.scoring.decay`

### Requirement: Test results as a signal

`drift.py check --tests run` SHALL run `tests.run` from `blueprint.json` and read the JUnit XML it names. `--tests <file>` SHALL read an existing JUnit XML report. Without `--tests`, check SHALL use no test results. A report entry SHALL count for a scenario when its file and test name match a tagged test. Check SHALL never run tests without `--tests run`.

- **Scenario: Failing tagged test**
  - **GIVEN** a test tagged `@scenario auth/session: Expired session redirects to login` that fails in the report
  - **WHEN** `check --tests report.xml` runs with no code changed
  - **THEN** `auth/session` is `deps-moved` with chance 1.0, confidence high, and a reason naming the test and scenario
- **Scenario: Run mode without a command**
  - **GIVEN** `blueprint.json` has no `tests.run`
  - **WHEN** `check --tests run` runs
  - **THEN** it exits 2 naming `tests.run`

### Requirement: Confidence and reasons

Each capability SHALL get a confidence of `high` (test results were given and imports were resolved by symbol), `medium` (imports were resolved by symbol, no test results), or `low` (imports could only be followed by file, or not at all, for a TS/JS capability). A capability with no TS/JS files SHALL get `high` when only direct changes apply. Every contribution to the chance SHALL appear as one reason line naming what changed, its distance, the packages crossed with their weights and its score, and the confidence SHALL carry one line saying why it is not higher.

- **Scenario: No test results**
  - **WHEN** check runs without `--tests` on a TS capability with TypeScript available
  - **THEN** its confidence is medium with the reason "no test results given"

### Requirement: Fallback without TypeScript tooling

When Node or the repo's `typescript` package can't be found, check SHALL follow imports by file instead of by symbol, set confidence `low` for affected capabilities with a reason saying what was missing, print one notice line, and still exit by the same rule. It SHALL never install anything.

- **Scenario: CI without node_modules**
  - **GIVEN** a CI checkout with no installed dependencies
  - **WHEN** a file two imports away from an anchored file changes
  - **THEN** check scores it at file level, marks confidence low with "typescript not installed", and prints one notice

### Requirement: Sync reads the reasons

For a `deps-moved` capability, sync SHALL treat the changed symbols and files named in its reasons as the code change to sort into behavior or internal, and restamp it, closure included, once spec and code agree.

- **Scenario: Upstream refactor**
  - **GIVEN** a capability `deps-moved` because an imported helper was renamed internally
  - **WHEN** sync sorts it as internal
  - **THEN** the spec is left alone and the capability and its closure are restamped
