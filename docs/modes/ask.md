# Ask

```
/blueprint-ask <question>
```

Ask answers *how should X work?* or *how does X work?* from the capability specs, after checking that each spec still agrees with the code. It also starts on its own when you ask that kind of question in a repo with blueprint, whether in the terminal or through an agent such as Claude in Slack.

## How it answers

It finds the capabilities your question is about, then checks both sides:

- **Code side**: has the capability's code moved since its spec was last synced? This comes from git, the same way as [drift](/modes/drift).
- **Spec side**: has someone edited the spec page since then?

The answer depends on what it finds:

| Code | Spec | Answer |
| --- | --- | --- |
| in sync | unchanged | Straight from the spec, with the requirement quoted and the page linked. |
| moved | unchanged | *"The spec says X; the code does Y"*, naming the changed files. It points to `/blueprint-sync` if the code is right, or `/blueprint-drift` if the spec is. |
| in sync | edited | From the current page, noting that the edited part isn't built yet. |
| moved | edited | Both, pointing to `/blueprint-drift` first. |

If the backend can't be reached, it answers from the spec text in `.blueprint/baseline/` and says so.

## Read only

Ask never writes anything: no specs, no stamps, no code, no tickets. When you ask it to *change* behavior, it points you to [`/blueprint`](/modes/propose).
