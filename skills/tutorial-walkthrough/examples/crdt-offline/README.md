# Example: merge offline edits in a CRDT playground

A 26-second tutorial that teaches one task on
[a live blog post](https://karolnov.dev/blog/before-you-build-a-sync-engine/): take one
person offline, edit on both sides, reconnect, and watch the edits merge. Everything
happens inside the page, so every run starts clean and nothing needs resetting.

```bash
~/.walkthrough/bin/wt run spec.json --out /tmp/crdt-tutorial --burn-subtitles
open /tmp/crdt-tutorial/walkthrough.mp4
```

Files:
- [`plan.md`](plan.md): the plan, written and agreed before the spec
- [`spec.json`](spec.json): what `wt` runs
- [`steps.md`](steps.md): the written companion that goes under the video

## What it shows

| Label | Action | Said |
|---|---|---|
| — | Slow scroll to the CRDT playground | "Let's break a CRDT on purpose, by editing offline." |
| Step 1 · Take Bob offline | Untick **online** next to Bob | "Untick online next to Bob." |
| Step 2 · Edit as Alice | Type " world" at the end of Alice's text | "Add world to the end of Alice's text." |
| Step 3 · Edit as Bob | Type "Oh, " at the start of Bob's text; it shows as *waiting* | "Bob types Oh, at the start. His edit waits in a queue." |
| Step 4 · Reconnect Bob | Tick **online**, wait for **In sync ✓**, highlight it | "Tick online again, and wait for In sync." |
| — | Highlight the server's "Oh, Hello world" | "Both edits survive, in every copy." |

## Choices worth copying

- **One action per step**, each with a `label`, and narration that quotes the UI's own
  words ("online", "In sync").
- **`caret: "start"`** on `type`: the edit has to go at the beginning of the field, and a
  click alone would put the cursor wherever the dot lands.
- **`wait_for` the visible result** (`[data-status]:has-text('In sync')`) instead of a
  fixed wait, so the step lasts as long as the sync really takes.
- **`highlight` with `"point": false`** on the status, because the dot would cover the
  very text it's pointing at.
- Proven re-runnable by two silent drafts in a row (`wt run spec.json --no-voice`)
  before the narrated take.
