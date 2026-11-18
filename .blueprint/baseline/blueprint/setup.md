## Purpose

Connects a repo to blueprint once: finds where the team already tracks projects and tickets, agrees with the user where specs and tickets go, maps the repo's capabilities to code, and writes `.blueprint/`.

## Requirements

### Requirement: Read-only survey first

Setup SHALL first survey without writing anything: the repo's remote, issues, labels and spec material; the reachable tools; and where projects and tickets are tracked. It SHALL summarize what it found in a few lines.

- **Scenario: Project row exists**
  - **GIVEN** a Notion database has a row for the repo
  - **WHEN** setup surveys
  - **THEN** it reads that database's schema and description and reports where tickets are said to live

### Requirement: One decision round

Setup SHALL ask about docs backend and location, ticket tracker, and project link in one round, each with a recommendation drawn from the survey. A place the user names SHALL win.

- **Scenario: User names a location**
  - **WHEN** the arguments say "Notion, under the project's page"
  - **THEN** that location is used and the docs question is not asked again

### Requirement: Create only after yes

Setup SHALL list the pages, databases, folders or labels it will create and where, and create them only after the user's yes. It SHALL reuse existing structure and never change the team's existing databases unless the user asks.

- **Scenario: Labels in a public tracker**
  - **WHEN** setup needs a label in a shared or public tracker
  - **THEN** it names the label and the repo or team when asking

### Requirement: Capability map

Setup SHALL propose 4 to 15 capabilities in the repo's own vocabulary, each with anchors. It SHALL show them as one table, flag observable code that no capability covers, and iterate until the user accepts.

- **Scenario: Existing OpenSpec specs**
  - **GIVEN** the repo has `openspec/specs/`
  - **WHEN** the map is proposed
  - **THEN** setup offers to import each spec as a capability spec, with scenarios turned into list items

### Requirement: Seeding is optional

Setup SHALL ask whether to write specs now or lazily. Lazy capabilities get `"ref": null`. Specs written now SHALL be drafted from the code, mark accidental-looking behavior for the user to verify, and be written only after approval, followed by the bookkeeping.

- **Scenario: Lazy seeding**
  - **WHEN** the user chooses lazily
  - **THEN** each capability is recorded with `"ref": null` and no spec pages are created

### Requirement: Repo files written

Setup SHALL write `.blueprint/blueprint.json`, a fresh copy of `drift.py`, a fresh copy of `notion_normalize.py` when the backend is Notion, a `baseline/` folder with a baseline for every existing spec, and a short `README.md`. It SHALL commit nothing, and SHALL only offer the `CLAUDE.md` line and a drift guard, adding them on a yes.

- **Scenario: Rerun**
  - **GIVEN** `.blueprint/` already exists
  - **WHEN** setup runs again
  - **THEN** it updates location, capabilities, `drift.py` and `notion_normalize.py` without losing recorded specs or changes

### Requirement: Pending mode for repos that don't exist yet

When the target repo doesn't exist yet, setup SHALL still decide docs, tickets and project. It SHALL skip the capability map and seeding, and write `blueprint.json` with `targetRepo` and `baseline/` to `~/.blueprint/pending/<repo name>/`.

- **Scenario: Extraction**
  - **WHEN** a change will create a new repo
  - **THEN** the setup is pending in the home folder until apply's first task creates the repo
