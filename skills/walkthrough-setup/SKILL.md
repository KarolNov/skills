---
name: walkthrough-setup
description: Install and configure the walkthrough recorder used by the design-walkthrough and tutorial-walkthrough skills. It sets up Playwright, a narration voice (Chatterbox voice clone, Kokoro, or ElevenLabs), and a saved login for each app to record. Use when the user asks to set up, install, update or repair walkthrough or tutorial video recording, to add an app to record, to log in again because a session expired, or to change the narration voice. Also use when another walkthrough skill reports that ~/.walkthrough is missing.
---

# Walkthrough setup

This skill installs a small engine, `wt`, that records a real browser with Playwright. An
animated dot stands in for the cursor, narration is generated per step, and the two are
mixed into an mp4. The `design-walkthrough` and `tutorial-walkthrough` skills write specs
for it. Everything lives in `~/.walkthrough/` (override with `WALKTHROUGH_HOME`):

```
~/.walkthrough/
  bin/wt            command (wrapper around the venv)
  engine/           engine code + SPEC.md (copied from this skill)
  venv/             Python 3.10-3.12 with Playwright and the voice model
  config.json       voice provider and settings, video size, pointer colour
  apps/<name>.json  apps to record: base URL, auth mode, login steps
  auth/<name>.json  saved browser sessions (cookies): treat like passwords
  voices/           reference recordings for voice cloning
  .env              API keys and test-account credentials (chmod 600)
```

`<skill-dir>` below is the directory containing this file.

## Ground rules

- **Never ask for secrets in chat.** API keys and passwords go into `~/.walkthrough/.env`,
  typed by the user. Open the file for them (`open -e ~/.walkthrough/.env` on macOS) and
  name the exact variables to fill in.
- **Never print or read back** `.env` or `auth/*.json`. Check whether a variable is set
  with `grep -c '^NAME=.\+' ~/.walkthrough/.env`, never by showing it.
- Ask before installing system packages (Homebrew, apt). Installing Python packages
  into `~/.walkthrough/venv` is part of the job and needs no extra confirmation.

## Steps

Work through these in order. Skip steps that `~/.walkthrough/bin/wt doctor` already
shows as `ok` (for example, when the user only wants to add an app or re-login).

### 1. Choose the voice

Ask which narration voice they want. Explain the trade-offs from
[references/voices.md](references/voices.md) in two or three lines:

- **Kokoro** (`af_heart` by default): free, local, fast, good quality. Not their own voice.
  The easy default.
- **Chatterbox**: free, local voice clone from a 10–20 s recording of their own voice.
  Heavier install (PyTorch, ~2 GB of model downloads on first use), slow on CPU,
  reasonable on Apple Silicon.
- **ElevenLabs**: paid API, best quality, cloned or stock voices; needs an API key.

They can install more than one and switch with `tts.provider` in `config.json`.

### 2. Check the prerequisites

```bash
command -v ffmpeg espeak-ng uv python3.11 python3.12; python3 --version
```

Needed: `ffmpeg` always, `espeak-ng` for Kokoro, and Python 3.10–3.12 *or* `uv` (which
fetches the right Python itself). If anything is missing, ask before running e.g.
`brew install ffmpeg espeak-ng uv`.

### 3. Install

```bash
bash <skill-dir>/scripts/install.sh <provider> [<provider> ...]
```

It is idempotent: re-run it to update the engine after this skill changes. It keeps
config, apps, sessions and `.env`. The first run takes a few minutes (Chromium, plus
PyTorch for Chatterbox). Run it in the background if it may exceed two minutes.

Then configure the voice, following [references/voices.md](references/voices.md):

- **Kokoro:** nothing more; optionally pick another voice in `config.json`.
- **Chatterbox:** help them record a reference clip to `~/.walkthrough/voices/reference.wav`.
- **ElevenLabs:** they add `ELEVENLABS_API_KEY` to `.env` themselves; you set `voice_id`.

Test it:

```bash
~/.walkthrough/bin/wt say "Hi, this is how my walkthroughs will sound." --out /tmp/voice-test.wav && afplay /tmp/voice-test.wav
```

### 4. Register each app to record

Ask for the app's base URL (local dev server, staging, or production) and how to log in.
Recommend a **dedicated walkthrough account with demo data** (whatever is on screen ends up
in the video), then pick the auth mode. Details and edge cases (SSO, 2FA, Google blocking
automated browsers) are in [references/auth.md](references/auth.md).

| Mode | When | How |
|---|---|---|
| `storage-state` (default) | SSO, 2FA, anything with a human step | They log in by hand in a browser window and close it; the cookies are saved and reused. Re-run `wt login` when the session expires. |
| `credentials` | A plain email/password test account | Stored in `.env`; the engine logs in headlessly whenever needed. |
| `none` | Public pages, local dev without auth | — |

```bash
~/.walkthrough/bin/wt app add <name> --url <base-url> --auth storage-state \
  --login-url /login --logged-in-check "<selector only visible when logged in>"
~/.walkthrough/bin/wt login <name>
```

`--logged-in-check` is optional but recommended: it makes the recorder fail clearly on
an expired session instead of recording a login page. A good pick is the avatar or
account menu, e.g. `[data-testid=user-menu]` or `role=button[name='Account']`.

For `storage-state`, `wt login` opens a browser window and waits. Tell the user to log in.
With `--logged-in-check` the window closes by itself once they're in; without it, they wait
until the app has loaded, then **close the window**, and the session is saved.

For `credentials`: `wt app add` writes template `login_steps` into
`~/.walkthrough/apps/<name>.json` and names the `.env` variables. Fix the selectors to match
the real login form (look at the page), have the user fill in the variables, then run
`wt login <name> --headed` to watch it work once.

### 5. Verify

```bash
~/.walkthrough/bin/wt doctor
```

Then make a five-second smoke test: write a one-step spec to a temp dir that opens the
app, points at something and says one sentence, and run it with `wt run`. Open the result
(`open <dir>/walkthrough.mp4`) and ask the user whether the dot, the voice and the
logged-in state look right.

Tell the user the essentials: the walkthrough skills are ready, `wt login <app>` refreshes
a session, and `~/.walkthrough/auth/` and `.env` are secrets that must never be committed
or shared.

## Changing things later

- Voice: edit `tts.provider` / provider settings in `~/.walkthrough/config.json`
  (install the provider first with `install.sh <provider>`).
- Video size and pointer colour: `video` in `config.json` (default 1440×900, red dot).
  The video is exactly the viewport size; a narrower viewport makes small text larger.
- Expired session: `wt login <app>`.
- Engine update after pulling a new version of these skills: re-run `install.sh`.
