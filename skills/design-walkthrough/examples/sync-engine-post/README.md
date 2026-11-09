# Example: "Before you build a sync engine"

https://github.com/user-attachments/assets/bbfa99d5-693f-4a3d-893d-d4cfaf388859

*42 s, captions burned in.*

A 42-second design walkthrough of
[a blog post with interactive sync playgrounds](https://karolnov.dev/blog/before-you-build-a-sync-engine/).
It runs against the live site, so you can try it as soon as `walkthrough-setup` is done:

```bash
~/.walkthrough/bin/wt run spec.json --out /tmp/sync-demo --burn-subtitles
open /tmp/sync-demo/walkthrough.mp4
```

## What it shows

| Beat | On screen | Said |
|---|---|---|
| Intro | Pointer rests on the title | "Sync engines, explained with playgrounds you can poke at." |
| Last write wins | Slow scroll to the first playground, click **▶ Type at once**, it ends **Diverged ✗** | "Send the whole text, and someone's edit just vanishes." |
| Operational transformation | Scroll to the OT playground, same click; the server log shows an op moved past an earlier one, ends **In sync ✓** | "OT has a server shift each edit around the other, so both survive." |
| CRDT | Scroll to the CRDT playground, same click, ends **In sync ✓** | "A CRDT merges both on each device, no server needed." |
| Which tool fits | Three answers in the picker; the suggestion updates | "And four quick questions suggest where to start." |

## Choices worth copying

- **Five lines for 42 seconds.** Narration fills under half the video; the playgrounds
  do the explaining. A first take of the About page on the same site was 78 seconds,
  described every section, and felt too talkative.
- **`say_offset` after the scroll.** Each line starts once the scroll and click are done
  (2.8–3.6 s in), so the voice describes what's happening rather than what's coming.
- **Slow `scroll` with an explicit `duration`.** The page moves the way a reader would
  scroll it, and the scroll itself becomes a transition between beats.
- **A `wait` after each click** that's long enough for the animation to finish
  (4.5–5 s at the playground's 1.4 s latency). The result is the payoff, so don't cut away early.
  OT takes longer to settle, so that beat uses `wait_for` on `text=In sync` instead of a
  fixed wait; a first take with 5 s cut away while it still said "Syncing…".
- **Selectors from the page's own data attributes** (`figure[data-sync=crdt]`,
  `figure[data-picker]`), found with `wt inspect`. They're stable and readable.
- `setup` removes Astro's dev toolbar; it's a no-op on the live site but needed on
  `localhost`.
