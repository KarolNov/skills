import { expect, mock, test } from 'claude-code/testing'

const PANE = {
  plugin: 'blueprint-ui',
  component: 'Pane',
  requestId: 'blueprint-ui',
  props: { title: 'Blueprint', isFocused: false, bodyColumns: 60, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} },
} as const

const map = (backend: string) =>
  JSON.stringify({ docs: { backend }, specs: { 'auth/session': { ref: 'https://notion.so/spec' } }, changes: {} })

const SPEC = '## Requirement: Login\n\nThe user SHALL log in with SSO.\n\n<image source="x">Flow</image>\n'

test('a Notion page is fetched, normalized and drawn block by block', async ($, on) => {
  const calls: string[] = []
  on('fs.read', () => ({ value: map('notion') }))
  on('tool.list', () => ({ value: [{ name: 'mcp__3c44__notion-fetch', description: 'Fetch', mcp: true }, { name: 'Read', description: 'Read', mcp: false }] }))
  on('mcp.call', (_, e) => {
    calls.push(String(e.server))
    if (e.server !== '3c44') throw new Error(`no server ${e.server}`)
    return { value: { content: [{ type: 'text', text: JSON.stringify({ text: `<content>\n${SPEC}</content>` }) }], isError: false } }
  })
  on('process.run', (_, e) => ({ value: { exitCode: 0, stdout: SPEC, stderr: '', isStdoutTruncated: false, isStderrTruncated: false, argv: e.argv } }))

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    await ui.press({ key: 'spec:auth/session' })
    expect(await ui.find({ key: 'b0' })).toBeDefined()
    expect(await ui.find({ key: 'b1' })).toBeDefined()
    const img = await ui.find({ type: 'Link', text: /Image: Flow \(open in Notion\)/ })
    expect(img?.props).toEqual({ href: 'https://notion.so/spec', label: '↗ Image: Flow (open in Notion)' })
    await ui.press({ key: 'back' })
    await ui.unmount()
  }
  // The configured name first, then the server that has notion-fetch.
  expect(calls.slice(0, 2)).toEqual(['claude.ai Notion', '3c44'])
})

test('no Notion server: the pane waits for it, then names what it tried and the setting', async ($, on) => {
  const clock = mock.clock(on)
  on('fs.read', () => ({ value: map('notion') }))
  on('tool.list', () => ({ value: [] }))
  on('mcp.call', () => {
    throw new Error('no such server')
  })
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await ui.press({ key: 'spec:auth/session' })
  expect(await ui.find({ type: 'Text', text: /Waiting for the Notion connection/ })).toBeDefined()
  // Each retry sleeps anew once the last one woke: move the clock past every one.
  for (let i = 0; i < 16; i++) await clock.advance(1000)
  expect(await ui.find({ type: 'Text', text: /"claude.ai Notion" or "Notion"/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Last error: .+Notion server/ })).toBeDefined()
  await ui.unmount()
})

test('another backend: not supported yet, with the link', async ($, on) => {
  on('fs.read', () => ({ value: map('obsidian') }))
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: 'spec:auth/session' })
  expect(await ui.find({ type: 'Text', text: /doesn't read the obsidian backend yet/ })).toBeDefined()
  await ui.unmount()
})

test('a Notion connection that comes up within the wait is read', async ($, on) => {
  const clock = mock.clock(on)
  let isUp = false
  on('fs.read', () => ({ value: map('notion') }))
  on('tool.list', () => ({ value: [] }))
  on('mcp.call', () => {
    if (!isUp) throw new Error('no such server')
    return { value: { content: [{ type: 'text', text: 'page' }], isError: false } }
  })
  on('process.run', () => ({ value: { exitCode: 0, stdout: SPEC, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: 'spec:auth/session' })
  expect(await ui.find({ type: 'Text', text: /Waiting for the Notion connection/ })).toBeDefined()
  isUp = true
  await clock.advance(1000)
  expect(await ui.find({ key: 'b0' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /No Notion connection/ })).toBeUndefined()
  await ui.unmount()
})
