## Purpose

Publishes blueprint's documentation as a public website at `blueprint.karolnov.dev`, rebuilt from the repo on every change, with this repo's own capability map embedded.

## Requirements

### Requirement: Published from main

Every push to `main` SHALL rebuild the site and publish it at [https://blueprint.karolnov.dev](https://blueprint.karolnov.dev), so the site always reflects the latest `main`.

- **Scenario: Merge publishes**
  - **GIVEN** a PR that edits a docs page
  - **WHEN** it is merged to `main`
  - **THEN** `blueprint.karolnov.dev` shows the edited page once the build finishes
- **Scenario: Failed build**
  - **WHEN** a build of `main` fails
  - **THEN** the site keeps serving the last version that built

### Requirement: Preview per branch

A push to any branch other than `main` SHALL build the site as a preview at its own URL and post that URL on the branch's pull request, without changing the published site.

- **Scenario: PR preview**
  - **GIVEN** an open PR that changes a docs page
  - **WHEN** a commit is pushed to its branch
  - **THEN** the PR gets a comment with a preview URL that shows the change, and `blueprint.karolnov.dev` is unchanged

### Requirement: Pages for people

The site SHALL have a getting-started page, a page for each blueprint mode, and pages for the review pane, the backends and upgrading, all reachable from its navigation and searchable from the site's search.

- **Scenario: Find a mode**
  - **WHEN** a visitor searches the site for "coverage"
  - **THEN** the coverage page is among the results and opens from them

### Requirement: Live capability map

The site SHALL have a Capability map page that shows this repo's interactive capability map, built from the same commit as the rest of the site, with drift left out, and SHALL say where drift is shown instead.

- **Scenario: Map matches the commit**
  - **GIVEN** a commit adds a capability to `.blueprint/blueprint.json`
  - **WHEN** the site is built from that commit
  - **THEN** the Capability map page shows the new capability
- **Scenario: No drift on the public map**
  - **GIVEN** a capability whose code moved since its spec was synced
  - **WHEN** a visitor opens the Capability map page
  - **THEN** the capability is drawn like any other, and the page links to where drift is shown

### Requirement: Builds from the repo alone

Building the site SHALL need nothing but the repo and a standard Node and Python toolchain: no secrets, no connection to the specs backend, and no git history beyond the commit being built.

- **Scenario: Shallow clone builds**
  - **GIVEN** a `--depth 1` clone with no backend credentials
  - **WHEN** `npm ci && npm run docs:build` runs
  - **THEN** the build succeeds and the output contains the map page
