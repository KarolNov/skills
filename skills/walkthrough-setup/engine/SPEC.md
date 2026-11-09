# Walkthrough spec reference

A walkthrough is one JSON file. `wt run spec.json` narrates each step, records a real
browser session that plays the steps while the narration time passes, and mixes the
two into `walkthrough.mp4`. Outputs go next to the spec unless `--out` is given.

## Top level

```json
{
  "app": "acme",
  "title": "Invite a teammate",
  "start_url": "/projects",
  "color_scheme": "light",
  "video": { "width": 1440, "height": 900 },
  "default_hold": 0.6,
  "lead_in": 0.6,
  "tail": 1.0,
  "setup": [ { "do": "click", "target": "text=Dismiss" } ],
  "steps": [ ... ]
}
```

| Field | Meaning |
|---|---|
| `app` | Registered app name (`wt app list`). Gives base URL and saved session. `"none"` for a public page with an absolute `start_url`. |
| `start_url` | Path (relative to the app's base URL) or absolute URL to open before recording starts. |
| `setup` | Actions run before the clock starts; they are trimmed out of the video. Use for closing banners, seeding state, scrolling to a start position. |
| `video` | Overrides `config.json` video settings: `width`, `height`, `pointer_color`. The video is exactly the viewport size; for small text, use a smaller viewport (e.g. 1280×800) so content fills more of the frame. |
| `default_hold` | Seconds of quiet after each step's narration (default 0.6). |
| `lead_in` / `tail` | Quiet seconds before the first step and after the last one. |

## Steps

```json
{
  "id": "open-settings",
  "say": "Team settings live under your avatar, top right.",
  "label": "Step 1 · Open settings",
  "actions": [
    { "do": "point", "target": "[data-testid=avatar]" },
    { "do": "click", "target": "[data-testid=avatar]" },
    { "do": "click", "target": "role=menuitem[name='Settings']" }
  ],
  "hold": 0.8
}
```

| Field | Meaning |
|---|---|
| `id` | Unique slug. Also the narration filename. |
| `say` | Narration for this step. Starts when the step starts. Omit for silent steps. |
| `label` | On-screen chip (bottom-left) shown from this step on. `null` hides it. |
| `actions` | Played in order while the narration runs. |
| `delay` | Seconds to wait before running the actions (lets narration lead the motion). |
| `say_offset` | Seconds after the step starts before narration begins. |
| `hold` | Quiet seconds after the narration ends (overrides `default_hold`). |
| `chapter` | Chapter title starting at this step; written to `chapters.txt` (the first chapter is forced to 0:00). |
| `poster` | `true` marks this step as the poster frame. |

**Timing rule.** A step lasts `max(time its actions take, say_offset + narration length + hold)`.
Narration is generated first, so its length is known before recording. Keep each step's
actions shorter than its narration, or the voice falls silent while the screen keeps moving.

## Targets

`target` is any Playwright selector, in order of preference:

1. `role=button[name='Invite']` (accessible role + name; stable and readable)
2. `[data-testid=invite-button]`
3. `text=Invite teammates` (visible text)
4. CSS: `form.invite input[type=email]`

The first visible match is used, scrolled into view if needed. Values in `text`, `url` and
`target` can use `$VAR` from `~/.walkthrough/.env`, so credentials never live in the spec.

## Actions

| `do` | Fields | What it does |
|---|---|---|
| `goto` | `url` | Navigate (path or absolute URL) and wait for the network to settle. |
| `point` | `target`, `offset?`, `pause?` | Glide the dot to the element (hover effects fire). |
| `hover` | `target` | Same as `point`. |
| `click` | `target`, `offset?`, `pause?` | Glide, press with a ripple, release, wait for the page to settle. |
| `type` | `target`, `text`, `delay_ms?`, `clear?`, `caret?` | Click the field and type character by character (55 ms/char). `caret`: `start` or `end` puts the cursor there first (inputs and textareas). |
| `fill` | `target`, `text` | Set a field's value at once (use for long text). |
| `press` | `key` | Keyboard key or chord: `Enter`, `Escape`, `Meta+K`. |
| `select` | `target`, `value` | Choose an option in a native `<select>`. |
| `scroll` | `target` or `by`, `block?`, `duration?`, `pause?` | Eased scroll that puts an element at the `start`/`center`/`end` of the screen (default `center`), or moves by N pixels. Duration defaults to distance-based, 0.6–2.5 s. Use a long `duration` (3–6 s) to let scroll-linked animations play. |
| `highlight` | `target`, `seconds?`, `dim?`, `point?` | Draw a ring around an element (optionally dim the rest) and point at it. |
| `label` | `text` | Change or hide (`null`) the step chip mid-step. |
| `drag` | `target`, `to` | Press on one element, glide to another, release. |
| `wait` | `seconds` | Pause. |
| `wait_for` | `target`, `timeout?` | Wait until an element is visible (e.g. after a save). |
| `wait_for_url` | `url`, `timeout?` | Wait for a URL glob such as `**/settings`. |
| `hide_pointer` / `show_pointer` | | Hide the dot during pure scrolling or reading moments. |
| `eval` | `js` | Run JavaScript in the page; for things nothing else covers. |

`offset: [x, y]` points at a spot relative to the element's top-left instead of its centre.
`speed` on any motion action scales pointer speed (`0.6` = slower, `1.5` = faster).

## Commands

```bash
wt inspect <app> /settings        # accessibility tree + inspect.png of a page, for picking selectors
wt validate spec.json             # check structure only
wt tts spec.json                  # narration only (cached per line; edit one line, re-run cheaply)
wt record spec.json --headed      # watch the recording live (uses cached narration timings)
wt render --out <dir>             # re-mix without re-recording
wt run spec.json                  # all three
wt run spec.json --no-voice       # silent draft to check motion and selectors
wt run spec.json --music bed.mp3 --burn-subtitles
```

Captions come from the narration, one per sentence. By default `walkthrough.mp4` carries
them as a toggleable caption track (the CC button in QuickTime, VLC and most players), and
they're also in `walkthrough.srt`. `--burn-subtitles` draws them into the picture instead,
for places with no caption support (Slack, X, LinkedIn autoplay). Burned captions are drawn
by the headless browser, so they work with any ffmpeg build.

Outputs: `walkthrough.mp4`, `walkthrough.srt`, `poster.jpg`, `raw.webm`, `timeline.json`,
`narration/*.wav`, and `chapters.txt` when steps set `chapter`. On failure, `failure.png` shows the page at the moment it broke.

## Debugging selectors

Before writing selectors for a page, run `wt inspect <app> <path>`: it prints the
accessibility tree (roles and names map directly to `role=...[name='...']` selectors) and
saves a screenshot. Inspect each page the walkthrough visits, including pages reached by
clicking.

When a step fails with a timeout, the selector is wrong or the element isn't there yet.
Look at `failure.png`, then fix the selector or put a `wait_for` before it. For tricky
interactions, Playwright's recorder shows the selectors it would use:

```bash
~/.walkthrough/venv/bin/python -m playwright codegen --load-storage ~/.walkthrough/auth/<app>.json <url>
```
