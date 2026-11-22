## Purpose

Keeps a repo's blueprint structure healthy as it grows: migrates `.blueprint/` and the backend to the current format, groups capabilities into domains, and reports overlapping anchors, writing only what the user approves.

## Requirements

### Requirement: Migrate first

Tidy SHALL read `version` from `blueprint.json` (absent means 1) and, when it is older than the plugin's current format version, apply each pending entry of the upgrades ledger in order before anything else. It SHALL show the migration's writes and apply them after the user's yes, then record the new `version`. When the user declines, it SHALL stop.

- **Scenario: Version 1 repo**
  - **GIVEN** `blueprint.json` has no `version` field
  - **WHEN** `/blueprint-tidy` runs
  - **THEN** it shows the v1→v2 migration, applies it on a yes, and `blueprint.json` reads `version: 2` with an empty `domains` map
- **Scenario: Already current**
  - **WHEN** the version matches the plugin's
  - **THEN** tidy says so in one line and goes straight to grouping

### Requirement: Dry run

With `--dry-run`, tidy SHALL show the migration and the move table and stop without writing anything.

- **Scenario: Preview on an old repo**
  - **GIVEN** a version 1 repo
  - **WHEN** `/blueprint-tidy --dry-run` runs
  - **THEN** it shows the migration and the move table, and no file or page changes

### Requirement: Domains proposed from names and anchors

Tidy SHALL propose domains by grouping capabilities that share a name prefix or a top-level anchor folder, each with a one-line purpose. It SHALL propose a rename for every name that is both a capability and a domain, and SHALL never propose domains deeper than one level.

- **Scenario: Leaf and parent collide**
  - **GIVEN** capabilities `board` and `board/ops`
  - **WHEN** tidy proposes domains
  - **THEN** it proposes domain `board`, keeps `board/ops`, and proposes a new name for `board` such as `board/session` for the user to pick

### Requirement: Overlapping anchors reported

Tidy SHALL list files matched by two or more capabilities (from `drift.py overlaps`), and for overlaps caused by a broad glob propose a narrower anchor. It SHALL check which files a narrower anchor drops and never leave one unanchored without saying so. It SHALL never change anchors without approval, and SHALL leave overlaps the user marks as intended.

- **Scenario: Broad glob**
  - **GIVEN** `jams` anchors `shared/**` and `board/ops` anchors `shared/board/**`
  - **WHEN** tidy reports overlaps
  - **THEN** it lists `shared/board/*` under both and proposes narrowing `jams`

### Requirement: One approved move table

Tidy SHALL show every proposed change (new domains, renames, moves, anchor edits) as one table and write nothing until the user approves it. On approval it SHALL apply the whole table: backend titles, parents and paths; `blueprint.json` keys; `baseline/` files; tests' `@scenario` tags; domain overview pages; and open blueprints that name a renamed capability, whose reviews it rebuilds. A blueprint SHALL count as open when either `changes` or the backend marks it so, and a status that differs between the two SHALL be reported, not changed.

- **Scenario: Rename with an open blueprint**
  - **GIVEN** an approved blueprint touches `board`
  - **WHEN** `board` is renamed to `board/session`
  - **THEN** the brief's capabilities and spec delta headings read `board/session`, its review is rebuilt, and `drift.py check` reports the same status as before the rename

### Requirement: Renames keep history

A rename SHALL keep the backend page (and its history) and only change its title, parent or path; `specVersion` and `syncedCommit` SHALL carry over, so a rename never reads as drift.

- **Scenario: Status after tidy**
  - **WHEN** tidy finishes on a repo that was in sync
  - **THEN** `drift.py check` still reports every capability in sync under its new name
