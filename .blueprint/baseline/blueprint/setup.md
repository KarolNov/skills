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

Setup SHALL propose 4 to 15 capabilities in the repo's own vocabulary, each with anchors. When the map has 8 or more and the repo is on the current format version, it SHALL also propose domains, each with a one-line purpose, following the domain naming rule; on an older format it SHALL propose none and leave grouping to `/blueprint-tidy`. It SHALL show them as one table, flag observable code that no capability covers, refuse a map where a name is both a domain and a capability, and iterate until the user accepts.

- **Scenario: Existing OpenSpec specs**
  - **GIVEN** the repo has `openspec/specs/`
  - **WHEN** the map is proposed
  - **THEN** setup offers to import each spec as a capability spec, with scenarios turned into list items
- **Scenario: Large repo**
  - **WHEN** the proposed map has 8 or more capabilities
  - **THEN** the table groups them under proposed domains, and no name is both a domain and a capability

### Requirement: Seeding is optional

Setup SHALL ask whether to write specs now or lazily. Lazy capabilities get `"ref": null`. Specs written now SHALL be drafted from the code, mark accidental-looking behavior for the user to verify, and be written only after approval, followed by the bookkeeping.

- **Scenario: Lazy seeding**
  - **WHEN** the user chooses lazily
  - **THEN** each capability is recorded with `"ref": null` and no spec pages are created

### Requirement: Repo files written

Setup SHALL write `.blueprint/blueprint.json` with a `domains` map and, on a new setup, the current format `version`, a fresh copy of `drift.py` and `drift_ts.mjs`, a fresh copy of `notion_normalize.py` when the backend is Notion, a `baseline/` folder with a baseline for every existing spec, a short `README.md`, and `.gitattributes` lines marking `.blueprint/closure/**`, `.blueprint/drift.py`, `.blueprint/drift_ts.mjs` and `.blueprint/notion_normalize.py` as `linguist-generated=true`, adding only the lines that are missing and keeping the rest of the file. It SHALL create an overview page for each accepted domain, listing a capability without a spec as "no spec yet". It SHALL commit nothing, and SHALL only offer the `CLAUDE.md` line and a drift guard, adding them on a yes.

- **Scenario: Rerun**
  - **GIVEN** `.blueprint/` already exists
  - **WHEN** setup runs again
  - **THEN** it updates location, capabilities, `drift.py`, `drift_ts.mjs`, `notion_normalize.py` and the `.gitattributes` lines without losing recorded specs or changes, and keeps the recorded `version` exactly
- **Scenario: Rerun on an older format**
  - **GIVEN** `.blueprint/` is on an older format version
  - **WHEN** setup runs again
  - **THEN** it points to `/blueprint-tidy` for the migration instead of rewriting the format itself

### Requirement: Pending mode for repos that don't exist yet

When the target repo doesn't exist yet, setup SHALL still decide docs, tickets and project. It SHALL skip the capability map and seeding, and write `blueprint.json` with `targetRepo` and `baseline/` to `~/.blueprint/pending/<repo name>/`.

- **Scenario: Extraction**
  - **WHEN** a change will create a new repo
  - **THEN** the setup is pending in the home folder until apply's first task creates the repo

### Requirement: Drift guard from a template

When the user accepts a CI drift guard, setup SHALL copy the skill's `blueprint-drift.yml` template to `.github/workflows/blueprint-drift.yml`, or, when the repo already has a workflow the user prefers, add the same steps there. The workflow SHALL run `python3 .blueprint/drift.py check` and `python3 .blueprint/drift.py artifacts` on every pull request. When anything drifted, anything is possibly affected, or any artifact is stale, it SHALL keep one PR comment listing the drifted capabilities (`code-moved` and `deps-moved`) with their drift chance, shown as ten squares filled by the chance and colored by the confidence (🟩 high, 🟨 medium, 🟥 low) under a one-line legend, confidence and reasons, then under "Possibly affected" the capabilities below the threshold with the same details, and the stale artifacts with their type, value (linked when it can be) and description, under "Artifacts that may need an update". The comment SHALL be updated on each push and marked back in sync once all three lists are empty. The workflow SHALL emit a warning annotation for each drifted capability and each stale artifact, and none for a possibly affected one; a PR that never drifted and never had a stale artifact gets none. It SHALL fail only when `BLUEPRINT_DRIFT_FAIL` is `"true"` and a capability drifted, never for possibly affected capabilities or stale artifacts alone, and SHALL say that only code-side drift is checked. It SHALL carry an optional, commented-out step that sets up Node and installs dependencies, saying that enabling it raises confidence for TS/JS capabilities. When the repo's `drift.py` has no `artifacts` command, the workflow SHALL skip the artifacts section with a notice. The template SHALL be presented as the recommended shape: the repo owns its copy, and setup SHALL tailor it when the user asks (for example adding a `drifted` label), keeping the drift check.

- **Scenario: Team tailors it**
  - **WHEN** the user asks for a `drifted` label on PRs with drift
  - **THEN** the repo's copy gains a step that adds the label, and the comment, annotations and fail switch keep working
- **Scenario: Drift on a PR**
  - **GIVEN** the template is installed with its defaults
  - **WHEN** a PR changes an anchored file without a sync
  - **THEN** the PR gets one comment naming the capability and file with chance 1.0, a warning annotation, and the check passes
- **Scenario: Possibly affected on a PR**
  - **GIVEN** the template is installed with its defaults
  - **WHEN** a PR changes a symbol three imports away from a capability's anchored code
  - **THEN** the comment lists the capability under "Possibly affected" with its chance, confidence and reason, with no annotation for it
- **Scenario: Stale artifact on a PR**
  - **GIVEN** a `webpage` artifact covering a capability
  - **WHEN** a PR changes a file that capability anchors
  - **THEN** the comment lists the artifact's linked URL and description under "Artifacts that may need an update", and a warning annotation names it
- **Scenario: Second push**
  - **WHEN** a later push to the same PR changes the drift
  - **THEN** the same comment is updated, not a new one added
- **Scenario: Back in sync**
  - **WHEN** a later push to the same PR leaves nothing drifted, nothing possibly affected and no artifact stale
  - **THEN** the same comment says everything is back in sync
- **Scenario: Fork PR**
  - **WHEN** the workflow can't comment because the PR comes from a fork
  - **THEN** the warning annotations still report the drift and the stale artifacts, and the job doesn't fail for that reason
- **Scenario: Strict mode**
  - **GIVEN** `BLUEPRINT_DRIFT_FAIL: "true"`
  - **WHEN** drift is found
  - **THEN** the job fails
- **Scenario: Strict mode, stale artifact only**
  - **GIVEN** `BLUEPRINT_DRIFT_FAIL: "true"`
  - **WHEN** an artifact is stale and no capability drifted
  - **THEN** the job passes and the comment lists the artifact
- **Scenario: Older ****`drift.py`**
  - **GIVEN** the repo's `.blueprint/drift.py` predates artifacts
  - **WHEN** the workflow runs
  - **THEN** capability drift is reported as before and the artifacts section is skipped with a notice

### Requirement: Points to backfill

When the capability map would hold more than 15 capabilities, or the user wants every capability specced now, setup SHALL suggest `/blueprint-backfill` instead of seeding.

- **Scenario: Backfill for a large repo**
  - **WHEN** the survey finds more than 15 candidate capabilities
  - **THEN** setup suggests `/blueprint-backfill` for mapping and speccing them
