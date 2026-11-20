## Purpose

Reads, writes and versions capability specs and blueprints in each supported docs backend, so every other blueprint capability works the same wherever the docs live.

## Requirements

### Requirement: Supported backends

Specs and blueprints SHALL be storable in `notion`, `obsidian`, `markdown`, `linear`, `jira` or `github`, chosen by `docs.backend` in `blueprint.json`. Only the configured backend's instructions SHALL be used.

- **Scenario: Notion configured**
  - **WHEN** `docs.backend` is `notion`
  - **THEN** pages are read and written through the Notion connector, using the Notion backend's rules only

### Requirement: Dedicated structure, not loose pages

Each backend SHALL keep specs and blueprints in a structure built for them, such as databases or folders under one root. It SHALL never add rows or properties to the team's existing databases. The blueprint's own Specs database MAY gain a `Kind` property and sub-items for domains, since that structure is the blueprint's own.

- **Scenario: Existing tracker database**
  - **GIVEN** the team's project database has a row for the repo
  - **WHEN** the backend is set up
  - **THEN** new structure goes under that row's page, and the project database is not changed

### Requirement: Review and brief paired

In each backend a blueprint's brief and review SHALL sit together and link to each other. In Notion the row page is the review and the brief is its child page, `<change>: brief`.

- **Scenario: Opening a blueprint**
  - **WHEN** someone opens a blueprint row in Notion
  - **THEN** they see the review, with the brief as its subpage and in the Brief property

### Requirement: Version marker

Every backend SHALL provide a cheap marker that shows whether a spec or brief changed since it was last read. Notion SHALL use the first 16 hex characters of the SHA-256 of the normalized page body, taken from a read-back after the last write.

- **Scenario: Same-minute edit**
  - **WHEN** a teammate edits a Notion spec in the same minute as a sync
  - **THEN** the marker still changes, because it hashes the content instead of using the edit time

### Requirement: Normalized read-back

Content read back from a backend SHALL be normalized to the formats Markdown before it is compared or saved as a baseline, so that what the backend rewrites on save never reads as drift. For Notion this means undoing HTML inline formatting, escaped list numbers and auto-linked dotted identifiers.

- **Scenario: Auto-linked identifier**
  - **GIVEN** Notion saved the inline code `Y.Map` as an HTML code tag
  - **WHEN** the page is normalized
  - **THEN** it reads as Markdown inline code again and matches the baseline

### Requirement: Visuals placed where the backend renders them

Diagrams SHALL be placed so the backend displays them as pictures. In Notion they are uploaded SVG images with a toggle under each holding the Mermaid source and the diagram's terminal version as a `text` code block, which the `blueprint-ui` pane shows in a terminal in place of the image. The playground is an embedded HTML file in the review.

- **Scenario: Review rebuilt**
  - **WHEN** a Notion review is rebuilt
  - **THEN** fresh images and embeds replace the old blocks, and a read-back confirms each one became a file block

### Requirement: Domains nest like folders

Each backend SHALL store a domain as an overview page that holds its capabilities like a folder: in Notion, a Specs row with `Kind = Domain` whose capability rows set it as their parent item; in Markdown, `specs/<domain>/index.md`; in Obsidian, the folder `<domain>/` with folder note `<domain>/<domain>.md`; in Confluence, a domain page with its capability pages under it. Where pages can't nest (Linear, the GitHub wiki), the overview SHALL be a page titled `Domain: <name>` that links its capabilities, whose titles keep the domain prefix.

- **Scenario: Notion domain**
  - **WHEN** a domain `board` is created in Notion
  - **THEN** the Specs table shows `board` as an expandable row with `board/session` and `board/ops` under it, and opening it shows the overview

### Requirement: Overview is not versioned

A domain overview SHALL hold Purpose, Capabilities (linked, one line each) and How they connect, and SHALL have no baseline, version marker or drift check.

- **Scenario: Edited overview**
  - **WHEN** someone edits a domain overview's How they connect section
  - **THEN** no capability reads as drifted
