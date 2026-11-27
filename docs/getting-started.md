# Getting started

## Install

Blueprint ships as a Claude Code plugin marketplace. In Claude Code:

```
/plugin marketplace add KarolNov/skills
/plugin install blueprint@karolnov-skills
/plugin install blueprint-ui@karolnov-skills   # optional: the review pane
```

Or copy the skills by hand. They link to each other's references, so copy the whole family together:

```bash
git clone https://github.com/KarolNov/skills.git
cp -r skills/skills/blueprint* ~/.claude/skills/        # all projects
cp -r skills/skills/blueprint* .claude/skills/          # one project
```

**Needs:** Python 3, git, and the connector for your backend (Notion, Linear or Atlassian) or the `gh` CLI. To render diagrams as images for Notion, you also need Python Playwright with Chromium (`pip install playwright && playwright install chromium`).

## Set up a repo

Run [`/blueprint-setup`](/modes/setup) once per repo. It looks at where you already track projects and tickets, then suggests where specs and blueprints should live. It also maps the repo's capabilities to their code, and writes `.blueprint/`. Nothing is written until you say yes.

For a large existing codebase (more than about 15 capabilities), setup suggests [`/blueprint-backfill`](/modes/backfill). Backfill brings the repo under blueprint in passes that can be spread across sessions.

## Your first blueprint

Describe the change you already have in mind:

```
/blueprint move session storage from cookies to Redis, keyed by user id, with a 30-day sliding expiry
```

Blueprint plays the solution back with a rough before/after sketch, then asks a few short rounds of questions. Once you approve, it writes the brief and the review. Then:

```
/blueprint apply
```

This builds the blueprint task by task. It checks each requirement against the code and folds the change into the capability specs. [Propose](/modes/propose) and [Apply](/modes/apply) have the details.

## Day to day

| You want to… | Run |
| --- | --- |
| Plan and build a larger change | [`/blueprint <solution>`](/modes/propose), then [`/blueprint apply`](/modes/apply) |
| Know how a feature should work | [`/blueprint-ask <question>`](/modes/ask) |
| See the capabilities, their files and drift | [`/blueprint map`](/modes/map) |
| See which spec scenarios have tests | [`/blueprint coverage`](/modes/coverage) |
| Fix code that strayed from its spec | [`/blueprint-drift`](/modes/drift) |
| Update specs after the code moved on purpose | [`/blueprint-sync`](/modes/sync) |
| Group capabilities into domains, or migrate an old setup | [`/blueprint-tidy`](/modes/tidy) |
