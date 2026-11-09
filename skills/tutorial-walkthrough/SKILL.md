---
name: tutorial-walkthrough
description: Record a narrated step-by-step tutorial video of a real, running web app. Playwright performs each click and keystroke while an animated pointer dot and on-screen step labels guide the viewer, and the voice tells them exactly what to do. Use when the user wants a how-to video, tutorial, help-center or onboarding video, training clip or "show users how to X" recording, e.g. "make a tutorial on inviting a teammate", "record how to export a report", "help video for setting up SSO". Also produces a written step list to go with the video. For design reviews or feature tours aimed at the team, use design-walkthrough instead.
---

# Tutorial walkthrough

Make a video that teaches someone to do a task themselves. The viewer is an end user who
may pause, rewind and follow along, so clarity beats polish: every action is visible,
named the way the UI names it, and given time to land.

Recording is done by the `wt` engine in `~/.walkthrough/`. You plan the tutorial and write
it as a JSON spec; `wt` performs it in the real app and adds the voice.

## 0. Preflight

```bash
~/.walkthrough/bin/wt doctor && ~/.walkthrough/bin/wt app list
```

If `wt` is missing, or the app isn't registered or logged in, use the
**walkthrough-setup** skill first. Read `~/.walkthrough/engine/SPEC.md` before writing a
spec: it is the contract for every field and action.

## 1. Pin down the task

Settle these before touching the browser; ask the user what you can't infer:

- **The task** as the viewer would phrase it: "Invite a teammate to a project".
- **Who's watching:** a new user, an admin or a power user. This sets how much
  you explain.
- **Starting point:** where the viewer begins (logged in, on the dashboard?), and
  prerequisites (role, plan, existing data).
- **Done looks like:** the visible result that proves it worked.
- **Environment and account:** tutorials perform real actions. Record on local, staging
  or a sandbox workspace with a demo account. Never run create/delete/send flows in
  someone's real workspace.

## 2. Do the task once, by inspection

Walk the flow page by page with `wt inspect <app> <path>`, reading the screenshot and the
accessibility tree for every screen you'll pass through, including dialogs and the
result screen. For each step, record:

- the exact on-screen label of what the user clicks or types into (the narration will
  quote it);
- a stable selector (`role=…[name='…']`, then `data-testid`, then text);
- what changes afterwards (navigation, dialog, toast), so you can `wait_for` it.

**Re-runnability.** Recording usually takes a few attempts, and the task changes state
(the teammate is now invited, the project already exists). Plan how each run starts
clean: a unique value per run (e.g. an email with a timestamp, set via `$VAR`), a reset
in `setup` (delete the previous result through the UI or an `eval` API call on the
sandbox), or a fresh demo workspace. Confirm with the user before automating any
deletion.

## 3. Plan

Write `walkthrough-output/<slug>/plan.md` in the current project (add
`walkthrough-output/` to `.gitignore` if needed):

```markdown
# How to <task>
Audience: … | Start: … | Result: … | App: <name> @ <base url>

1. Intro (≤8s): what you'll do and why it's useful.
2. Step 1 · <verb phrase>: action → what the viewer sees.
3. Step 2 · …
…
N. Result (≤8s): show the outcome; mention where to go next.
```

Rules of thumb:
- **One user action per step.** Typing into a field and pressing Save can be one step
  only if it's a single thought ("Enter their email and click Send").
- Target 30–120 s. Over about 8 steps: split into a series ("Part 1: create the
  workspace", "Part 2: invite your team").
- Mention prerequisites in the intro rather than recording them.

Show the plan to the user before writing the spec.

## 4. Write the spec

Write `walkthrough-output/<slug>/spec.json` following SPEC.md. Guidance for tutorials:

**Narration** (`say`)
- Second person, imperative, present tense: "Click **Invite**, then type their email."
  Quote UI labels exactly as they appear on screen, so viewers can find them.
- Say *where* before *what* when the target is hard to spot: "In the top-right corner,
  click your avatar."
- Mention the result: "A confirmation appears at the bottom of the screen."
- Plain words, short sentences. Written to be heard: no parentheses, abbreviations or
  symbols.
- Pace about 2.3 words per second (a touch slower than a design walkthrough). Each
  step usually needs 1–2 sentences.
- Don't promise behaviour the app doesn't show in the recording.

**Motion**
- `label` on every step: `"Step 2 · Open project settings"`. Use `"label": null` on the
  intro and result steps.
- Let the voice lead the hand: the target should be named just before the click. Use
  `"delay": 0.6–1.2` on steps whose narration first says where to look.
- `point` (or `highlight` without dim) at the target before a `click` when it's small or
  easy to miss.
- `type` for anything the viewer types themselves (they need to see it typed). Use `fill`
  only for long boilerplate.
- `wait_for` the result of each action (dialog, toast, new page) before the next step,
  and `hold` 1.0–1.5 s after results the viewer should register.
- Set `chapter` per step (same text as the label without "Step N ·") and `poster: true`
  on the result step.

Validate before recording: `~/.walkthrough/bin/wt validate <spec>`.

## 5. Draft, check, record

1. **Silent draft:** `~/.walkthrough/bin/wt run <spec> --no-voice`. This checks
   selectors, waits and re-runnability. On failure, read `failure.png`, fix the spec, and
   reset state if the failed run got halfway.
2. **Run it twice in a row** (silent is fine) to prove it starts clean each time.
3. **Full run:** `~/.walkthrough/bin/wt run <spec> --burn-subtitles` (burned-in captions
   are the default for tutorials, since viewers often watch muted; drop the flag if the
   user prefers a separate caption file only).
4. **Review it yourself.** Pull a frame at the middle and end of each step from
   `timeline.json` (`ffmpeg -v error -ss <t> -i walkthrough.mp4 -frames:v 1 -q:v 3
   frame-<id>.jpg`) and read them. Check that the label matches the narration, the click
   target is visible when it's named, each step's result is on screen, and there's no
   error toast, spinner or real personal data.

## 6. Written companion

Write `walkthrough-output/<slug>/steps.md`: the same tutorial as text, ready for a help
center or README:

```markdown
# How to <task>
<one-line intro>. **Before you start:** <prerequisites>.

1. <Imperative step with **exact UI labels** in bold.>
2. …

**Result:** <what the user should now see>.
```

## 7. Deliver

Tell the user:
- the video path and length (offer to `open` it), plus `poster.jpg`, `walkthrough.srt`
  and `chapters.txt`;
- `steps.md`, the written version;
- what state the recording left in the sandbox (e.g. "a teammate named Demo User was
  invited"), and whether you cleaned up;
- offer a re-take: slower or faster pacing, a different voice, or splitting it up.

## Rules

- **Sandbox only for mutations.** Every click is real. Never record flows that create,
  send, pay, delete or invite in a production workspace with real users or data, even if
  asked casually. Confirm the environment first.
- **No real personal data on screen.** Use demo names and example.com emails. Mask
  anything sensitive that you can't avoid.
- **Credentials never appear in specs or narration.** Use `$VAR` from `~/.walkthrough/.env`,
  and never type a real password on camera. Use `fill` for password fields so the
  typing isn't shown.
- **Never edit the app's code** to make a recording work, unless the user asks.
