# Skills

A collection of [Claude Code](https://claude.com/claude-code) skills I use day to day,
grouped into plugins, plus a mod that extends one of them.

## Install

### As a plugin marketplace (recommended)

In Claude Code:

```
/plugin marketplace add KarolNov/skills
/plugin install walkthrough@karolnov-skills
/plugin install slack-nag@karolnov-skills
/plugin install blueprint@karolnov-skills
/plugin install blueprint-ui@karolnov-skills   # the review pane for blueprint
```

### Manually

Copy skill folders into your personal or project skills directory:

```bash
git clone https://github.com/KarolNov/skills.git
cp -r skills/skills/<skill-name> ~/.claude/skills/        # all projects
cp -r skills/skills/<skill-name> .claude/skills/          # one project
```

## Plugins

### walkthrough

Narrated videos of your real, running web app. Playwright drives the browser, an animated
dot plays the cursor, and a voice explains what's happening. No screen-recording tool and
no hand-built animation needed.

| Skill | What it does | Example |
| ----- | ------------ | ------- |
| [`walkthrough-setup`](skills/walkthrough-setup) | One-time setup: installs Playwright and a narration voice, and saves a login for each app you want to record. | |
| [`design-walkthrough`](skills/design-walkthrough) | A short design review or feature tour: explains *why* the UI is the way it is, letting the page's own motion carry it. | [Sync engine post, 42 s](skills/design-walkthrough/examples/sync-engine-post) |
| [`tutorial-walkthrough`](skills/tutorial-walkthrough) | A step-by-step how-to: performs each click and keystroke with step labels and captions, plus a written version. | [CRDT offline edits, 26 s](skills/tutorial-walkthrough/examples/crdt-offline) |

**Design walkthrough:** a 42-second tour of [a blog post with sync playgrounds](https://karolnov.dev/blog/before-you-build-a-sync-engine/).

https://github.com/user-attachments/assets/bbfa99d5-693f-4a3d-893d-d4cfaf388859

**Tutorial:** merging offline edits in one of its CRDT playgrounds, in four steps.

https://github.com/user-attachments/assets/66856da9-063b-4434-b879-38bbfaeff4e7

**Voices:** [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) (free, local, `af_heart` by
default), [Chatterbox](https://github.com/resemble-ai/chatterbox) (free, local clone of
your own voice), or [ElevenLabs](https://elevenlabs.io) (paid API).

**Logging in:** log in by hand once in a browser window and close it (the session is
reused), or store a test account's credentials and log in automatically.

**Needs:** macOS or Linux, `ffmpeg`, and Python 3.10–3.12 or [`uv`](https://docs.astral.sh/uv/).
`walkthrough-setup` checks for these and installs the rest into `~/.walkthrough/`.

Try it: ask Claude to *"set up walkthrough recording"*, then *"record a design
walkthrough of the new settings page"* or *"make a tutorial on inviting a teammate"*.

Inspired by [brag](https://github.com/latent-spaces/brag) by Shunit Haviv Hakimi (MIT).
brag builds launch videos as HTML compositions; these skills record the real app instead.

### slack-nag

Chase an answer in a Slack thread without doing the chasing yourself. Give it a thread link,
what you're waiting on, and a backoff (default `1 3 5 14`: four nudges, the first a day
from now, each later one that many days after the last); it drafts a schedule of light,
gently escalating nudges and, after you approve them, schedules one task per nudge.
Each task reads the thread first and stays quiet once someone has answered, then deletes
the rest of the series.

| Skill | What it does |
| ----- | ------------ |
| [`slack-nag`](skills/slack-nag) | Drafts and schedules follow-ups at the recipient's 11:00 on weekdays, minding their timezone and daylight saving. |

**Needs:** the Slack connector and the Claude desktop app's scheduled tasks (they run only while
the app is open).

Try it: `/slack-nag https://acme.slack.com/archives/C0123/p1792488185023259 "Dana's sign-off on the Q3 budget" 1 3 5 14`,
or just ask Claude to *"keep nudging Dana in this thread until they reply"*.

### blueprint

My preferred way to work on larger, architected changes, between [wayfinder](https://github.com/mattpocock/skills)
and [OpenSpec](https://github.com/Fission-AI/OpenSpec). You bring the solution; it grills *that*
solution (a few short rounds, no hunt for alternatives), writes it up as a spec change in your
notes tool, builds it, and keeps the specs and the code honest in both directions.

| Mode | What it does |
| ---- | ------------ |
| `/blueprint-setup` | Looks at where you already track projects and tickets, then picks where specs and blueprints live (as databases or folders next to the project), where tasks become tickets, and maps the repo's **capabilities** to code (anchors). Optionally seeds specs from the code or imports OpenSpec specs. |
| `/blueprint <your solution>` | Plays the solution back, sketches it, grills it in at most three rounds of five short questions, and writes a **blueprint** as two linked documents side by side: a text **brief** for agents (decisions, spec delta, tasks; the source of truth) and a visual **review** for people. |
| `/blueprint apply [change]` | Builds the blueprint task by task, verifies each requirement against the code, then folds the delta into the capability specs. |
| `/blueprint map` | Writes `.blueprint/map.html` and opens it: one local page (d3 inlined, works offline) with capabilities as nodes, domains as outlines, lines between capabilities that share files, code-drifted ones in red, a details panel with each capability's requirements and scenarios, and search across names, requirements and file paths. Kept out of git by `.blueprint/.gitignore` and regenerated on demand. |
| `/blueprint coverage [capability \| suggest]` | **Scenario coverage**: a test claims a spec scenario with a comment tag above it, `@scenario <capability>: <scenario name>`, in any language's line comment. Reports per capability which scenarios tests claim, by kind (unit, e2e, … from globs in `blueprint.json`, proposed on first run), the scenarios no test claims, and tags that point at nothing; `suggest` proposes tags for existing tests as a diff. Static: nothing is run, so a scenario is "claimed", never "passing". `--strict` gates CI on orphan tags. The map shows the same per scenario. |
| `/blueprint-ask <question>` | **Ask**: answers how a feature should work, or how it works, from the capability specs, after checking each one still agrees with the code. Cites the requirement and links the spec; where they disagree, says "the spec says X, the code does Y" and points to drift or sync. Starts on its own when you ask such a question (in the terminal, or through an agent such as Claude in Slack), and never writes anything. |
| `/blueprint-drift [capability]` | **Intent drift**: the spec is right. Judges the code against it requirement by requirement, including spec edits people made outside the code, and fixes the code or turns the gap into a blueprint or tickets. |
| `/blueprint-sync [capability]` | **Spec sync**: the code is right. Reads what the code changed since the spec last matched it and updates the spec, or writes a spec from the code for a capability that has none. |
| `/blueprint-tidy [--dry-run]` | **Tidy**, on demand: migrates `.blueprint/` to the current format, groups capabilities into **domains** (each with an overview page that holds its specs like a folder), renames a name that is both a domain and a capability, and reports anchors that overlap through broad globs. Shows one move table and writes nothing until you approve it (a migration asks first on its own); renames keep each page and its history, so nothing reads as drift. |
| `/blueprint-backfill [domain <name> \| fold \| finish]` | **Backfill**: brings an existing repo fully under blueprint in passes that can run in separate sessions: domains, every capability with its anchors, specs drafted from the code and reviewed scenario by scenario, then folded into `blueprint.json`, tests tagged with the scenarios they claim, and outside docs recorded as artifacts. Progress is kept in `.blueprint/backfill/`, so any session resumes where the last one stopped; the folder is deleted when the backfill finishes. `/blueprint-setup` suggests it for repos with more than 15 capabilities. |

**Upgrading from 0.5.0:** 0.6.0 moves the blueprint format to version 2 (domains). Repos set up
before it keep working; `/blueprint` says in one line that the repo is on format 1. Run
`/blueprint-tidy` once per repo to migrate: it adds `version` and `domains` to `blueprint.json`,
refreshes `.blueprint/drift.py`, and updates the backend's structure (in Notion a `Kind` property and
sub-items on Specs; in Obsidian, specs move from `domain__capability.md` into domain folders). It then
offers to group the capabilities, which you can decline. What each format version changed is in
[`upgrades.md`](skills/blueprint/references/upgrades.md).

**Visuals:** live only in the review, so specs and briefs stay plain text for agents and diffs. Every review opens with a picture: a before → after Mermaid
diagram with the change colored in, plus a sequence, state or data diagram when the change has
that shape. For behavior over time (retries, ordering, offline, caching), it offers a
**playground**: a small interactive model with scenario buttons, knobs like latency or an
offline toggle, and a before/after switch that runs the same scenario through the old and the new design.
In Notion the diagrams go in as rendered images (Mermaid source in a toggle underneath) and the playground runs inside the review as an embedded HTML block.
Examples: this repo runs blueprint on itself (see [`.blueprint/`](.blueprint/) and its [specs and blueprints in Notion](https://app.notion.com/p/41c43cce21f2819ba9e9e27bc322d312)), and so does [jambo](https://github.com/KarolNov/jambo).

**Docs and tickets can live apart:** for example specs and blueprints in Notion, under the project's own page, and tasks as GitHub issues in the repo. Ticket trackers: GitHub issues, Linear, Jira, a Notion tasks database (the team's own, or a new one beside the specs), or none.

**Backends:** Notion (default), Obsidian, a Markdown folder outside the repo, Linear, Jira +
Confluence, or GitHub (wiki for specs, issues for blueprints).

**What lives in the repo:** only `.blueprint/`: a map of capabilities to pages and code globs, the
spec text as of the last sync (the merge base), and `drift.py`, which tells from git alone which
capabilities' code moved since their spec was synced. `python3 .blueprint/drift.py check` can run
as a pre-push hook or in CI. For CI, `/blueprint-setup` copies a ready-made GitHub Action,
[`blueprint-drift.yml`](skills/blueprint-setup/templates/blueprint-drift.yml), into `.github/workflows/`: when a pull request
drifts it comments listing the drifted capabilities and their changed files (one comment, updated on every push,
marked back in sync once fixed) and adds a warning annotation per drifted capability; a clean PR gets neither. It passes unless you set `BLUEPRINT_DRIFT_FAIL: "true"`. It is a starting
point the repo owns; ask setup to tailor it (a `drifted` label, a reviewer). Both the map and CI see
code-side drift only; `/blueprint-sync` reports specs edited in the backend.

**Dogfooding:** this repo runs blueprint on itself. [`.blueprint/`](.blueprint) maps six
`blueprint/*` capabilities (propose, apply, backends, setup, sync, drift) to the skill files that
define them, with each spec's last-synced text in [`.blueprint/baseline/`](.blueprint/baseline). Changes
to blueprint, starting with a review pane that shows specs inside Claude Code, are planned as
blueprints against those specs. The specs themselves live in a private Notion workspace. Its tests
(`skills/blueprint/scripts/test_*.py` as integration, the review pane's `*.test.ts(x)` as unit) carry
`@scenario` tags, so `/blueprint coverage` and the map show which scenarios they claim.

**Needs:** Python 3, git, and the connector for your backend (Notion, Linear, Atlassian) or `gh`. Rendering diagrams to images (Notion) needs Python Playwright with Chromium, the same one `walkthrough-setup` installs.

**Review pane (`blueprint-ui`):** a mod that opens a pane beside the chat with `/blueprint-ui`
(or `/blueprint-ui <change or capability>`). It lists the reviews, briefs and specs `.blueprint/blueprint.json`
maps and shows the chosen page read-only. Press "+" beside a block to comment on it or suggest new
wording, as on a GitHub diff line; comments batch up like a pending review, and "Submit review" hands
the batch to `/blueprint review`, which shows one preview and writes on your yes. It reads Notion through
your session's Notion connection (the server name is a setting, `claude.ai Notion` by default) and
works the same in the terminal and the desktop app. While a `/blueprint-backfill` is in progress, the board's
first line shows its pass, and choosing it opens the Backfill view: one scenario card at a time, with
Accept, Amend and Reject, each decision saved before the next card. Install it next to `blueprint`.

Try it: `/blueprint-setup`, then *"/blueprint move session storage from cookies to Redis, keyed by
user id, with a 30-day sliding expiry"*.

## Repository layout

```
.claude-plugin/marketplace.json   # plugin marketplace manifest
skills/<skill-name>/SKILL.md      # one folder per skill
mods/<mod-name>/                  # one folder per mod (its own plugin manifest and hooks module)
template/SKILL.md                 # starting point for new skills
```

## Adding a skill

1. Copy `template/` to `skills/<skill-name>/` (lowercase, hyphenated).
2. Fill in the `name` and `description` frontmatter in `SKILL.md`; `name` must match the folder name.
3. Add `"./skills/<skill-name>"` to a plugin's `skills` array in `.claude-plugin/marketplace.json`,
   or add a new plugin entry for a new family of skills.
4. Add it to the README.

## Adding a mod

A mod (a Claude Code plugin with a hooks module: panes, commands, hooks) lives in `mods/<mod-name>/`
with its own `.claude-plugin/plugin.json`, and gets its own plugin entry in
`.claude-plugin/marketplace.json` with `"source": "./mods/<mod-name>"`. Add its install line and a
paragraph to the README next to the skills it extends. Check it with `claude plugin validate` and
`claude plugin test` on its folder.

## License

[MIT](LICENSE)
