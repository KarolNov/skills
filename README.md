# Skills

A collection of [Claude Code](https://claude.com/claude-code) skills I use day to day,
grouped into plugins.

## Install

### As a plugin marketplace (recommended)

In Claude Code:

```
/plugin marketplace add KarolNov/skills
/plugin install walkthrough@karolnov-skills
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
| [`design-walkthrough`](skills/design-walkthrough) | A short design review or feature tour: explains *why* the UI is the way it is, letting the page's own motion carry it. | [Sync engine post, 32 s](skills/design-walkthrough/examples/sync-engine-post) |
| [`tutorial-walkthrough`](skills/tutorial-walkthrough) | A step-by-step how-to: performs each click and keystroke with step labels and captions, plus a written version. | [CRDT offline edits, 26 s](skills/tutorial-walkthrough/examples/crdt-offline) |

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

## Repository layout

```
.claude-plugin/marketplace.json   # plugin marketplace manifest
skills/<skill-name>/SKILL.md      # one folder per skill
template/SKILL.md                 # starting point for new skills
```

## Adding a skill

1. Copy `template/` to `skills/<skill-name>/` (lowercase, hyphenated).
2. Fill in the `name` and `description` frontmatter in `SKILL.md`; `name` must match the folder name.
3. Add `"./skills/<skill-name>"` to a plugin's `skills` array in `.claude-plugin/marketplace.json`,
   or add a new plugin entry for a new family of skills.
4. Add it to the README.

## License

[MIT](LICENSE)
