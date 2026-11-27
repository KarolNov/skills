# Apply

```
/blueprint apply [change] [group]
```

Apply builds an approved blueprint, then folds its spec delta into the capability specs, so the specs change together with the code.

## Build

Apply reads the brief (never the review) and picks up where the team is: tasks whose tickets were closed by hand count as done. If people left comments on the review, apply raises them as proposed changes to the brief before building. It also checks that the capabilities the change touches haven't drifted. If one has, that gets settled first.

Then it goes task by task: build, test, close the ticket, tick the task in the brief. If a task can't be built as written, or the delta turns out to be wrong, apply stops and tells you. The brief is amended first, so it never falls behind the code without anyone noticing.

## Big changes become several PRs

When a change has more than about four build tasks, or would change more than about 400 lines, apply proposes splitting it into PR groups:

```text
main
├── 1. Session store ········ tasks 1, 2   ▶ starts now
│   └── 2. Login endpoint ··· tasks 3, 4   stacked on 1
├── 3. Admin UI ············· task 5       ▶ starts now, parallel with 1
└── Specs ··················· task 6       after 1–3 merge
```

A group is **stacked** on another when it builds on that group's code, **parallel** when it shares nothing with it, and **after** when it needs several groups merged first. Each group runs in its own session with `/blueprint apply <change> <group>`. The specs update always comes last. With the [review pane](/review-pane) installed, the plan is drawn beside the chat, with a start button for each group that is ready.

## Verify and fold

Before folding, apply checks every requirement and scenario in the delta against the code. Tests carry [scenario tags](/modes/coverage), so the evidence is the test that claims each scenario. A scenario no test claims counts as missing evidence.

Then it writes the specs as they should read now. It shows each one as a diff against the current page and writes on your yes. Afterwards it records the new sync point in `.blueprint/`, so the change doesn't show up as drift later.
