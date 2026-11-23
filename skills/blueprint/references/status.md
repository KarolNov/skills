# Status and bookkeeping

Shared by `blueprint-drift` and `blueprint-sync`, and by `blueprint` when it writes a spec.

## Status

For each capability in scope:

- **Code side**: `python3 .blueprint/drift.py check --json <capabilities>` gives `in-sync`, `code-moved` (with the files added, removed or edited since the last stamp), `deps-moved` (code it imports, or a failing tagged test, took its drift chance to the threshold), `possibly-affected` (a chance above 0 but below the threshold), `no-spec` or `no-anchors`, plus each capability's drift `chance` (0-1), `confidence` (`high` or `low`) and the `reasons` behind both, naming the imported files that changed. It exits 1 when any capability is `code-moved` or `deps-moved`, and 2 on a bad `drift.scoring` setting or an unknown capability: report that error instead of a status. `deps-moved` counts as code moved: it suggests sync, or drift first when the spec moved too. `possibly-affected` is not drift: show it with its chance, suggest nothing, and leave it out of a bare sync.
- **Spec side**: fetch the page's current version marker (see the backend file) and compare it with `specVersion`. Different means the spec moved: someone edited intent outside the code. Diff `baseline/<capability>.md` against the current page, matching requirements by name, to see which requirements changed.

Show one table:

| Capability | Code | Spec | Suggests |
| --- | --- | --- | --- |
| `auth/session` | moved (3 files) | moved | drift first, then sync |
| `billing/invoices` | — | moved | drift |
| `search` | moved (1 file) | — | drift or sync, by which side is right |
| `billing/refunds` | imports moved (0.5 · medium) | — | sync |

Which skill fits is a question of **which side is right**:

- **`blueprint-drift`** (intent drift): the spec is right; judge the code against it and fix the code.
- **`blueprint-sync`** (spec sync): the code is right; judge the spec against it and fix the spec.

A capability whose spec moved goes through drift first: the spec edits are new intent, and a sync would overwrite them.

## Spec bookkeeping

Every time a capability's spec and code are known to agree (after a spec write, or after code was fixed to match the spec), record it, or the next status reads as drift:

1. Save the spec text, normalized as the backend file says, to `.blueprint/baseline/<capability>.md`.
2. Record the backend's current version marker as `specVersion` in `blueprint.json` (read it after the last write).
3. Run `python3 .blueprint/drift.py stamp <capability>`. Stamp after the code it covers is committed: if stamp warns that anchored files are uncommitted, commit them (with the user's yes) and stamp again, or `syncedCommit` predates that code and the next sync re-reads it as new.

Never do it for a capability that still has a known disagreement; leave that one drifted so the next run finds it.

## Baselines stay in the repo

Baselines live in `.blueprint/baseline/` and are committed with the code they describe. Never move them to the backend, out of git, or into `.gitignore`, even to tidy up: that is intended, not an accident.

The reason is the conflict. When two branches each sync the same capability, both edit `baseline/<capability>.md` (and its `specVersion` and stamp in `blueprint.json`), so the second to merge conflicts in git. That conflict is the signal that two changes rewrote one spec. Resolve it by syncing the merged code against the current spec page (`/blueprint-sync <capability>` after the merge), which rewrites the baseline and stamp; never by picking one side's baseline, which would record agreement nobody checked.
