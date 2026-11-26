# Fold

Merges finished domains into `blueprint.json`, the one place backfill writes it. Run it where every domain session's work is merged: the default branch, or a branch cut from it after their branches merged. A domain still on an unmerged branch has no finished progress file here; it folds on a later run.

1. Run `backfill.py status` and show which domains finished pass 3 and aren't folded. None: say so, with the next commands, and stop.
2. Run `backfill.py fold` with the domain names from the arguments, or none to fold every finished domain. It writes each domain's overview into `domains` (when new) and each capability's `ref`, `specVersion`, anchors and stamps into `specs`; capabilities that had a spec before the backfill are left exactly as they were.
3. It exits 1 and says why for a domain it can't fold: a pass not done, coverage unconfirmed, no overview `ref`, a capability without `ref`, anchors, stamp or baseline, or a name that collides. Settle each with the user: most need that domain's session to finish (`/blueprint-backfill domain <name>`); a missing stamp is `backfill.py stamp <capability>`. The other domains fold regardless.
4. Run `python3 .blueprint/drift.py check <the folded capabilities>`. Each should read `in-sync`. A `code-moved` one had its code edited after its stamp: run `/blueprint-sync <capability>` for it.
5. Commit `blueprint.json`, the folded domains' progress files and the `README.md` together.

## Done when

The folded domains read `folded` in `backfill.py status`, their capabilities are `in-sync` in `drift.py check`, and it is committed. Report the folded domains and their capability counts, any refused with the reason, and the next commands from `backfill.py status`.
