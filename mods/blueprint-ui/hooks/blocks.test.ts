import { expect, test } from 'claude-code/testing'

import { blocksOf, svgSource, terminalVersion } from './blocks'
import { SVG_MAX, svgMarkup } from './notion'

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

test('an uploaded SVG image carries its reference; other media do not', () => {
  const blocks = blocksOf(REVIEW, PAGE)
  const image = blocks[2]!
  expect(image.kind === 'link' && image.picture).toBe('notion-file-block://x?name=before-after.svg')
  const embed = blocks[9]!
  expect(embed.kind === 'link' && embed.picture).toBe(undefined)
  const png = blocksOf('<image source="notion-file-block://p?space_id=s&amp;name=shot.png">A shot</image>\n', PAGE)[0]!
  expect(png.kind === 'link' && png.picture).toBe(undefined)
  const external = blocksOf('<image source="https://example.com/a.svg"></image>\n', PAGE)[0]!
  expect(external.kind === 'link' && external.picture).toBe(undefined)
})

test('an image reference has its &amp; undone and its name read encoded', () => {
  expect(svgSource('<image source="notion-file-block://a/b?space_id=s&amp;name=flow%20chart.svg">')).toBe(
    'notion-file-block://a/b?space_id=s&name=flow%20chart.svg',
  )
  expect(svgSource('<image source="notion-file-block://a/b?space_id=s&name=bad%zz.svg">')).toBe(
    'notion-file-block://a/b?space_id=s&name=bad%zz.svg',
  )
})

test('only a whole SVG document within the size cap is drawable', () => {
  expect(svgMarkup('<?xml version="1.0"?>\n<svg xmlns="x"><g/></svg>\n')).toBe('<svg xmlns="x"><g/></svg>')
  expect(svgMarkup('<html>nope</html>')).toBe(undefined)
  expect(svgMarkup('<svg><g/>')).toBe(undefined)
  expect(svgMarkup(`<svg>${'x'.repeat(SVG_MAX)}</svg>`)).toBe(undefined)
})

const DRAWN = '┌────┐\n│ A  │\n└─┬──┘\n  ▼\n  B'

test("a diagram toggle's terminal version goes on its image; a toggle without one leaves it off", () => {
  const page = (lang: string) =>
    `<image source="notion-file-block://x?name=flow.svg">\nThe flow\n</image>\n\n<toggle>\n<span color="gray">Mermaid source</span>\n\n\`\`\`mermaid\nflowchart TD\n  A --> B\n\`\`\`\n\n<span color="gray">Terminal version</span>\n\n\`\`\`${lang}\n${DRAWN}\n\`\`\`\n</toggle>\n`
  for (const lang of ['text', 'plain text', '']) {
    const blocks = blocksOf(page(lang), PAGE)
    expect(blocks).toHaveLength(1)
    expect(blocks[0]!.kind === 'link' && blocks[0]!.diagram).toBe(DRAWN)
  }
  // The review above has a Mermaid-only toggle: no terminal version.
  const image = blocksOf(REVIEW, PAGE)[2]!
  expect(image.kind === 'link' && image.diagram).toBe(undefined)
  expect(terminalVersion(['```mermaid', 'flowchart TD', '```'])).toBe(undefined)
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
