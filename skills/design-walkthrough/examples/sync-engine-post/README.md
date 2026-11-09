# Example: "Before you build a sync engine"

https://github.com/user-attachments/assets/7e029177-7d35-423d-b9bb-923a26d0b341

*32 s, captions burned in. Also in [`docs/media/sync-engine-walkthrough.mp4`](../../../../docs/media/sync-engine-walkthrough.mp4).*

A 32-second design walkthrough of
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
| CRDT | 4 s scroll past the OT section, same click, ends **In sync ✓** | "A CRDT keeps both, so nobody loses work." |
| Which tool fits | Three answers in the picker; the suggestion updates | "And four quick questions suggest where to start." |

## Choices worth copying

- **Four lines for 32 seconds.** Narration fills under half the video; the playgrounds
  do the explaining. A first take of the About page on the same site was 78 seconds,
  described every section, and felt too talkative.
- **`say_offset` after the scroll.** Each line starts once the scroll and click are done
  (2.8–4.2 s in), so the voice describes what's happening rather than what's coming.
- **Slow `scroll` with an explicit `duration`.** The page moves the way a reader would
  scroll it, and the scroll itself becomes a transition between beats.
- **A `wait` after each click** that's long enough for the animation to finish
  (4.5–5 s at the playground's 1.4 s latency). The result is the payoff, so don't cut away early.
- **Selectors from the page's own data attributes** (`figure[data-sync=crdt]`,
  `figure[data-picker]`), found with `wt inspect`. They're stable and readable.
- `setup` removes Astro's dev toolbar; it's a no-op on the live site but needed on
  `localhost`.
