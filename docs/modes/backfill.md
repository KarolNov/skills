# Backfill

```
/blueprint-backfill [domain <name> | fold [domain ...] | finish]
```

Backfill brings an existing repo fully under blueprint. It covers domains, every capability with its anchors, specs drafted from the code and reviewed scenario by scenario, test tags and artifacts. It works in passes that can run in separate sessions, and progress is kept in `.blueprint/backfill/`, so any session picks up where the last one stopped.

[Setup](/modes/setup) suggests it for repos with more than about 15 capabilities.

## The passes

| Pass | Runs | What it does |
| --- | --- | --- |
| 1. Survey and domains | once | Splits the repo into domains and records the plan. |
| 2. Capabilities and anchors | per domain | Names each capability and the globs for its code, and writes the domain's overview page. |
| 3. Spec drafts and review | per domain | Drafts each spec from the code, then you review it **one scenario at a time**: accept, amend or reject. |
| Fold | when domains finish pass 3 | Adds the reviewed capabilities to `blueprint.json`. |
| 4. Test tags | per folded domain | Tags existing tests with the [scenarios](/modes/coverage) they claim. |
| 5. Artifacts | per folded domain | Records outside docs that describe each capability as [artifacts](/modes/sync#artifacts). |
| Finish | once | Deletes `.blueprint/backfill/`. |

Each domain's passes 2 to 4 can run in their own session, on their own branch. With the [review pane](/review-pane) installed, pass 3's scenario review runs there as cards, and each decision is saved before the next card.
