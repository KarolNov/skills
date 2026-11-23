import { expect, mock, test } from 'claude-code/testing'
import type { EngineInterface, On } from 'claude-code'

import { READ_TOOL, idsIn, pagesNamed, pagesOf } from './pages'
import { firstChange, sameText } from './review'
import { blocksOf } from './blocks'
import { typeInto } from './typing'

const PANE = {
  plugin: 'blueprint-ui',
  component: 'Pane',
  requestId: 'blueprint-ui',
  props: { title: 'Blueprint', isFocused: false, bodyColumns: 70, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} },
} as const

const BRIEF = 'https://app.notion.com/p/41c43cce21f281aab4cdf8edc10c9d8a'
const REVIEW = 'https://app.notion.com/p/41c43cce21f2816c8bc6c76cfdbd313d'
const MAP = JSON.stringify({
  docs: { backend: 'notion' },
  specs: { 'upload/retry': { ref: 'https://app.notion.com/p/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' } },
  changes: { 'add-ui': { brief: BRIEF, review: REVIEW } },
})

// Tool names from a made-up server, which this build's tool table doesn't list.
type Caller = { tool: { call: EngineInterface['tool']['call'] } }
const call = ($: Caller, input: Record<string, unknown>) => $.tool.call(input as unknown as Parameters<EngineInterface['tool']['call']>[0])

function world(on: On, page: { text: string }) {
  const opened: string[] = []
  on('fs.read', () => ({ value: MAP }))
  on('tool.list', () => ({ value: [] }))
  on('ui.open', (_, e) => {
    opened.push(String(e.id))
    return { value: { isPlaced: true } }
  })
  on('mcp.call', () => ({ value: { content: [{ type: 'text', text: 'page' }], isError: false } }))
  on('process.run', () => ({
    value: { exitCode: 0, stdout: page.text, stderr: '', isStdoutTruncated: false, isStderrTruncated: false },
  }))
  // The engine's own tool run, beneath the plugin.
  on('tool.call', () => ({ result: {} }))
  return opened
}

test('ids, mapped pages and read tools', () => {
  expect(idsIn(`x ${BRIEF} 41c43cce-21f2-816c-8bc6-c76cfdbd313d`)).toEqual([
    '41c43cce21f281aab4cdf8edc10c9d8a',
    '41c43cce21f2816c8bc6c76cfdbd313d',
  ])
  const { pages } = pagesOf(MAP)
  expect(pagesNamed(pages, JSON.stringify({ page_id: '41c43cce-21f2-81aa-b4cd-f8edc10c9d8a' })).map(p => p.id)).toEqual(['change:add-ui:brief'])
  expect(pagesNamed(pages, JSON.stringify({ page_id: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' }))).toEqual([])
  expect(READ_TOOL.test('mcp__3c44__notion-fetch')).toBe(true)
  expect(READ_TOOL.test('mcp__3c44__notion-get-comments')).toBe(true)
  expect(READ_TOOL.test('mcp__3c44__notion-update-page')).toBe(false)
  expect(READ_TOOL.test('mcp__3c44__notion-create-pages')).toBe(false)
  expect(sameText('- **Scenario: X**\n  - **WHEN** a', 'Scenario: X WHEN a')).toBe(true)
  expect(sameText('at most five', 'at most three')).toBe(false)
})

// @scenario blueprint/ui: Brief rewritten
// @scenario blueprint/ui: Unrelated page
test('a write to a mapped page opens the pane on it; reads and unmapped pages do nothing', async ($, on) => {
  const page = { text: '## Decisions\n\nShip it.\n' }
  const opened = world(on, page)

  await call($, { tool: 'mcp__3c44__notion-fetch', id: BRIEF })
  await call($, { tool: 'mcp__3c44__notion-update-page', page_id: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' })
  expect(opened).toEqual([])

  await call($, { tool: 'mcp__3c44__notion-update-page', page_id: '41c43cce-21f2-81aa-b4cd-f8edc10c9d8a', command: 'update_content' })
  expect(opened).toEqual(['blueprint-ui'])
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await ui.find({ type: 'Text', text: /^add-ui · brief$/ })).toBeDefined()
  expect(await ui.find({ key: 'b1' })).toBeDefined()
  await ui.unmount()
})

for (const surface of ['terminal', 'desktop'] as const) {
  // @scenario blueprint/ui: Quote edited away
  test(`a pending item whose quote is gone after a refresh is kept and marked outdated, on ${surface}`, async ($, on) => {
    const page = { text: '## Decisions\n\nShip it on Friday.\n\nKeep the flag.\n' }
    world(on, page)
    await call($, { tool: 'mcp__3c44__notion-update-page', page_id: '41c43cce21f281aab4cdf8edc10c9d8a' })
    const ui = await $.ui.mount({ ...PANE, surface })
    await ui.press({ key: 'plus-1' })
    await typeInto(ui, 'comment-1', 'why Friday?')
    expect(await ui.find({ type: 'Text', text: /outdated/ })).toBeUndefined()

    // Blueprint rewrites the sentence: the write refreshes the pane.
    page.text = '## Decisions\n\nShip it on Monday.\n\nKeep the flag.\n'
    await call($, { tool: 'mcp__3c44__notion-update-page', page_id: '41c43cce21f281aab4cdf8edc10c9d8a' })
    expect(await ui.find({ type: 'Text', text: /Pending review · 1 comment/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /outdated/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /Ship it on Friday/ })).toBeDefined()
    await ui.unmount()
  })
}

test('firstChange finds the first block a write changed', () => {
  const before = blocksOf('## A\n\none\n\ntwo\n\nthree\n', 'u')
  expect(firstChange(before, blocksOf('## A\n\none\n\nTWO\n\nthree\n', 'u'))).toBe(2)
  expect(firstChange(before, blocksOf('## A\n\none\n\nthree\n', 'u'))).toBe(2)
  expect(firstChange(before, blocksOf('## A\n\none\n\ntwo\n\nthree\n\nfour\n', 'u'))).toBe(4)
  expect(firstChange(before, blocksOf('## A\n\none   \n\ntwo\n\nthree\n', 'u'))).toBeUndefined()
})

for (const surface of ['terminal', 'desktop'] as const) {
  // @scenario blueprint/ui: Write to the page showing
  test(`a write scrolls to the first changed block and lights it briefly, on ${surface}`, async ($, on) => {
    const clock = mock.clock(on)
    const page = { text: '## Decisions\n\nShip it on Friday.\n\nKeep the flag.\n' }
    world(on, page)
    await call($, { tool: 'mcp__3c44__notion-update-page', page_id: '41c43cce21f281aab4cdf8edc10c9d8a' })
    const ui = await $.ui.mount({ ...PANE, surface })
    // The first read marks nothing: there was nothing to compare with.
    expect((await ui.find({ key: 'block-1' }))?.props?.backgroundColor).toBeUndefined()

    page.text = '## Decisions\n\nShip it on Friday.\n\nDrop the flag.\n'
    await call($, { tool: 'mcp__3c44__notion-update-page', page_id: '41c43cce21f281aab4cdf8edc10c9d8a' })
    expect((await ui.find({ key: 'block-2' }))?.props?.backgroundColor).toBe('diffAddedDimmed')
    expect((await ui.find({ key: 'block-1' }))?.props?.backgroundColor).toBeUndefined()

    await clock.advance(3000)
    expect((await ui.find({ key: 'block-2' }))?.props?.backgroundColor).toBeUndefined()
    await ui.unmount()
  })
}

// @scenario blueprint/ui: Content only links a mapped page
test('a write to an unmapped page whose content links a mapped one leaves the pane as it is', async ($, on) => {
  const page = { text: '## Decisions\n\nShip it.\n' }
  const opened = world(on, page)
  // The pane is showing the review.
  await call($, { tool: 'mcp__3c44__notion-update-page', page_id: '41c43cce21f2816c8bc6c76cfdbd313d', command: 'update_content' })
  expect(opened).toEqual(['blueprint-ui'])
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await ui.find({ type: 'Text', text: /^add-ui · review$/ })).toBeDefined()

  await call($, {
    tool: 'mcp__3c44__notion-update-page',
    page_id: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    command: 'replace_content',
    new_str: `See the [brief](${BRIEF}) and the review ${REVIEW}.`,
  })
  await call($, {
    tool: 'mcp__3c44__notion-create-pages',
    parent: { page_id: 'cccccccccccccccccccccccccccccccc' },
    pages: [{ properties: { title: 'Notes' }, content: `Links ${BRIEF}` }],
  })
  expect(opened).toEqual(['blueprint-ui'])
  expect(await ui.find({ type: 'Text', text: /^add-ui · review$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^add-ui · brief$/ })).toBeUndefined()
  await ui.unmount()
})
