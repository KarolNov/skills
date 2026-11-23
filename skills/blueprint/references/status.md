# Status and bookkeeping

Shared by `blueprint-drift` and `blueprint-sync`, and by `blueprint` when it writes a spec.

## Status

For each capability in scope:

- **Code side**: `python3 .blueprint/drift.py check --json <capabilities>` gives each capability a status, its drift `chance` (0 to 1), its `confidence` and the `reasons` behind both (below). It exits 1 when any capability is `code-moved` or `deps-moved`, and 2 on a bad `drift.scoring` setting, an unknown capability or an unusable `--tests`: report that error instead of a status. Add `--tests <report.xml>` when a JUnit report of this tree is at hand, or `--tests run` to run `tests.run` first ([formats.md](formats.md)); only on the user's word, since it runs their tests. Without it no test results count, and nothing is run.
- **Spec side**: fetch the page's current version marker (see the backend file) and compare it with `specVersion`. Different means the spec moved: someone edited intent outside the code. Diff `baseline/<capability>.md` against the current page, matching requirements by name, to see which requirements changed.

| Status | Means | Exit | Suggests |
| --- | --- | --- | --- |
| `in-sync` | Nothing it anchors or imports moved since its stamp | 0 | nothing |
| `code-moved` | An anchored file was added, removed or edited (listed in `changed`); chance 1 | 1 | sync, or drift first when the spec moved too |
| `deps-moved` | No anchored file changed, but code it imports, a locked version it imports, or a failing test tagged with one of its scenarios took the chance to `threshold` | 1 | the same as `code-moved` |
| `possibly-affected` | Code it imports moved, with a chance above 0 and below `threshold` | 0 | nothing: show it with its chance, and leave it out of a bare sync |
| `no-spec` | Mapped, never stamped (`ref` null or no stamp) | 0 | sync writes its spec |
| `no-anchors` | No anchors to check | 0 | nothing; propose anchors when it should have code |

**Drift chance** is computed by a fixed formula, so the same stamps, tree, settings and test results always give the same number: a changed anchored file scores 1; a changed file or symbol reached through imports `decay^distance` times the weight of each workspace package the path enters; a changed locked version `lockfileWeight`; a failing tagged test 1. Signals combine as `1 − ∏(1 − sᵢ)`. The weights live in `drift.scoring` ([formats.md](formats.md)). A reason line reads, for example, `packages/core/src/token.ts signToken changed, 2 imports away, via @company/core (weight 0.5) → 0.13`, `zod 3.22.0 → 3.23.0 in the lockfile → 0.3`, or `test "rejects an expired token" (src/auth/session.test.ts:12) failed, claiming "Expired token" → 1`.

**Confidence** says how much of the evidence `check` could see, and its reason line says why it isn't higher:

| Confidence | When | Reason line |
| --- | --- | --- |
| `high` | A TS/JS capability whose imports were resolved by symbol and whose tagged tests have results in the report; or a capability with no TS/JS files, where direct changes are all there is to know | none |
| `medium` | Imports resolved by symbol, no test results: no `--tests`, or none of its tagged tests in the report | `confidence medium: no test results given` / `… no results for its tagged tests in the report` |
| `low` | Imports followed by file only (no Node or no `typescript` now or when stamped), or no closure stamped yet so only direct changes count, or `no-spec` / `no-anchors` | `confidence low: typescript not installed, so imports are followed by file`, and the like |

Test results raise confidence per capability: a report that holds results for other capabilities' tests but none of this one's leaves it `medium`. Passing tests never lower the chance; they only raise confidence. Low confidence is a reason to say so when reporting, not to skip the capability: its chance still decides its status. Where `drift.py check` prints `notice:` about missing Node or `typescript`, pass it on once; never install anything to raise confidence.

Show one table:

| Capability | Code | Spec | Suggests |
| --- | --- | --- | --- |
| `auth/session` | moved (3 files) | moved | drift first, then sync |
| `billing/invoices` | — | moved | drift |
| `search` | moved (1 file) | — | drift or sync, by which side is right |
| `billing/refunds` | imports moved (0.5 · medium) | — | sync |
| `billing/tax` | possibly affected (0.13 · medium) | — | — |

Which skill fits is a question of **which side is right**:

- **`blueprint-drift`** (intent drift): the spec is right; judge the code against it and fix the code.
- **`blueprint-sync`** (spec sync): the code is right; judge the spec against it and fix the spec.

A capability whose spec moved goes through drift first: the spec edits are new intent, and a sync would overwrite them.

## Spec bookkeeping

Every time a capability's spec and code are known to agree (after a spec write, or after code was fixed to match the spec), record it, or the next status reads as drift:

1. Save the spec text, normalized as the backend file says, to `.blueprint/baseline/<capability>.md`.
2. Record the backend's current version marker as `specVersion` in `blueprint.json` (read it after the last write).
3. Run `python3 .blueprint/drift.py stamp <capability>`. For a TS/JS capability it also re-records the import closure in `.blueprint/closure/<capability>.json`; commit that file with the baseline. Stamp after the code it covers is committed: if stamp warns that anchored files are uncommitted, commit them (with the user's yes) and stamp again, or `syncedCommit` predates that code and the next sync re-reads it as new.

Never do it for a capability that still has a known disagreement; leave that one drifted so the next run finds it.

## Baselines stay in the repo

Baselines live in `.blueprint/baseline/` and are committed with the code they describe. Never move them to the backend, out of git, or into `.gitignore`, even to tidy up: that is intended, not an accident.

The reason is the conflict. When two branches each sync the same capability, both edit `baseline/<capability>.md` (and its `specVersion` and stamp in `blueprint.json`), so the second to merge conflicts in git. That conflict is the signal that two changes rewrote one spec. Resolve it by syncing the merged code against the current spec page (`/blueprint-sync <capability>` after the merge), which rewrites the baseline and stamp; never by picking one side's baseline, which would record agreement nobody checked.
