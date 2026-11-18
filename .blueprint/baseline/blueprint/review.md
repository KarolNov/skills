## Purpose

Applies a review submitted from the pane to the page it was written on, through blueprint's own backend rules.

## Requirements

### Requirement: Batch applied as one

`/blueprint review <file>` SHALL turn every item into an edit, show all edits as one preview, and write them on a single yes. Suggestions SHALL be applied word for word. Comments it can't turn into an edit SHALL be asked about before the preview.

- **Scenario: Clear batch**
  - **GIVEN** a file with two suggestions and one comment asking to drop a scenario
  - **WHEN** `/blueprint review <file>` runs
  - **THEN** one preview shows all three edits, and nothing is written until the user says yes
- **Scenario: Vague comment**
  - **WHEN** a comment says only "unclear"
  - **THEN** blueprint asks what it should say instead before showing the preview

### Requirement: Anchors found by quote and heading

Each item SHALL be located by its quote under its heading in the page as it reads now. An item whose anchor can't be found SHALL be listed back to the user, not guessed at.

- **Scenario: Page changed since review**
  - **GIVEN** someone rewrote the quoted sentence after the review was made
  - **WHEN** the review is applied
  - **THEN** that item is shown as not found, and the rest are applied

### Requirement: Routed by page kind

Edits to a brief SHALL be made to the brief, then the review rebuilt. Items on a review SHALL become edits to the brief, never to the review. Items on a capability spec that change wording only SHALL be applied with the spec bookkeeping. Items that change behavior SHALL be listed back with an offer to start a blueprint.

- **Scenario: Comment on a review**
  - **WHEN** a comment on a review's Decisions asks for a reason
  - **THEN** the brief's decision gains the reason, and the review is rebuilt from it
- **Scenario: Behavior change on a spec**
  - **WHEN** a suggestion on a spec changes what a requirement does
  - **THEN** the spec is not edited, and blueprint offers `/blueprint` with that change
