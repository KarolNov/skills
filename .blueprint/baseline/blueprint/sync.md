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
