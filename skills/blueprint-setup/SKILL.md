---
name: blueprint-setup
description: One-time setup for /blueprint in a repo. Finds where the team already tracks projects and tickets, picks where specs and blueprints live and where their tasks become tickets, maps the repo's capabilities to code, and writes .blueprint/.
disable-model-invocation: true
argument-hint: "[where specs should live, e.g. \"Notion, under the project's page\"]"
---

# Blueprint setup

Arguments: `$ARGUMENTS`

Connect this repo to the places its team already works. Setup decides three things:

- **Docs**: where capability specs and blueprints (brief + review) live. Always databases or folders built for them, never loose pages.
- **Tickets**: where a blueprint's tasks become tickets: the tracker the repo already uses, or none.
- **Project**: the existing page, row or project the specs belong to, if the team tracks projects somewhere.

Done once per repo. Rerunning it updates the setup (a new location, new capabilities, a fresh `drift.py`) without losing what `.blueprint/blueprint.json` records. The shared references live in the `blueprint` skill next to this one: `../blueprint/references/`.

## Target repo doesn't exist yet

Some changes create the repo they target (extracting packages into a new library, a new service). Then there is no repo to write `.blueprint/` into, and this setup runs in pending mode:

- Survey and decide docs, tickets and project as usual (steps 1 to 3), from the repo the code comes from and the user's plans for the new one.
- Skip the capability map (step 4) and seeding (step 5): the new repo's capabilities are the blueprint's new capabilities, added when it is proposed.
- Write `blueprint.json` and `baseline/` to the pending folder `~/.blueprint/pending/<new repo name>/`, with `targetRepo` set to the new repo's intended name or URL, and say so in the brief's header (`- Target repo: <name>, created by task 1; setup pending in <folder>`). No `drift.py` and no `README.md` yet.
- The first task of the blueprint creates the repo; `apply` then moves the pending folder in as `.blueprint/` ([../blueprint/references/apply.md](../blueprint/references/apply.md)).

## 1. Survey what exists

Read only; create nothing yet. Gather in parallel:

- **The repo**: its remote; whether its issues are in use (`gh issue list`, labels, milestones); conventions already there, like area labels, a `ready-for-agent` label, or other planning tools' labels; `openspec/`, `docs/`, ADRs, a glossary; an existing `.blueprint/`.
- **Reachable tools**: which connectors this session has (Notion, Linear, Atlassian), `gh auth status`, and folders like an Obsidian vault (a folder with `.obsidian/` under the home directory).
- **Where work is tracked**, in each reachable tool: search for the repo's name and for task, ticket, project and roadmap databases or projects. In Notion, read the schema of any database that has a row for this repo, and its description; descriptions often say where day-to-day tickets live. In Linear or Jira, the team or project whose issues mention the repo.

Summarize in a few lines: where projects are tracked, where tickets are tracked, and anything already set up for specs.

## 2. Decide docs, tickets and project

Ask in one round, each with your recommendation drawn from the survey (format as in [../blueprint/references/propose.md](../blueprint/references/propose.md) step 2):

1. **Docs backend and location**. Recommend the tool where projects are already tracked, and a new subpage of this repo's own project page or row there (e.g. a `Specs & blueprints` page under the repo's row), holding the backend's databases or folders. Choose from the backends in [../blueprint/references/backends/](../blueprint/references/backends/notion.md): `notion`, `obsidian`, `markdown`, `linear`, `jira`, `github`.
2. **Tickets**. Recommend the tracker the repo's tickets already live in, from [../blueprint/references/tickets.md](../blueprint/references/tickets.md): `github`, `linear`, `jira`, `notion` (an existing tasks database, or a new `Tasks` database under the specs root when the team has none or the user asks for one), or `none` (tasks stay as checkboxes in the brief). Docs and tickets may live in different tools.
3. **Project link**. The URL of the existing project page, row or project, recorded so blueprints can point back to it.

Leave what the team already has untouched: existing databases keep their schema, rows and views, and new structure goes beside them, never inside them, unless the user asks for that. If the user names a place in the arguments or their answer, that wins.

## 3. Create the structure

Show what will be created and where (a short list of pages, databases or folders, and their parent), and create it after the user's yes:

- **Docs**: follow the chosen backend file's "Set up" section. Reuse what exists; create only what is missing.
- **Tickets**: follow the tracker's "Set up" section in `tickets.md`: usually one label to mark blueprint tickets, and reading the tracker's statuses so they can be mapped. Creating labels in a shared or public tracker is outward-facing: name the label and the repo or team when asking.

## 4. Map the capabilities

Survey the repo with a subagent: entry points, top-level modules, public APIs, routes, jobs, and any existing spec material. From that, propose a **capability map**: 4 to 15 capabilities, each a durable behavior boundary named in the repo's own vocabulary (`billing/invoices`, not `invoice-service-refactor`), each with its anchors.

Present it as one table: capability, one-line purpose, anchors. Flag code that no capability covers; that is fine for glue, build config and tests, and worth a capability for anything a user can observe. The user edits the table; iterate until they accept it.

If the repo already has OpenSpec specs, offer to import them: each `openspec/specs/<path>/spec.md` becomes a capability spec page with the same requirements, its `#### Scenario:` headings turned into scenario list items, and the user picks anchors for each.

## 5. Seed the specs (optional)

Ask whether to write the capability specs now or lazily:

- **Lazily** (the default): capabilities get `"ref": null`. A spec page is created the first time a blueprint or sync touches that capability.
- **Now**, for all or selected capabilities: for each, read its anchored code and draft the spec **from the code** (as the `blueprint-sync` skill does for a capability with no spec), describing what the code does today, including behavior that looks accidental; mark those with `<!-- verify: … -->` so the user can decide. Show each draft, write it after approval, and do the spec bookkeeping from [../blueprint/references/status.md](../blueprint/references/status.md).

## 6. Write `.blueprint/`

- `blueprint.json` in the shape from [../blueprint/references/formats.md](../blueprint/references/formats.md), with the `docs`, `tickets` and `project` choices.
- `drift.py`: copy `../blueprint/scripts/drift.py` (overwrite an older copy).
- `baseline/`: create it, with a baseline for every spec that exists.
- `README.md`: three lines saying where the specs live and where tickets go (with links), that `blueprint.json` and `baseline/` are maintained by `/blueprint`, and that `python3 .blueprint/drift.py check` lists capabilities whose code moved since their spec was synced.

Then offer one line for `CLAUDE.md` / `AGENTS.md` (only add it on a yes):

```markdown
Specs for this repo live in <docs link>; `.blueprint/blueprint.json` maps capabilities to code. After changing behavior in an anchored area on purpose, run `/blueprint-sync <capability>`; to check the code still does what the specs say, run `/blueprint-drift`.
```

## 7. Drift guard (optional)

Offer one, never install without a yes. Each runs `python3 .blueprint/drift.py check`, which exits 1 when code moved since its spec was synced:

- **pre-push hook** that warns and lets the push through (`|| true`), installed via the repo's existing hook manager (husky, lefthook, pre-commit) if it has one, otherwise `.git/hooks/pre-push`.
- **CI step** that comments or fails on drift, added to the existing workflow.

## Done when

`blueprint.json` records docs, tickets and project, and lists every accepted capability with anchors; `python3 .blueprint/drift.py check` runs clean; and the user has seen where everything lives. Report: the docs location and ticket tracker (linked), the capability table, what was seeded, and the optional pieces that were added. Nothing is committed; tell the user which files to commit. Then suggest `/blueprint <the change you have in mind>`.
