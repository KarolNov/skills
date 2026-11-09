# Visuals

Visuals are for people, so they live in the **review**, never in the brief or a capability spec, which agents read and sync diffs. Three kinds, from cheapest to richest: the **sketch** in the conversation, the **diagrams** in the review, and an optional **playground** linked from it.

Every visual explains the brief, never adds to it. When a visual and the brief disagree, the brief wins and the visual is fixed. Whenever the brief changes (a grilling answer, an amendment during apply), rebuild the visuals with the review.

## Sketch

One Mermaid flowchart in the playback of [propose.md](propose.md) step 1: the parts the solution touches, before and after side by side, at most a dozen nodes. Its job is to catch a misunderstanding before any question is asked, so it is rough on purpose: no styling beyond the change colors below.

## Diagrams

The review's **Picture** section holds one to three Mermaid diagrams, each with a one-line caption saying what to look at ("the session lookup moves from the cookie to Redis; nothing else on the request path changes").

Always include **before → after**: a flowchart of the touched parts, with the change marked. Then add the views the change actually has, chosen by its shape:

| The change is mostly about | Diagram |
| --- | --- |
| who calls whom, in what order (APIs, services, jobs, protocols) | `sequenceDiagram` of the main flow, plus the one failure path that matters most |
| something with a lifecycle (orders, sessions, documents, jobs) | `stateDiagram-v2`, new and changed transitions marked |
| the shape of data (schema, events, documents) | `erDiagram` of the touched entities only |
| where things run (new service, queue, cache, region) | `flowchart` grouped with `subgraph` per deployable |
| a rollout or migration over time | `flowchart LR` of the phases, each with its exit condition |

Rules that keep them readable:

- At most about 15 nodes per diagram. Bigger means two diagrams or a coarser level.
- Name nodes with capability names and the repo's own vocabulary, the same words the spec uses.
- Mark change the same way everywhere, with this legend once under the first diagram:
  ```
  classDef added fill:#dcfce7,stroke:#16a34a,color:#14532d
  classDef changed fill:#fef3c7,stroke:#d97706,color:#78350f
  classDef removed fill:#fee2e2,stroke:#dc2626,color:#7f1d1d,stroke-dasharray:4 3
  ```
  Unchanged nodes stay unstyled, so the eye goes straight to the change.
- Diagrams show concepts and boundaries, not classes or files.

## Playground

A small, live model of the change that a reviewer can poke: the same idea as an interactive figure in a blog post. Offer it, don't default to it, when the change is about **behavior over time** that a static diagram flattens: ordering and concurrency, retries and failures, caching and expiry, offline and reconnect, rate limits, migrations rolling across versions. For a choice between options with trade-offs, the playground can instead be a **decision explorer**: a few questions, and the recommendation updating as they are answered.

What makes a good one:

- **A stage**: the actors (clients, services, queue, store) as labelled boxes, and messages drawn travelling between them, with timing you can see.
- **Scenarios** as buttons: `▶ Happy path`, plus the two or three cases the design exists to handle (`▶ Server restarts mid-request`, `▶ Two writes at once`). Each runs a scripted, deterministic sequence.
- **Knobs** for the conditions that matter: latency, an online/offline toggle per actor, a clock speed, a failure rate.
- **Before / after**: one toggle that runs the same scenario through the old and the new design, so the improvement is something you watch, not something you are told.
- A **log** of events and a one-line **status** ("in sync", "2 writes queued", "stale read!").
- A **scoreboard** that keeps the last run of the other mode beside the current one. Score what the design actually changes: run both modes once and check the numbers differ for the reason the blueprint claims. A worst case that both designs share hides the difference; how often, or the average, usually shows it.
- **Same luck in both modes**: derive randomness (packet loss, timing jitter) from a hash of the logical event, not a running RNG, so a comparison is never won by a lucky draw.
- The model is a few plain functions over a state object, separate from the drawing, so scenarios replay identically. It models the concept, not the real code: no imports from the repo.

Build it as one self-contained HTML file: inline CSS and JS, no build step, no network. Keep it to what the blueprint needs to explain; one strong playground beats three thin ones. [`../examples/fictional-yjs-provider/`](../examples/fictional-yjs-provider/) is a worked example: `brief.md`, and `review.html`, a review with diagrams and a transport playground: reuse its structure, not its subject. If the repo or its docs site has its own design tokens, use them so the playground looks like it belongs.

**Where it goes**: in the backend, next to the review, so reviewers never leave the tool they review in. Where the backend can show HTML inline (Notion's embed block), embed it in the review's Playground section; otherwise store the HTML beside the review and link it. The backend file says which. Replace it in the same place when the brief changes what the playground shows. Keep it one file under 200 KiB with no network access beyond fonts, because embeds run sandboxed.

## When the backend can't render it

Some backends store Mermaid but show it as code (Notion does, and every rebuild of the review would reset a block switched to preview by hand). There, place each diagram as an **image** with its caption, and keep the Mermaid source in a collapsed toggle under it, so it stays readable and editable. Render with `python3 <this skill>/scripts/render_mermaid.py <out dir> <file.mmd | review.md | review.html>`: it writes standalone SVGs with plain-text labels and a white card behind them, so they work as images and read on dark pages. The backend file says which way it goes; for any other backend, read the page back after writing and switch to images if the diagrams show as code.
