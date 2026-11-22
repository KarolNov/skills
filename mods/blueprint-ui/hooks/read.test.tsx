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

const REF = 'notion-file-block://a/b?space_id=s&name=flow.svg'
const DIAGRAM = `## Picture\n\n<image source="${REF.replace('&', '&amp;')}">\nThe flow\n</image>\n\n<image source="notion-file-block://c/d?name=shot.png">A shot</image>\n`
const SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'

// @scenario blueprint/ui: Review with diagrams on the desktop
test('an uploaded SVG diagram is downloaded and drawn on the desktop; the terminal keeps the link', async ($, on) => {
  const asked: unknown[] = []
  const fetched: string[] = []
  on('fs.read', () => ({ value: map('notion') }))
  on('tool.list', () => ({ value: [{ name: 'mcp__3c44__notion-fetch', description: 'Fetch', mcp: true }] }))
  on('mcp.call', (_, e) => {
    if (e.server !== '3c44') throw new Error(`no server ${e.server}`)
    if (e.tool === 'notion-get-file-download-urls') {
      asked.push(e.args.references)
      const files = [{ reference: REF, url: 'https://files.example/flow.svg?sig=1' }]
      return { value: { content: [{ type: 'text', text: JSON.stringify({ files, unresolved: [] }) }], isError: false } }
    }
    return { value: { content: [{ type: 'text', text: 'page' }], isError: false } }
  })
  on('process.run', (_, e) => ({ value: { exitCode: 0, stdout: DIAGRAM, stderr: '', isStdoutTruncated: false, isStderrTruncated: false, argv: e.argv } }))
  on('http.fetch', (_, e) => {
    fetched.push(e.url)
    return { value: { status: 200, ok: true, headers: { 'content-type': 'image/svg+xml' }, text: `<?xml version="1.0"?>\n${SVG}\n` } }
  })

  const desktop = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await desktop.press({ key: 'spec:auth/session' })
  const svg = await desktop.find({ type: 'Svg' })
  expect(svg?.props).toEqual({ source: SVG, alt: 'Image: The flow' })
  expect(await desktop.find({ type: 'Text', text: /^The flow$/ })).toBeDefined()
  // Only the SVG is asked for; the PNG stays a link.
  expect(asked).toEqual([[REF]])
  expect(fetched).toEqual(['https://files.example/flow.svg?sig=1'])
  expect(await desktop.find({ type: 'Link', text: /Image: A shot/ })).toBeDefined()
  await desktop.press({ key: 'back' })
  await desktop.unmount()

  const terminal = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await terminal.press({ key: 'spec:auth/session' })
  expect(await terminal.find({ type: 'Link', text: /Image: The flow \(open in Notion\)/ })).toBeDefined()
  await terminal.unmount()
})

const DRAWN = '┌──────┐\n│ open │\n└──┬───┘\n   ▼\n Board'
const WITH_TEXT = `<image source="${REF.replace('&', '&amp;')}">\nThe flow\n</image>\n\n<toggle>\n<span color="gray">Mermaid source</span>\n\n\`\`\`mermaid\nflowchart TD\n  A --> B\n\`\`\`\n\n<span color="gray">Terminal version</span>\n\n\`\`\`text\n${DRAWN}\n\`\`\`\n</toggle>\n`

// @scenario blueprint/ui: Review with diagrams in the terminal
test("the terminal draws a diagram's text version in place of its image; the desktop keeps the SVG", async ($, on) => {
  on('fs.read', () => ({ value: map('notion') }))
  on('tool.list', () => ({ value: [{ name: 'mcp__3c44__notion-fetch', description: 'Fetch', mcp: true }] }))
  on('mcp.call', (_, e) => {
    if (e.server !== '3c44') throw new Error(`no server ${e.server}`)
    if (e.tool === 'notion-get-file-download-urls') {
      const files = [{ reference: REF, url: 'https://files.example/flow.svg' }]
      return { value: { content: [{ type: 'text', text: JSON.stringify({ files }) }], isError: false } }
    }
    return { value: { content: [{ type: 'text', text: 'page' }], isError: false } }
  })
  on('process.run', (_, e) => ({ value: { exitCode: 0, stdout: WITH_TEXT, stderr: '', isStdoutTruncated: false, isStderrTruncated: false, argv: e.argv } }))
  on('http.fetch', () => ({ value: { status: 200, ok: true, headers: {}, text: SVG } }))

  const terminal = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await terminal.press({ key: 'spec:auth/session' })
  expect((await terminal.find({ type: 'Code' }))?.props).toEqual({ source: DRAWN })
  expect(await terminal.find({ type: 'Text', text: /^The flow$/ })).toBeDefined()
  expect(await terminal.find({ type: 'Link', text: /Image: The flow/ })).toBeUndefined()
  await terminal.press({ key: 'back' })
  await terminal.unmount()

  const desktop = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await desktop.press({ key: 'spec:auth/session' })
  expect(await desktop.find({ type: 'Svg' })).toBeDefined()
  expect(await desktop.find({ type: 'Code' })).toBeUndefined()
  await desktop.unmount()
})

// @scenario blueprint/ui: Diagram without a terminal version
test('a diagram that does not download stays a link', async ($, on) => {
  on('fs.read', () => ({ value: map('notion') }))
  on('tool.list', () => ({ value: [{ name: 'mcp__3c44__notion-fetch', description: 'Fetch', mcp: true }] }))
  on('mcp.call', (_, e) => {
    if (e.server !== '3c44') throw new Error(`no server ${e.server}`)
    if (e.tool === 'notion-get-file-download-urls') {
      const files = [{ reference: REF, url: 'https://files.example/flow.svg' }]
      return { value: { content: [{ type: 'text', text: JSON.stringify({ files }) }], isError: false } }
    }
    return { value: { content: [{ type: 'text', text: 'page' }], isError: false } }
  })
  on('process.run', (_, e) => ({ value: { exitCode: 0, stdout: DIAGRAM, stderr: '', isStdoutTruncated: false, isStderrTruncated: false, argv: e.argv } }))
  on('http.fetch', () => ({ value: { status: 403, ok: false, headers: {}, text: '<Error>expired</Error>' } }))
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await ui.press({ key: 'spec:auth/session' })
  expect(await ui.find({ type: 'Link', text: /Image: The flow \(open in Notion\)/ })).toBeDefined()
  expect(await ui.find({ type: 'Svg' })).toBeUndefined()
  await ui.unmount()
})

// @scenario blueprint/ui: No Notion connection
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

// @scenario blueprint/ui: Other backend
test('another backend: not supported yet, with the link', async ($, on) => {
  on('fs.read', () => ({ value: map('obsidian') }))
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: 'spec:auth/session' })
  expect(await ui.find({ type: 'Text', text: /doesn't read the obsidian backend yet/ })).toBeDefined()
  await ui.unmount()
})

// @scenario blueprint/ui: Connection comes up during the wait
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
