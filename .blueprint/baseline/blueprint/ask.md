## Purpose

Answers questions about how a feature should work, or how it works, from the capability specs, after checking that each spec still agrees with the code, and never writes anything.

## Requirements

### Requirement: Started by a question

`blueprint-ask` SHALL start when someone asks how a feature should work, or how it works, in a repo that has `.blueprint/blueprint.json`, without the user naming the skill, and also when the user runs `/blueprint-ask <question>`. A request to change behavior SHALL NOT start it.

- **Scenario: Plain question**
  - **GIVEN** a repo set up with blueprint
  - **WHEN** someone asks "how should session expiry work?"
  - **THEN** `blueprint-ask` answers it
- **Scenario: Change request**
  - **WHEN** someone says "make sessions expire after a day"
  - **THEN** `blueprint-ask` does not start

### Requirement: Check before quoting

Before answering from a capability's spec, `blueprint-ask` SHALL check the code side with `drift.py check` and the spec side by comparing the backend's version marker with `specVersion` in `blueprint.json`, for every capability the answer relies on.

- **Scenario: Two capabilities**
  - **WHEN** a question touches `auth/session` and `auth/tokens`
  - **THEN** both are checked, and the answer covers each

### Requirement: Answer by status

The answer SHALL depend on what the check found:

- in sync: taken from the spec, citing the requirement and its scenario names, with a link to the spec page;
- code moved (`code-moved` or `deps-moved`): read from the code as well, saying "the spec says X, the code does Y", naming the changed files, and pointing to `/blueprint-sync` when the code is right and `/blueprint-drift` when the spec is;
- `possibly-affected`: taken from the spec after reading the anchored code behind the requirement, with the drift chance and confidence in one line only when the code disagrees;
- spec moved: taken from the spec, saying that this part is intent not built yet;
- both moved: saying what the spec now says (not built yet) and what the code does, pointing to `/blueprint-drift` first.
- **Scenario: In sync**
  - **GIVEN** `auth/session` is in sync on both sides
  - **WHEN** someone asks how session expiry should work
  - **THEN** the answer quotes the "Session expiry" requirement, names its scenarios and links the spec, without reading code
- **Scenario: Code moved**
  - **GIVEN** `auth/session`'s anchored code changed since its stamp, and now expires sessions after 12 hours where the spec says 24
  - **WHEN** someone asks how long a session lasts
  - **THEN** the answer says the spec says 24 hours and the code does 12, names the changed file, and points to `/blueprint-sync` or `/blueprint-drift`
- **Scenario: Spec moved**
  - **GIVEN** someone edited the "Session expiry" requirement in the backend since the last sync
  - **WHEN** someone asks how session expiry should work
  - **THEN** the answer gives the edited requirement and says it is not built yet

### Requirement: Backend unreachable

When the spec page can't be fetched, `blueprint-ask` SHALL answer from `.blueprint/baseline/<capability>.md`, saying it is the spec as of the last sync and that edits made in the backend since then couldn't be checked. The code-side check SHALL still run.

- **Scenario: No connector**
  - **GIVEN** an agent with the repo but no access to the docs backend
  - **WHEN** it is asked how session expiry should work
  - **THEN** it answers from the baseline and says the spec side was not checked

### Requirement: No spec covers it

When no capability covers the question, `blueprint-ask` SHALL say so and answer from the code, marked as coming from the code alone. When the files involved belong to no capability, it SHALL say in one line that `drift.py unanchored` and `/blueprint-sync` can bring them under a spec.

- **Scenario: Unmapped area**
  - **GIVEN** the question is about code no capability's anchors match
  - **WHEN** it is answered
  - **THEN** the answer says no spec covers it, is labelled as from the code, and ends with the one-line pointer

### Requirement: Read only

`blueprint-ask` SHALL write nothing: no `drift.py stamp`, no edits to the backend, `.blueprint/`, tickets or code, and it SHALL never run tests or setup.

- **Scenario: Drift found**
  - **GIVEN** the check finds `auth/session` drifted
  - **WHEN** the answer is given
  - **THEN** nothing in the repo or the backend has changed, and the answer points to the skill that would fix it
