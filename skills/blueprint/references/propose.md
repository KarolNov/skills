# Propose

Turn the user's solution into an approved blueprint. Five steps; the blueprint is written once, at the end, after the user approves it.

## 1. Restate and anchor

Read the arguments and the conversation for the user's solution. If there is none yet, ask for it in one line: what they want to build and how they plan to do it.

Then, before asking anything, gather facts in parallel (a subagent for anything wider than a few files):

- the code the solution touches, through the capability anchors in `blueprint.json` and a search beyond them;
- the capability specs for those capabilities, fetched from the backend (and their `drift.py check` status: build on drifted specs only after flagging it);
- open blueprints in `blueprint.json` that touch the same capabilities;
- the repo's glossary and ADRs, if any. Use their vocabulary.

Play the solution back as one short block, followed by the **sketch** from [visuals.md](visuals.md): a rough before → after flowchart of the touched parts.

```
**Destination:** <one line: what is true when this is done>
**Solution:** <3 to 8 bullets, in the user's terms>
**Touches:** <capabilities, linked; "new: <name>" for ones that don't exist yet>
**Out of scope:** <what you take this to exclude>
**Collides with:** <facts from the code or specs that contradict the solution; omit if none>
```

The user corrects it (the words or the sketch) or says yes. The destination and scope are now fixed: every later question is measured against them.

## 2. Grill the solution

**Solution-first grilling**: you are pressure-testing *this* design, not searching for a better one. The design tree is the user's solution; you walk its branches looking for the places where it is underspecified or where it meets a hard fact.

A question earns a place only if its answer changes the spec delta, an interface, a data shape, a migration, or a test. Everything else you decide yourself with the conventional default and list under **Assumed** for the user to skim.

Raise an alternative design only when the solution collides with a fact (a constraint in the code, an existing requirement, a limit of a dependency), and then once, as a collision with the fact quoted. Otherwise the user's choice stands.

Ask in rounds. Each round holds the questions answerable now (not ones that depend on another open question), at most five, ordered by how much of the blueprint hangs on them:

```
**Q1 · <title>**: <the question, two lines at most; options inline if there are options>
→ <your recommendation>
```

Word each so "yes" accepts your recommendation, and let the user answer all of them in one line ("yes, 2: no, keep the cookie, rest yes").

Stop grilling when no question meets the bar, or after three rounds. Whatever is still unsettled after three rounds goes into **Open questions** in the brief, each with your recommendation; say so rather than starting a fourth round.

### When talk can't settle it

Two escapes from the round, both only when needed:

- **Research**: a fact outside the repo blocks a decision (an API's limits, a library's behavior, pricing). Send a subagent to find it from primary sources and keep asking the questions that don't depend on it. Its findings go under Decisions with the source link.
- **Prototype**: the question is "how should it look" or "how should it behave" and the user can't answer in words. Offer a throwaway prototype (outside the main code, on a scratch branch or in the scratchpad), build it on a yes, and let the user pick. The user makes the choice, never you.

## 3. Draft the blueprint

Write the brief in the format from [formats.md](formats.md), in the conversation, not yet in the backend:

- **Spec delta** per capability touched. MODIFIED blocks copy the current requirement from the capability spec whole, then edit it. A new capability gets a full spec (Purpose plus ADDED) and proposed anchors.
- **Code map**: the files and modules the build will work in, from the facts you gathered in step 1.
- **Decisions** carry the reasons from the grilling, one line each.
- **Tasks** are vertical slices, each one checkable on its own: usually 3 to 10. The last task is always "Update specs: fold the delta into the capability specs" (apply does this).

Then draw the review's picture: the diagrams from [visuals.md](visuals.md), chosen by the shape of the change. If the change is about behavior over time, offer a playground in one line ("want a playground where you can run *two writes at once* before and after?") and build it on a yes.

Show the picture first, then the brief, so the user reviews the shape before the details. Iterate until the user approves the brief ("approved", "go", "yes, write it"); changes go into the brief and the picture follows.

## 4. Write it

On approval:

1. Create the brief in the backend (see the backend file for where the pair goes) with status `approved`.
2. Put the playground in the backend if there is one ([visuals.md](visuals.md), "Where it goes"), and render the diagrams to images if the backend needs them.
3. Build the review from the brief (format in [formats.md](formats.md)) next to it, linking the brief and the playground, and add the review's link to the brief. Read the review back to check the diagrams render.
4. Create the tickets, one per task, as [tickets.md](tickets.md) says for the configured tracker, after listing them for the user; link each from its task line in the brief and set the docs side's tickets link. Skip this for `none`.
5. Add the change to `blueprint.json` under `changes` with its `brief`, `review` and `playground` links, `status: approved`, and `baseCommit` set to the current `HEAD`.
6. For each new capability, add it to `specs` with its anchors and `"ref": null`; its spec page is created when the blueprint is applied.

The capability specs themselves are **not** edited now: the delta lives on the brief until the code exists. That is what keeps specs describing the system as built.

## 5. Hand off

Report in two or three lines: the review's link (the one to share with people), the brief's link (the one to hand an agent), the playground's link if there is one, the number of tasks, any open questions. Suggest `/blueprint apply <change id>` to build it, here or in a fresh session.
