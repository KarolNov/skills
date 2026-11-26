# Pass 3: spec drafts and scenario review

Per domain, in that domain's session, after its pass 2. Ends with a spec page, baseline and stamp for every capability in the domain that had no spec, each one reviewed scenario by scenario.

Run `backfill.py pass <domain> 3 in-progress`. In scope: every capability in the domain's progress file without a `ref` (new ones, and existing ones with `"ref": null`). Those with a `ref` already have a spec and are left alone.

## 1. Draft from code

For each capability in scope with no draft yet, draft its whole spec from its anchored code by sync's draft-from-code rules ([../../blueprint-sync/SKILL.md](../../blueprint-sync/SKILL.md), step 3): what the code does today, including behavior that looks accidental, marked `<!-- verify: <the question> -->` where the user should decide. The shape is the capability spec in [formats.md](../../blueprint/references/formats.md), from `# <capability>` down: Purpose, then requirements, each with at least one scenario, scenario names unique in the capability. Draft several capabilities in parallel with one subagent each, giving each its anchors, the domain's purpose and those two files.

Save each to `drafts/<domain>/<name>.md` (a bare capability: `drafts/<capability>.md`) and commit the drafts, so review can resume in any session.

## 2. Review, one card per scenario

Take the capabilities in the order pass 2 found them; within one, the undecided scenarios in document order. A scenario is **undecided** while its line carries no decision mark. Show each as one card:

```
**auth/tokens** · card 3 of 11 · 26 left in auth
Purpose: Issue, refresh and revoke API tokens.          (first card of the capability only)
Requirement: Token expiry
  Tokens SHALL expire one hour after they are issued.   (editable on this requirement's first card)
- Scenario: Expired token rejected
  - GIVEN a token issued more than an hour ago
  - WHEN it is presented
  - THEN the request is refused with 401
Verify: does a refresh extend the original token's expiry?
→ accept / amend / reject
```

- The Purpose shows on the capability's first card, and the requirement's statement is editable on the card of its first scenario only; later cards show the statement for context. A `<!-- verify: … -->` in the shown Purpose, statement or scenario becomes the card's **Verify** question; the answer is an accept (the draft is right) or an amend.
- Where the host has a question tool, ask with **Accept** and **Reject** as options; a free-text answer is the amended text. Otherwise ask in chat.
- Never batch cards: each decision is saved before the next card is shown.

**Save each decision** in the draft, then in the progress file, before the next card:

- **Accept**: append ` <!-- accepted -->` to the scenario's line (`- **Scenario: <name>** <!-- accepted -->`) and delete the verify marks the card showed.
- **Amend**: rewrite the text the user changed (scenario, and on its first card the statement or Purpose), append ` <!-- amended -->`, and delete the card's verify marks.
- **Reject**: delete the scenario's lines. When it was its requirement's last scenario, delete the requirement block too.

Then add one to the capability's `review.accepted`, `review.amended` or `review.rejected` in the progress file. A resumed session finds the next card from the marks alone.

## 3. Write the spec

When a capability has no undecided scenario left:

1. Strip the decision marks from the draft. When every requirement was rejected, there is no spec to write: ask whether the capability is real (keep it and draft again) or not (remove it from the progress file, which leaves its files to pass 2's coverage check again).
2. Create its page inside its domain (parent: the progress file's `ref`, or the domain's `ref` in `blueprint.json`) as the backend file says, and set the capability's `ref` in the progress file. The cards were the approval: no further preview.
3. Do the spec bookkeeping of [status.md](../../blueprint/references/status.md), with two changes because `blueprint.json` waits for fold: save the normalized text to `.blueprint/baseline/<capability>.md` as usual; record `specVersion` (read after the last write) on the capability in the progress file; and stamp with `backfill.py stamp <capability>`, not `drift.py stamp`.
4. Link it from the overview's Capabilities list: link its "no spec yet" line and drop the marker.
5. Delete the draft and commit the progress file, baseline and closure.

Report the page with its counts (accepted, amended, rejected), then show the next capability's first card.

## Done when

Every capability in the domain has a `ref`, `specVersion`, `anchorsFiles` and `syncedCommit` in the progress file and a baseline, no draft is left in `drafts/<domain>/`, `backfill.py pass <domain> 3 done` has run, and it is committed. Report the domain's pages (linked) and its review counts. The domain folds next: when this session is on the default branch, offer `/blueprint-backfill fold <domain>` now; otherwise fold runs once this branch merges.
