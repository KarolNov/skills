# Drift

```
/blueprint-drift [capability ...] [--deep]
```

The **spec is right**, and the code should follow it. Drift checks the code against each capability's spec, requirement by requirement, and brings the code back in line. It changes code, never a requirement.

## What counts as drift

A capability has drifted when its spec or its code moved since they last agreed:

- **Code side.** `.blueprint/drift.py` tells this from git alone. Each capability's anchored files are hashed when its spec is synced. If any of those files change, the capability is `code-moved`. For TypeScript and JavaScript, it also follows imports: code a capability imports that changed enough gives `deps-moved`, and smaller changes give `possibly-affected`. Every result comes with a drift chance, a confidence and the reasons behind them.
- **Spec side.** Someone edited the spec page in the backend since the last sync. This is found by comparing the page's version marker with the one recorded in `blueprint.json`.

## What it does

1. Shows the status of every capability whose spec or code moved (or every capability, with `--deep`).
2. Judges each requirement and scenario of the current spec against the code: **holds**, **broken**, **not built** (often a requirement someone just added to the spec) or **unclear**.
3. Goes through the broken and unbuilt ones with you, one at a time. Small gaps get fixed on the spot, with a test that pins the requirement. Larger ones become a [blueprint](/modes/propose) or tickets, and the spec gets a `Not yet built →` line pointing at them. If you decide the code is right after all, that row goes to [Sync](/modes/sync).
4. Records the new sync point for each capability whose code now meets its spec.

## In CI

`/blueprint-setup` can copy a GitHub Action into `.github/workflows/`. On every pull request, it runs `drift.py check` and posts one comment listing the drifted capabilities, their drift chances and the changed files. The comment is updated on each push and marked *back in sync* once fixed. It also lists [artifacts](/modes/sync#artifacts) whose code changed since they were last checked. The job passes unless you set `BLUEPRINT_DRIFT_FAIL: "true"`. The workflow belongs to your repo, so edit it to fit your team.

Both the Action and the [map](/modes/map) see code-side drift only. Spec edits are reported by `/blueprint-sync`.
