# Backends

Specs and blueprints live outside the repo, in the tool your team already reads. [Setup](/modes/setup) picks one. Only `.blueprint/` lives with the code.

| Backend | Specs | Blueprints | Needs |
| --- | --- | --- | --- |
| **Notion** (default) | pages in a Specs database, grouped by domain | pages in a Blueprints database, brief and review side by side | the Notion connector |
| **Obsidian** | notes in a vault, one folder per domain | notes in the vault | nothing: plain files |
| **Markdown folder** | files in a folder outside the repo (a notes repo, a shared drive) | files in the same folder | nothing: plain files |
| **Linear** | Linear documents | issues | the Linear connector |
| **Jira + Confluence** | Confluence pages | Jira epics | the Atlassian connector |
| **GitHub** | the repo's wiki (its own git repository) | issues | the `gh` CLI |

## Tickets can live elsewhere

A blueprint's tasks can become tickets in a different tool from the docs. For example, specs and blueprints can sit in Notion under the project's page while tasks are GitHub issues in the repo. Trackers: GitHub issues, Linear, Jira, a Notion tasks database (the team's own, or a new one next to the specs), or none.

## Visuals

Diagrams and playgrounds appear only in reviews, so specs and briefs stay plain text that agents read cheaply and diffs stay clean. In Notion, diagrams go in as rendered images with their Mermaid source in a toggle underneath, and a playground runs inside the review as an embedded HTML block.

## What lives in the repo

```
.blueprint/
├── blueprint.json     # capabilities → pages and anchors (code globs), domains, sync stamps, artifacts
├── baseline/          # each spec's text as of its last sync: the merge base
└── drift.py           # tells from git alone which capabilities' code moved
```

This repo runs blueprint on itself. Its specs and blueprints are [public in Notion](https://app.notion.com/p/41c43cce21f2819ba9e9e27bc322d312), and its [`.blueprint/`](https://github.com/KarolNov/skills/tree/main/.blueprint) is in the repo.
