import { expect, test } from 'claude-code/testing'

import { blocksOf } from './blocks'

const PAGE = 'https://app.notion.com/p/review'

const REVIEW = `Brief: <mention url="https://app.notion.com/p/brief">Add SSO: brief</mention> · Built from brief \`abc\`

## Picture

<image source="notion-file-block://x?name=before-after.svg">
Before → after: the pane reads pages.
</image>

<toggle>
<span color="gray">Mermaid source</span>

\`\`\`mermaid
flowchart LR
  A --> B
\`\`\`
</toggle>

## Behavior

- **New** · Open the pane: lists pages.
- **Scenario: Flaky network**
  - **WHEN** the first two uploads time out
  - **THEN** the third try succeeds

A paragraph
over two lines.

| a | b |
| --- | --- |
| 1 | 2 |

\`\`\`ts
const x = 1

const y = 2
\`\`\`

<embed source="notion-file-block://y?name=playground.html" />

<page url="https://app.notion.com/p/brief">
Add SSO: brief
</page>
`

test('a review splits into blocks, with links in place of media', () => {
  const blocks = blocksOf(REVIEW, PAGE)
  const shown = blocks.map(b => (b.kind === 'link' ? `link:${b.label}->${b.href}` : `md:${b.text.split('\n')[0]}`))
  expect(shown).toEqual([
    'md:Brief: [Add SSO: brief](https://app.notion.com/p/brief) · Built from brief `abc`',
    'md:## Picture',
    `link:Image: Before → after: the pane reads pages.->${PAGE}`,
    'md:## Behavior',
    'md:- **New** · Open the pane: lists pages.',
    'md:- **Scenario: Flaky network**',
    'md:A paragraph',
    'md:| a | b |',
    'md:```ts',
    `link:Embedded page->${PAGE}`,
    'link:Add SSO: brief->https://app.notion.com/p/brief',
  ])
  // The scenario keeps its nested lines; the fence keeps its blank line; headings carry over.
  const scenario = blocks[5]!
  expect(scenario.kind === 'md' && scenario.text.split('\n').length).toBe(3)
  expect(scenario.heading).toBe('Behavior')
  const fence = blocks[8]!
  expect(fence.kind === 'md' && fence.text.includes('\n\n')).toBe(true)
  expect(blocks[2]!.heading).toBe('Picture')
})

test('a toggle that is not a diagram shows its content', () => {
  const blocks = blocksOf('<toggle>\nDetails\n\nHidden text.\n</toggle>\n', PAGE)
  expect(blocks).toHaveLength(1)
  expect(blocks[0]!.kind === 'md' && blocks[0]!.text).toBe('**▸ Details**\n\nHidden text.')
})

import { rowsFor } from './review'

test('the suggest field grows with its text, wrapped lines included, up to a max', () => {
  expect(rowsFor('one line', 60)).toBe(2)
  expect(rowsFor('a\nb\nc\nd', 60)).toBe(4)
  expect(rowsFor('x'.repeat(150), 60)).toBe(3)
  expect(rowsFor(Array(40).fill('line').join('\n'), 60)).toBe(12)
})
