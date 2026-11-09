---
name: design-walkthrough
description: Record a narrated design walkthrough video of a real, running web app. Playwright drives the actual UI while an animated pointer dot shows where to look and a voice explains the design decisions. Use when the user wants a design walkthrough, design review video, feature tour, demo video or Loom-style video of a screen, flow, redesign or PR, e.g. "make a walkthrough of the new settings page", "record a design review of this PR", "demo video of the onboarding redesign". For step-by-step how-to videos that teach end users a task, use tutorial-walkthrough instead.
---

# Design walkthrough

Make a narrated video tour of a design as it really runs. The audience is designers,
engineers, PMs and stakeholders who want to understand **what changed and why**, without
clicking through it themselves. A good one feels like a teammate sharing their screen:
calm pointer movement, one idea per moment, and narration about intent rather than a
read-out of labels.

Recording is done by the `wt` engine in `~/.walkthrough/`. You plan the walkthrough and
write it as a JSON spec; `wt` records the real app and adds the voice.

## 0. Preflight

```bash
~/.walkthrough/bin/wt doctor && ~/.walkthrough/bin/wt app list
```

If `wt` is missing, or the target app isn't registered or logged in, use the
**walkthrough-setup** skill first, then come back. Read `~/.walkthrough/engine/SPEC.md`
before writing a spec: it is the contract for every field and action.

## 1. Understand the design

Gather enough to explain the design, not just show it:

- **What's being shown:** the user's description, plus a PR, branch diff, design doc or
  Figma notes if available. For a PR or branch, read the diff: it tells you which
  screens, states and interactions changed.
- **Who's watching:** a design review (decisions, trade-offs, states), stakeholders
  (outcomes, before/after), or engineers (behaviour, edge cases). Ask if it's unclear.
- **Where it runs:** which registered app and environment (local dev server, preview,
  staging). If it's local, make sure the dev server is running.
- **The "why":** the reasoning behind each decision. If the source material doesn't say,
  ask the user for 2–3 key rationales. Don't invent design rationale.

## 2. Walk the real UI first

For each screen you might show, run `wt inspect <app> <path>` and look at the screenshot
(read the image) and the accessibility tree. Note:

- the elements that carry the design story (new component, layout change, empty/error
  state, hover or focus treatment, animation);
- stable selectors for them (prefer `role=…[name='…']`, then `data-testid`, then text);
- how to reach each state (a click, a URL parameter, typing invalid input, a toggle).

States that need data (empty vs. populated, errors) may need setup actions or a
different demo account. Plan them now rather than discovering it mid-recording.

## 3. Plan

Write `walkthrough-output/<slug>/plan.md` in the current project (add
`walkthrough-output/` to `.gitignore` if it isn't there). Keep it short:

```markdown
# <Title>
Audience: … | Target length: 30–60s | App: <name> @ <base url>

## Story
One paragraph: the problem, the design move, and what to notice.

## Beats
1. Context (5–10s): where we are, what this screen is for.
2. <Decision 1>: what to show, the action, what to say about why.
3. <Decision 2>: …
4. States/details: hover, empty, error, responsive, motion.
5. Wrap-up (5s): one-sentence summary, open questions if it's for review.
```

**Shape:** context → 2–4 design decisions → wrap-up, in **30–60 seconds**. Shorter is
better: pick the few moments that matter and leave the rest out. If the user wants a
long tour, split it into several short videos, one per area.

Show the plan to the user and adjust it before writing the spec. It's cheaper than
re-recording.

## 4. Write the spec

Write `walkthrough-output/<slug>/spec.json` following SPEC.md. For a worked example of
the target length, density and pacing, read `<skill-dir>/examples/sync-engine-post/`
(`<skill-dir>` is this file's directory). Guidance for design walkthroughs:

**Narration** (`say`)
- **Say less than you think.** One short sentence per beat (about 5–15 words), and several
  beats with no narration at all while the page does its thing. Total narration
  should fill well under half the video. Never describe what's plainly on screen, never
  read the page's text back, and never list details.
- Talk about intent and trade-offs: "Filters stay in a sidebar, so they're always in
  reach". Not: "This is the filter sidebar."
- Conversational, first-person plural, contractions. Written to be heard: short sentences,
  no parentheses, no lists, no abbreviations the voice will mangle (write "for example",
  not "e.g."; spell out symbols).
- Pace about 2.5 words per second, so a sentence is 2–6 s.
- Use the pointer as your finger: "this badge", "up here". Make sure the matching
  `point` or `highlight` happens in the same step.
- Ground every factual claim (metrics, user research, "users asked for…") in what the
  user or the source material actually says. Framing and transitions are yours to write.

**Motion**
- **Let the product move first.** If the page has its own motion (scroll-linked
  animations, interactive demos, transitions), the walkthrough exists to show it: scroll
  slowly through it (`scroll` with `duration` 3–6 s) and click its controls, then wait
  for it to play out. Don't cover the page's own effects with overlay highlights.
- Otherwise, `point` and `highlight` do most of the work. Use `highlight` with `"dim": true`
  sparingly, for the 1–3 most important elements.
- `click`, `type` and `hover` only to reveal a state or interaction being discussed.
- Use `scroll` with a `target` to move down long pages; `hide_pointer` during long
  scrolls if the dot distracts.
- Leave breathing room: `hold` 0.8–1.2 s after a reveal, so viewers see the result
  before the next idea.
- Put state preparation that viewers shouldn't see in top-level `setup`.
- Set `chapter` on each beat's first step and `poster: true` on the most representative
  moment.
- No `label` chips by default (that's a tutorial device). Use one only if the user wants
  section titles on screen.

Validate before recording: `~/.walkthrough/bin/wt validate <spec>`.

## 5. Draft, check, record

1. **Silent draft:** `~/.walkthrough/bin/wt run <spec> --no-voice`. This is fast and
   checks selectors and motion. On failure, read `failure.png`, fix the selector or add a
   `wait_for`, and re-run.
2. **Full run:** `~/.walkthrough/bin/wt run <spec>`. Narration is cached per line, so
   re-runs only re-voice the lines that changed. The first Chatterbox run can take a while;
   run long jobs in the background.
3. **Review it yourself before showing anyone.** Pull a frame from the middle of every
   step, using `start`/`end` from `timeline.json`:
   ```bash
   ffmpeg -v error -ss <t> -i walkthrough.mp4 -frames:v 1 -q:v 3 frame-<id>.jpg
   ```
   Read the frames and check that the right screen is showing, the dot is on what the
   narration names, no spinner, login page or error toast is visible, no real personal
   data is on screen, and nothing is cut off. Fix the spec and re-run until it's clean.

## 6. Deliver

Tell the user:
- where the video is (`walkthrough-output/<slug>/walkthrough.mp4`) and its length;
  offer to `open` it;
- the chapter list (`chapters.txt`), handy for a PR description or Slack post;
- `walkthrough.srt` (captions) and `poster.jpg` (thumbnail) are alongside;
- one line of anything you'd improve, and offer a re-take (different pacing, voice, or
  more or fewer details).

Options to offer when relevant: `--music <file> --music-volume 0.08` for a quiet bed
(user-supplied, licensed music only); `--burn-subtitles` for silent autoplay contexts.

## Rules

- **Nothing private on screen.** The video will be shared. Use the demo account and
  data. If real customer data, emails, tokens or internal-only URLs appear, stop and tell
  the user, and either switch accounts or hide them with an `eval` action that masks
  those elements.
- **Read-only by default.** Design walkthroughs look rather than mutate. If showing a
  state requires creating or deleting data, do it in setup on a sandbox and say so.
- **Never edit the app's code** to make a recording work, unless the user asks.
