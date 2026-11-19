import { expect, test } from 'claude-code/testing'
import type { On } from 'claude-code'

import { isReady, splitOf, startPrompt, stateOf, treeOf } from './split'
import type { BlueprintUiSplit } from '../types'

const PANE = {
  plugin: 'blueprint-ui',
  component: 'Pane',
  requestId: 'blueprint-ui',
  props: { title: 'Blueprint', isFocused: false, bodyColumns: 80, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} },
} as const

const MAP = JSON.stringify({
  docs: { backend: 'notion' },
  specs: { 'auth/session': { ref: 'https://notion.so/a' } },
  changes: { 'add-sso': { brief: 'https://notion.so/brief', review: 'https://notion.so/review', status: 'building' } },
})

const PLAN = {
  change: 'add-sso',
  defaultBranch: 'main',
  groups: [
    { id: '1', name: 'Session store', tasks: '1, 2', base: 'main', prompt: '/blueprint apply add-sso 1\n\nBuilds the store.' },
    { id: '2', name: 'Login endpoint', tasks: '3, 4', base: '1', prompt: '/blueprint apply add-sso 2\n\nBuilds login.' },
    { id: '3', name: 'Admin UI', tasks: '5', base: 'main', prompt: '/blueprint apply add-sso 3\n\nBuilds the admin UI.' },
    { id: 'specs', name: 'Specs', tasks: '6', base: 'main', prompt: '/blueprint apply add-sso specs' },
  ],
}

const plan = (over: Partial<BlueprintUiSplit> = {}): BlueprintUiSplit => {
  const got = splitOf({ ...PLAN, isApproved: true, ...over })
  if ('error' in got) throw new Error(got.error)
  return got
}

test('the tree nests a stacked group under its base, parallel ones as siblings, Specs last', async () => {
  const rows = treeOf(plan()).map(r => `${r.prefix}${r.group.id}`)
  expect(rows).toEqual(['├── 1', '│   └── 2', '├── 3', '└── specs'])
})

test('a group is ready once approved and its base is main or has a PR; Specs once every group merged', async () => {
  const p = plan()
  expect(p.groups.filter(g => isReady(p, g)).map(g => g.id)).toEqual(['1', '3'])
  expect(stateOf(p, p.groups[1]!)).toBe("waits for group 1's PR")
  const opened = plan({ groups: PLAN.groups.map(g => (g.id === '1' ? { ...g, status: 'pr' } : g)) as never })
  expect(opened.groups.filter(g => isReady(opened, g)).map(g => g.id)).toEqual(['2', '3'])
  const merged = plan({ groups: PLAN.groups.map(g => (g.id === 'specs' ? g : { ...g, status: 'merged' })) as never })
  expect(merged.groups.filter(g => isReady(merged, g)).map(g => g.id)).toEqual(['specs'])
  const proposed = plan({ isApproved: false })
  expect(proposed.groups.filter(g => isReady(proposed, g))).toEqual([])
})

test('a plan with a base that is no group is refused', async () => {
  expect(splitOf({ ...PLAN, groups: [{ ...PLAN.groups[0], base: '9' }] })).toEqual({ error: 'group 1\'s base "9" is neither main nor a group.' })
})

test("the start prompt carries each group's own prompt", async () => {
  const p = plan()
  const text = startPrompt(p, [p.groups[0]!, p.groups[2]!])
  expect(text).toContain('Start these 2 groups of the blueprint change add-sso')
  expect(text).toContain('/blueprint apply add-sso 1\n\nBuilds the store.')
  expect(text).toContain('/blueprint apply add-sso 3')
  expect(text).not.toContain('add-sso 2')
})

function host(on: On) {
  const sent: string[] = []
  on('fs.read', () => ({ value: MAP }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('prompt.submit', (_, e) => {
    sent.push(e.text)
    return { text: e.text }
  })
  return sent
}

test('the split tool shows the plan in the pane; ▶ start sends the prompt once approved', async ($, on) => {
  const sent = host(on)
  const proposed = await $.tool.call({ tool: 'mcp__blueprint-ui__split', ...PLAN, isApproved: false } as never)
  expect(String(proposed.text)).toContain('as a proposal')

  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await ui.find({ type: 'Text', text: /^add-sso · PRs$/ })).toBeDefined()
  expect(await ui.find({ key: 'group-2' })).toBeDefined()
  expect(await ui.find({ key: 'start-1' })).toBeUndefined()

  await $.tool.call({ tool: 'mcp__blueprint-ui__split', ...PLAN, isApproved: true } as never)
  expect(await ui.find({ key: 'start-1' })).toBeDefined()
  expect(await ui.find({ key: 'start-2' })).toBeUndefined()
  await ui.press({ key: 'start-1' })
  expect(sent.length).toBe(1)
  expect(sent[0]).toContain('Start group 1 of the blueprint change add-sso')
  expect(await ui.find({ key: 'start-1' })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: 'starting…' })).toBeDefined()

  // Start all takes what is left ready: group 3 alone now, so there is no start-all button.
  expect(await ui.find({ key: 'start-all' })).toBeUndefined()
  await ui.press({ key: 'split-back' })
  expect(await ui.find({ key: 'prs-add-sso' })).toBeDefined()
  await ui.press({ key: 'prs-add-sso' })
  expect(await ui.find({ key: 'group-1' })).toBeDefined()
  await ui.unmount()
})

test('start all sends every ready group in one prompt', async ($, on) => {
  const sent = host(on)
  await $.tool.call({ tool: 'mcp__blueprint-ui__split', ...PLAN, isApproved: true } as never)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: 'start-all' })
  expect(sent.length).toBe(1)
  expect(sent[0]).toContain('Start these 2 groups')
  await ui.unmount()
})
