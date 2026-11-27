# Setup

```
/blueprint-setup [where specs should live]
```

You run setup once per repo, before anything else. It works out where your specs, blueprints and tickets go, maps the repo's capabilities to their code, and writes `.blueprint/`. If you run another blueprint mode in a repo that isn't set up, it says so and starts setup first.

## What it does

1. **Surveys what you already use.** It checks where the team tracks projects and tickets (a Notion database, Linear, Jira, GitHub issues), so blueprint's pages sit next to the project, not in a new silo.
2. **Proposes where things live.** Specs and blueprints go in one [backend](/backends), as databases or folders under the project's page. Tickets go in a tracker, which can be a different tool. For example, specs can live in Notion while tasks become GitHub issues. You can also have no tickets at all.
3. **Maps the capabilities.** It splits the repo into capabilities (`auth/session`, `billing/invoices`) and gives each one *anchors*: globs for the code that implements it. Related capabilities can share a domain.
4. **Seeds the specs, if you want.** It can draft specs from the code, or import existing OpenSpec specs.
5. **Writes `.blueprint/`.** This holds `blueprint.json` (the map), `baseline/` (spec text as of the last sync) and `drift.py`, which detects drift from git alone.
6. **Adds a drift guard, if you want.** This is a ready-made GitHub Action that comments on each pull request whose code moved away from its specs. See [Drift](/modes/drift#in-ci).

Nothing is written until you approve it.

## Large repos

When a repo has more than about 15 capabilities, setup suggests [Backfill](/modes/backfill). Backfill does the same work in passes, one domain at a time, across as many sessions as it takes.
