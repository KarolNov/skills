# Blueprint

[Claude Code](https://claude.com/claude-code) skills for architecting larger changes: you bring
the solution, blueprint grills it, writes it up as a spec change in your notes tool, builds it,
and keeps the capability specs and the code honest in both directions.

**Documentation: [blueprint.karolnov.dev](https://blueprint.karolnov.dev)**: getting started, every
mode, the review pane, backends, upgrading, and this repo's own capability map.

## Install

In Claude Code:

```
/plugin marketplace add KarolNov/skills
/plugin install blueprint@karolnov-skills
/plugin install blueprint-ui@karolnov-skills   # the review pane for blueprint
```

Or copy the whole blueprint family by hand (the skills link to each other's references, so copy
them together):

```bash
git clone https://github.com/KarolNov/skills.git
cp -r skills/skills/blueprint* ~/.claude/skills/        # all projects
cp -r skills/skills/blueprint* .claude/skills/          # one project
```

**Needs:** Python 3, git, and the connector for your backend (Notion, Linear, Atlassian) or `gh`.

## Skills

### blueprint

| Mode | What it does |
| ---- | ------------ |
| [`/blueprint-setup`](https://blueprint.karolnov.dev/modes/setup) | Once per repo: picks where specs, blueprints and tickets live, maps capabilities to code, writes `.blueprint/`. |
| [`/blueprint <your solution>`](https://blueprint.karolnov.dev/modes/propose) | Grills your solution in a few short rounds and writes a blueprint: a brief for agents and a visual review for people. |
| [`/blueprint apply [change]`](https://blueprint.karolnov.dev/modes/apply) | Builds it task by task (split into PRs when big), verifies it, and folds the delta into the specs. |
| [`/blueprint map`](https://blueprint.karolnov.dev/modes/map) | One local page of capabilities, domains, shared files, drift and coverage, with search. |
| [`/blueprint coverage`](https://blueprint.karolnov.dev/modes/coverage) | Traces spec scenarios to the tests tagged as claiming them; reports gaps and orphan tags. |
| [`/blueprint-ask <question>`](https://blueprint.karolnov.dev/modes/ask) | Answers how a feature should work from the specs, after checking they still match the code. Read only. |
| [`/blueprint-drift [capability]`](https://blueprint.karolnov.dev/modes/drift) | The spec is right: fixes the code that strayed from it. |
| [`/blueprint-sync [capability]`](https://blueprint.karolnov.dev/modes/sync) | The code is right: updates the spec to match it. |
| [`/blueprint-tidy`](https://blueprint.karolnov.dev/modes/tidy) | Groups capabilities into domains and migrates older setups. |
| [`/blueprint-backfill`](https://blueprint.karolnov.dev/modes/backfill) | Brings an existing repo fully under blueprint in passes across sessions. |

**Review pane (`blueprint-ui`):** a mod that shows reviews, briefs and specs beside the chat
(`/blueprint-ui`), and batches comments into one review for `/blueprint review`. Install it next to
`blueprint`. [More](https://blueprint.karolnov.dev/review-pane).

This repo runs blueprint on itself: see [`.blueprint/`](.blueprint/), its
[specs and blueprints in Notion](https://app.notion.com/p/41c43cce21f2819ba9e9e27bc322d312) and its
[capability map](https://blueprint.karolnov.dev/capability-map).

## Docs site

The site in [`docs/`](docs/) is built with VitePress and served by a Cloudflare Worker
([`wrangler.jsonc`](wrangler.jsonc)) through Workers Builds: `main` publishes, every other branch
gets a preview. `npm run docs:dev` runs it locally; `npm run docs:build` writes the map with
`graph.py --no-drift` and builds the site.

## Repository layout

```
.claude-plugin/marketplace.json   # plugin marketplace manifest
skills/<skill-name>/SKILL.md      # one folder per skill
mods/<mod-name>/                  # one folder per mod (its own plugin manifest and hooks module)
template/SKILL.md                 # starting point for a new blueprint skill
docs/                             # the docs site (VitePress), served at blueprint.karolnov.dev
```

## Adding a skill

1. Copy `template/` to `skills/blueprint-<name>/` (lowercase, hyphenated).
2. Fill in the `name` and `description` frontmatter in `SKILL.md`; `name` must match the folder name.
3. Add `"./skills/blueprint-<name>"` to the blueprint plugin's `skills` array in
   `.claude-plugin/marketplace.json`.
4. Add its mode to the table in the README, and a page for it under `docs/modes/` (linked from
   the sidebar in `docs/.vitepress/config.mts`).

## Adding a mod

A mod (a Claude Code plugin with a hooks module: panes, commands, hooks) lives in `mods/<mod-name>/`
with its own `.claude-plugin/plugin.json`, and gets its own plugin entry in
`.claude-plugin/marketplace.json` with `"source": "./mods/<mod-name>"`. Add its install line and a
paragraph to the README next to the skills it extends. Check it with `claude plugin validate` and
`claude plugin test` on its folder.

## License

[MIT](LICENSE)
