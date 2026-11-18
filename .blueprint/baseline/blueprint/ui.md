## Purpose

A pane beside the chat that shows blueprint pages read-only and lets the user review them like a GitHub pull request, handing the review to blueprint to apply.

## Requirements

### Requirement: Open the pane

`/blueprint-ui` SHALL open the pane, listing the changes (review and brief) and specs that `.blueprint/blueprint.json` maps. `/blueprint-ui <change or capability>` SHALL open that page directly.

- **Scenario: Picker**
  - **GIVEN** `blueprint.json` maps two changes and six specs
  - **WHEN** the user runs `/blueprint-ui`
  - **THEN** the pane lists them, and choosing one shows its page
- **Scenario: Repo not set up**
  - **GIVEN** the session's repo has no `.blueprint/blueprint.json`
  - **WHEN** the user runs `/blueprint-ui`
  - **THEN** the pane says so and suggests `/blueprint-setup`

### Requirement: Opens after a blueprint write

When a tool call whose arguments name a page that `blueprint.json` maps finishes, the pane SHALL open on that page, or refresh it if it is already showing it.

- **Scenario: Brief rewritten**
  - **WHEN** blueprint updates a change's brief in Notion
  - **THEN** the pane shows that brief as it now reads
- **Scenario: Unrelated page**
  - **WHEN** a tool call writes a Notion page that `blueprint.json` doesn't map
  - **THEN** the pane does not open or change

### Requirement: Read-only rendering

The pane SHALL draw the page's text block by block and SHALL never write to the backend. Images, diagrams and embedded playgrounds SHALL appear as links that open them in the backend.

- **Scenario: Review with diagrams**
  - **WHEN** a review with two diagram images and a playground is shown
  - **THEN** each appears as an "Open in Notion" link at its place, and the text around them reads as in Notion

### Requirement: Reads Notion through the session

The pane SHALL read Notion pages through the session's own Notion connection: the server named by a setting that defaults to `claude.ai Notion`, else the connected server that has `notion-fetch`. It SHALL clean them with the same normalization blueprint uses for baselines.

- **Scenario: No Notion connection**
  - **WHEN** no connected server answers under the configured name
  - **THEN** the pane says which names it tried, the last error, and how to change the setting
- **Scenario: Other backend**
  - **WHEN** `docs.backend` is not `notion`
  - **THEN** the pane says that backend is not supported yet and links the page

### Requirement: Comment or suggest on a block

Each block SHALL offer Comment and Suggest through a "+" beside it. Every item SHALL carry the block's heading and the block's text as its quote. Suggest SHALL start from the block's own text, so the user edits it in place.

- **Scenario: Comment on a block**
  - **WHEN** the user presses "+" on a scenario, chooses Comment and writes "why five?"
  - **THEN** a pending comment holds that requirement's heading, the scenario's text as its quote, and "why five?"
- **Scenario: Suggest wording**
  - **WHEN** the user presses Suggest on a requirement's text, edits it and saves
  - **THEN** a pending suggestion holds the block's heading, the original text as its quote, and the new text

### Requirement: Pending review

Comments and suggestions SHALL build up as a pending review that is shown with its count and survives until it is submitted, discarded or the session ends. Each pending item SHALL be removable.

- **Scenario: Switch pages**
  - **GIVEN** two pending comments on a brief
  - **WHEN** the user opens a spec and comes back
  - **THEN** both comments are still pending

### Requirement: Submit review

"Submit review" SHALL write the pending review as one JSON file (page, kind, link, and for each item its heading, quote, kind and text) and run `/blueprint review <file>`, then clear the batch.

- **Scenario: Submit**
  - **GIVEN** three pending items on a brief
  - **WHEN** the user presses "Submit review"
  - **THEN** `/blueprint review` runs with the file, the transcript shows a one-line summary, and the pending count is zero

### Requirement: Outdated comments

After the page refreshes, a pending item whose quote no longer appears SHALL be marked outdated and kept, not dropped.

- **Scenario: Quote edited away**
  - **GIVEN** a pending comment quoting a sentence
  - **WHEN** the page is refreshed and that sentence is gone
  - **THEN** the comment shows as outdated, with its quote

### Requirement: Same pane in terminal and desktop

The pane SHALL use only elements the terminal and the desktop app both draw, so it behaves the same in each.

- **Scenario: Desktop**
  - **WHEN** the pane is opened in the desktop app
  - **THEN** it offers the same pages, buttons and inputs as in the terminal
