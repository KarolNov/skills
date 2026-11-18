# Review

Apply a review submitted from the `blueprint-ui` pane: a batch of comments and suggested wording, each anchored to a block of one page. The pane only reads; every write happens here, through the backend's own rules.

`/blueprint review <file> — <summary>`: the first word after `review` is the path to the review file; the rest is a readable summary for the transcript and is ignored.

## 1. Read the batch

The file is JSON:

```json
{
  "version": 1,
  "page": { "id": "change:add-sso:brief", "kind": "brief", "name": "add-sso", "url": "https://…" },
  "items": [
    { "id": "…", "heading": "Requirement: Login", "quote": "<the block's text as it read>", "kind": "comment", "text": "why five?" },
    { "id": "…", "heading": "Decisions", "quote": "<the block's text>", "kind": "suggest", "text": "<the block's new text>" }
  ]
}
```

`kind` of the page is `review`, `brief` or `spec`. Every item quotes the **whole block** it was made on (a paragraph, a heading, a table, a code fence, or one top-level list item with its nested lines), as the pane drew it from the normalized page. Read the file once; never edit it.

## 2. Find each anchor

Fetch the page as it reads now, normalized as the backend file says, and locate each item by its quote under its heading:

- Compare ignoring whitespace and Markdown markup (`**`, backticks, list markers, escapes).
- The quote under the item's heading wins; otherwise the first match on the page.
- No match: the page changed since the review was made. Keep the item aside as **not found**, never guess where it went.

## 3. Route by page kind

| Page | Where the edit goes |
| --- | --- |
| `brief` | The brief itself; then rebuild the review from it (SKILL.md's rule), playground too if touched. |
| `review` | The **brief**: find what the quoted review text was built from (the decision, requirement or task it restates) and edit that. Never edit the review by hand; rebuild it from the brief. |
| `spec` | The spec, only if the item changes **wording** (clearer text, same behavior), followed by the spec bookkeeping in [status.md](status.md). An item that changes **behavior** (what the system does, a scenario's outcome) is not applied: list it back and offer `/blueprint <that change>`, since specs describe the system as built. |

## 4. Turn items into edits

- **Suggestion**: replace the quoted block with the suggested text, word for word. Don't reword it, even to match the page's style.
- **Comment**: make the smallest edit that does what it asks. If it can't become an edit as written ("unclear", a question with no answer in it, two readings), ask about it before the preview, one short question per comment, all in one round. A comment the user answers with "leave it" is dropped.
- An item on a brief that would change the spec delta is still applied, but say so in the preview: the delta is what apply folds into specs later.

## 5. One preview, one yes

Show every edit in one preview, grouped by section of the page, each as a before → after of its block, then the items not found and any behavior changes listed back from a spec. Write nothing until the user says yes; a yes covers the whole batch. If they want one edit changed or dropped, change the preview and show it again.

On yes: write the edits through the backend (one update with all of them where the backend allows), rebuild the review if the brief changed, and for a spec do the bookkeeping. The `blueprint-ui` pane refreshes by itself once the page is written.

## Done when

Every item is applied, listed as not found, or offered as a blueprint, and the page reads back with the edits. Report: what was applied (linked), what wasn't and why.
