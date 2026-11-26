## Purpose

Bring an existing repo fully under blueprint in passes that can run in separate sessions: domains, capabilities with anchors, reviewed specs, test tags and artifacts, with progress kept in the repo until it is done.

## Requirements

### Requirement: Passes

`/blueprint-backfill` SHALL run five passes in order: survey and domains; capabilities and anchors per domain; spec drafts and scenario review per domain; test tags per domain; artifacts per domain. Pass 1 SHALL run in one session; passes 2 to 5 SHALL run per domain, each domain in its own session if the user wants.

- **Scenario: Start a backfill**
  - **GIVEN** a repo with no `.blueprint/backfill/`
  - **WHEN** the user runs `/blueprint-backfill`
  - **THEN** pass 1 surveys the repo, interviews the user, and proposes domains for the user to accept
- **Scenario: Next sessions named**
  - **WHEN** the user accepts the domains at the end of pass 1
  - **THEN** backfill lists one `/blueprint-backfill domain <name>` command per domain

### Requirement: Progress kept in the repo

Backfill SHALL keep its progress in `.blueprint/backfill/`: `progress.json` with the survey's plan and each pass's and domain's status, one `domains/<domain>.progress.json` per domain, `drafts/<capability>.md` for specs awaiting review, and a `README.md` saying a blueprint backfill is in progress, at which pass, how to resume, and that the folder is deleted when the backfill finishes. The folder SHALL be committed as the backfill goes.

- **Scenario: Resume in a new session**
  - **GIVEN** pass 2 is done for `auth` and not started for `billing`
  - **WHEN** the user runs `/blueprint-backfill` in another session
  - **THEN** it reports where things stand and offers to continue with `billing`
- **Scenario: README explains the folder**
  - **WHEN** pass 1 writes `.blueprint/backfill/`
  - **THEN** its `README.md` names the backfill, the current pass, and `/blueprint-backfill` as the way to resume

### Requirement: Capabilities and anchors per domain

In pass 2, backfill SHALL find a domain's capabilities one at a time, each with anchors and named by the domain naming rule, and the user SHALL confirm each. A domain SHALL count as covered when no tracked file in its folders from the survey is left without an anchor, apart from files the user marks as glue, and the user confirms it. Capabilities already in `blueprint.json` SHALL be kept and listed as found.

- **Scenario: Domain not yet covered**
  - **GIVEN** two files under `auth`'s folders match no capability's anchors and are not marked glue
  - **WHEN** pass 2 checks the domain
  - **THEN** it names both files and proposes a capability or anchors for them
- **Scenario: Existing capability kept**
  - **GIVEN** `auth/session` is already in `blueprint.json`
  - **WHEN** pass 2 runs for `auth`
  - **THEN** `auth/session` is listed as found with its anchors unchanged

### Requirement: Domain sessions don't write `blueprint.json`

A domain session SHALL record its capabilities, anchors, spec refs and stamps only in its own domain progress file, and its baselines under `.blueprint/baseline/<domain>/`. `/blueprint-backfill fold` SHALL merge every finished domain into `blueprint.json` at once and mark it folded. Until a domain is folded, its new capabilities SHALL NOT appear in `drift.py check`.

- **Scenario: Two domains in parallel**
  - **GIVEN** sessions for `auth` and `billing` run on separate branches
  - **WHEN** both branches merge
  - **THEN** neither touched `blueprint.json`, and their progress and baseline files don't conflict
- **Scenario: Fold**
  - **GIVEN** `auth` and `billing` have finished scenario review
  - **WHEN** the user runs `/blueprint-backfill fold`
  - **THEN** both domains' capabilities are in `blueprint.json` with their refs and stamps, and `drift.py check` lists them in sync

### Requirement: Specs drafted from code and reviewed by scenario

In pass 3, backfill SHALL draft each capability with no spec from its anchored code by sync's draft-from-code rules into `drafts/<capability>.md`, then put each scenario to the user as one card: the scenario, its requirement's statement above it (editable on the requirement's first card only), and any verify mark as the question to settle, with Accept, Amend and Reject. Reject SHALL drop the scenario, and a requirement whose scenarios are all rejected SHALL be dropped. Once every card of a capability is decided, backfill SHALL create its spec page inside its domain and do the spec bookkeeping; decisions SHALL be saved as they are made.

- **Scenario: Amend a scenario**
  - **WHEN** the user amends a scenario's THEN and saves
  - **THEN** the draft holds the new text and the next card is shown
- **Scenario: Last card decided**
  - **GIVEN** one undecided card left on `auth/tokens`
  - **WHEN** the user accepts it
  - **THEN** the `auth/tokens` spec page is created with the accepted requirements and its baseline written
- **Scenario: Review without the pane**
  - **GIVEN** `blueprint-ui` is not installed
  - **WHEN** pass 3 reaches review
  - **THEN** the same cards are asked in chat

### Requirement: Test tags and artifacts passes

Pass 4 SHALL run coverage's suggest for each of the folded domain's capabilities. Pass 5 SHALL ask the user once per domain which outside resources describe its capabilities and record each with `drift.py artifacts add`; it SHALL NOT search for artifacts.

- **Scenario: Artifacts asked**
  - **WHEN** pass 5 runs for `auth`
  - **THEN** backfill asks one question for `auth`'s outside docs and adds only what the user names

### Requirement: Finish

When every domain has finished pass 5 and been folded, backfill SHALL delete `.blueprint/backfill/` and report the domains, capabilities, scenarios accepted, amended and rejected, tags added and artifacts recorded.

- **Scenario: Last pass done**
  - **GIVEN** every domain has finished pass 5 and is folded
  - **WHEN** the last pass completes
  - **THEN** `.blueprint/backfill/` is gone and the report lists what the backfill wrote
