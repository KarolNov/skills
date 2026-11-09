# Status and bookkeeping

Shared by `blueprint-drift` and `blueprint-sync`, and by `blueprint` when it writes a spec.

## Status

For each capability in scope:

- **Code side**: `python3 .blueprint/drift.py check --json <capabilities>` gives `in-sync`, `code-moved` (with the files added, removed or edited since the last stamp), `no-spec` or `no-anchors`.
- **Spec side**: fetch the page's current version marker (see the backend file) and compare it with `specVersion`. Different means the spec moved: someone edited intent outside the code. Diff `baseline/<capability>.md` against the current page, matching requirements by name, to see which requirements changed.

Show one table:

| Capability | Code | Spec | Suggests |
| --- | --- | --- | --- |
| `auth/session` | moved (3 files) | moved | drift first, then sync |
| `billing/invoices` | — | moved | drift |
| `search` | moved (1 file) | — | drift or sync, by which side is right |

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
