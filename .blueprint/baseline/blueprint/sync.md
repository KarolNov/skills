## Purpose

Code-side drift detection and spec sync: finds capabilities whose anchored code moved since their spec was last synced, and updates the specs to describe what the code now does. The code is right; the spec moves.

## Requirements

### Requirement: Code drift detection

`drift.py check` SHALL report each capability as `in-sync`, `code-moved` (listing the files added, removed or edited since the last stamp), `no-spec` or `no-anchors`, using only git and file hashes. It SHALL exit 1 when anything drifted.

- **Scenario: Anchored file edited**
  - **GIVEN** a capability was stamped
  - **WHEN** one of its anchored files changes
  - **THEN** check lists that capability as `code-moved` with that file, and exits 1

### Requirement: Stamping

`drift.py stamp` SHALL record a content hash per anchored file and the commit holding the synced code. It SHALL warn when anchored files are uncommitted.

- **Scenario: Uncommitted code**
  - **WHEN** stamp runs while anchored files have uncommitted changes
  - **THEN** it warns that `syncedCommit` would predate that code

### Requirement: Anchor helpers

`drift.py files <capability> [anchor…]` SHALL list the files a capability's anchors match, or the given anchors instead, writing nothing. `drift.py unanchored [--since REF]` SHALL list changed files that no capability covers. `drift.py overlaps [--json]` SHALL list files matched by two or more capabilities, with the capabilities and the anchors that match. `drift.py rename <old> <new>` SHALL move a capability's key and baseline file, keeping its stamps, and refuse when a baseline already sits at the new name. `drift.py prune <capability>` SHALL drop the stamps of files its anchors no longer match, keeping the rest. `drift.py version` SHALL print the format version of `blueprint.json`, 1 when absent. Anchors SHALL be git-style globs with `**` and `!` exclusions.

- **Scenario: Excluded tests**
  - **GIVEN** anchors `["src/auth/**", "!**/*.test.ts"]`
  - **WHEN** files are listed
  - **THEN** test files under `src/auth/` are not included
- **Scenario: Overlap listed**
  - **GIVEN** two capabilities whose anchors both match `worker/index.ts`
  - **WHEN** `drift.py overlaps` runs
  - **THEN** `worker/index.ts` is listed once with both capabilities

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
