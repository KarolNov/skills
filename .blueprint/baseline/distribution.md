## Purpose

Makes the repo's skills and mods installable as Claude Code plugins from one marketplace, and documents how to install and add them.

## Requirements

### Requirement: One marketplace for the repo

The repo SHALL publish one plugin marketplace, `karolnov-skills`, in `.claude-plugin/marketplace.json`, and every skill in `skills/` SHALL belong to exactly one plugin in it.

- **Scenario: Install a plugin**
  - **GIVEN** the user ran `/plugin marketplace add KarolNov/skills`
  - **WHEN** they run `/plugin install blueprint@karolnov-skills`
  - **THEN** every skill listed in the blueprint plugin is installed

### Requirement: Plugins group skill families

Skills that are used together SHALL ship as one plugin, so that one install gets the whole family.

- **Scenario: Blueprint family**
  - **WHEN** the blueprint plugin is installed
  - **THEN** `blueprint-setup`, `blueprint`, `blueprint-ask`, `blueprint-drift`, `blueprint-sync`, `blueprint-tidy` and `blueprint-backfill` are all available

### Requirement: README documents every plugin

The README SHALL give the install commands for every plugin, a section per plugin describing what its skills do and what they need, and steps for adding a new skill.

- **Scenario: New plugin added**
  - **WHEN** a plugin is added to the marketplace
  - **THEN** the README gains its install line and its section

### Requirement: Manual install

Each skill SHALL also work when its folder is copied into a personal or project skills directory, without the marketplace.

- **Scenario: Copied skill**
  - **WHEN** the user copies `skills/slack-nag` to `~/.claude/skills/`
  - **THEN** `/slack-nag` is available

### Requirement: Mods ship beside skills

A mod SHALL live in `mods/<name>/` with its own plugin manifest, and SHALL be listed in the marketplace as its own plugin. The README SHALL install it next to the skills it extends.

- **Scenario: Install the review pane**
  - **WHEN** the user runs `/plugin install blueprint-ui@karolnov-skills`
  - **THEN** the `blueprint-ui` mod loads, and `/blueprint-ui` is available
