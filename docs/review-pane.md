# Review pane

`blueprint-ui` is a mod: a pane that opens beside the chat in Claude Code and shows blueprint's pages without leaving the session. It works the same in the terminal and in the desktop app.

```
/plugin install blueprint-ui@karolnov-skills
```

## Reading

Open it with `/blueprint-ui`, or `/blueprint-ui <change or capability>` to go straight to a page. It lists the reviews, briefs and specs that `.blueprint/blueprint.json` maps, and shows the one you choose, read-only. The pane reads Notion through your session's Notion connection. The server name is a setting, `claude.ai Notion` by default.

## Commenting

Press **+** beside any block to comment on it or suggest new wording, as on a GitHub diff line. Comments batch up like a pending review. **Submit review** hands the batch to `/blueprint review`, which turns each item into an edit, shows one preview, and writes on your yes. A review never changes the brief on its own. Comments on a review become proposed changes to the brief, and the review is rebuilt from the brief afterwards.

## Splitting into PRs

When [Apply](/modes/apply#big-changes-become-several-prs) splits a big change into PR groups, the pane draws the plan as a tree, with a start button for each group that can begin. As groups open PRs and merge, the buttons for the groups waiting on them appear.

## Backfill

While a [backfill](/modes/backfill) is in progress, the board's first line shows its pass. Choosing it opens the Backfill view: one scenario card at a time, with **Accept**, **Amend** and **Reject**, and each decision saved before the next card.
