import { expect, test } from 'claude-code/testing'
import type { On } from 'claude-code'

const PANE = {
  plugin: 'blueprint-ui',
  component: 'Pane',
  requestId: 'blueprint-ui',
  props: { title: 'Blueprint', isFocused: false, bodyColumns: 80, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} },
} as const

const TOKENS = `# auth/tokens

## Purpose
Issue, refresh and revoke API tokens.

## Requirements

### Requirement: Token expiry
Tokens SHALL expire one hour after they are issued.

- **Scenario: Expired token rejected**
  - **WHEN** a token issued more than an hour ago is presented
  - **THEN** the request is refused with 401 <!-- verify: or 403? -->
- **Scenario: Fresh token accepted**
  - **WHEN** a token under an hour old is presented
  - **THEN** the request goes through

### Requirement: Revoke
A revoked token SHALL be refused.

- **Scenario: Revoked token refused**
  - **WHEN** a revoked token is presented
  - **THEN** the request is refused
`

const SESSION = `# auth/session

## Purpose
Keep a signed-in user signed in.

## Requirements

### Requirement: Idle timeout
A session SHALL end after 30 idle minutes.

- **Scenario: Idle session ends**
  - **WHEN** 30 minutes pass without a request
  - **THEN** the next request is sent to sign-in
`

const DIR = '/.blueprint/backfill'

/** A repo with a backfill at pass 3: auth has two drafts to review, the other domains none. */
function world(on: On) {
  const files: Record<string, string> = {
    '/.blueprint/blueprint.json': JSON.stringify({ docs: { backend: 'notion' }, specs: {}, changes: {} }),
    '/skills/blueprint/scripts/backfill.py': '# the script',
    [`${DIR}/progress.json`]: '{}',
    [`${DIR}/domains/auth.progress.json`]: JSON.stringify({ domain: 'auth', capabilities: { 'auth/tokens': {}, 'auth/session': {} } }, null, 2) + '\n',
    [`${DIR}/drafts/auth/tokens.md`]: TOKENS,
    [`${DIR}/drafts/auth/session.md`]: SESSION,
  }
  const sent: string[] = []
  const ran: string[] = []
  const domain = (name: string, done: boolean) => ({
    name,
    passes: { '2': 'done', '3': done ? 'done' : 'in-progress', '4': 'pending', '5': 'pending' },
    nextPass: done ? 4 : 3,
    folded: false,
    capabilities: [],
    drafts: Object.keys(files)
      .filter(p => p.startsWith(`${DIR}/drafts/${name}/`))
      .map(p => p.slice(`${DIR}/drafts/`.length, -3)),
  })
  const status = () => ({
    active: true,
    pass: 3,
    passName: 'spec drafts and scenario review',
    line: 'Backfill · pass 3 of 5 · 2 of 4 domains reviewed',
    passes: { '1': 'done' },
    domains: [domain('auth', false), domain('billing', false), domain('docs', true), domain('ui', true)],
    next: [
      { command: '/blueprint-backfill domain auth', domain: 'auth', pass: 3, why: 'pass 3 for auth (spec drafts and scenario review), in progress' },
      { command: '/blueprint-backfill domain billing', domain: 'billing', pass: 3, why: 'pass 3 for billing (spec drafts and scenario review)' },
    ],
  })
  const ok = (stdout: string, exitCode = 0) => ({ value: { exitCode, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })
  on('session.cwd', () => ({ value: '/' }))
  on('fs.read', (_, e) => (e.path in files ? { value: files[e.path]! } : { deny: `ENOENT: ${e.path}` }))
  on('fs.exists', (_, e) => ({ value: e.path in files }))
  on('fs.write', (_, e) => {
    files[e.path] = e.text
    return { value: undefined }
  })
  on('process.run', (_, e) => {
    const [, script, sub] = e.argv
    if (String(script).endsWith('backfill.py') && sub === 'status') return ok(JSON.stringify(status()))
    if (script === '.blueprint/drift.py' && sub === 'check') return ok('[]')
    return ok('')
  })
  on('tool.list', () => ({ value: [] }))
  on('tool.register', (_, e) => ({ value: { tool: e.name } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', () => ({ value: undefined }))
  on('command.register', () => ({ value: { command: 'blueprint-ui' } }))
  on('command.list', () => ({ value: [{ name: 'blueprint:blueprint-backfill', description: '', source: 'plugin' as const }] }))
  on('command.run', (_, e) => {
    ran.push(`/${e.command} ${e.args}`)
    return { text: '' }
  })
  on('prompt.submit', (_, e) => {
    sent.push(e.text)
    return { text: e.text }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  return { files, sent, ran }
}

const typed = (args = '') =>
  ({ command: 'blueprint-ui', args, origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 120 } }) as const

const review = (files: Record<string, string>) => JSON.parse(files[`${DIR}/domains/auth.progress.json`]!).capabilities['auth/tokens'].review

for (const surface of ['terminal', 'desktop'] as const) {
  // @scenario blueprint/ui: Backfill in progress
  // @scenario blueprint/ui: Reject a scenario
  // @scenario blueprint/backfill: Amend a scenario
  test(`the board's Backfill line opens the cards; each decision is saved before the next card, on ${surface}`, async ($, on) => {
    const { files, sent } = world(on)
    await $.session.start({ cwd: '/', surface, isInteractive: true })
    await $.command.run(typed())
    const ui = await $.ui.mount({ ...PANE, surface })

    // The board's first line is the backfill's.
    const texts = await ui.findAll({ type: 'Text' })
    expect(texts[0]?.text).toBe('Backfill · pass 3 of 5 · 2 of 4 domains reviewed')
    await ui.press({ key: 'backfill' })

    // auth is the one domain with drafts: its first card shows, with its statement and verify question.
    expect(await ui.find({ type: 'Text', text: 'Backfill · auth' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: 'Requirement: Token expiry' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: 'Tokens SHALL expire one hour after they are issued.' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: 'Verify: or 403?' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: '· card 1 of 3' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: '· 3 left in auth/tokens · 4 left in auth' })).toBeDefined()

    // Reject: saved, one fewer left, the next card showing.
    await ui.press({ key: 'bf-reject' })
    expect(files[`${DIR}/drafts/auth/tokens.md`]).not.toContain('Expired token rejected')
    expect(review(files)).toEqual({ accepted: 0, amended: 0, rejected: 1 })
    expect(await ui.find({ type: 'Text', text: '· 2 left in auth/tokens · 3 left in auth' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: '· card 2 of 3' })).toBeDefined()
    expect(await ui.find({ key: 'bf-card-auth/tokens-Fresh token accepted' })).toBeDefined()

    // Amend the THEN and save: the draft holds the new text, and the next card shows.
    await ui.press({ key: 'bf-amend' })
    await ui.input({
      key: 'bf-amend-scenario',
      kind: 'change',
      text: '- **Scenario: Fresh token accepted**\n  - **WHEN** a token under an hour old is presented\n  - **THEN** the request goes through with 200',
    })
    await ui.press({ key: 'bf-save' })
    expect(files[`${DIR}/drafts/auth/tokens.md`]).toContain('- **Scenario: Fresh token accepted** <!-- amended -->\n  - **WHEN** a token under an hour old is presented\n  - **THEN** the request goes through with 200')
    expect(review(files)).toEqual({ accepted: 0, amended: 1, rejected: 1 })
    expect(await ui.find({ type: 'Text', text: 'Requirement: Revoke' })).toBeDefined()
    expect(sent).toEqual([])

    // The capability's last card: accepted, and Claude is asked to write its spec; the next capability's card shows.
    await ui.press({ key: 'bf-accept' })
    expect(files[`${DIR}/drafts/auth/tokens.md`]).toContain('- **Scenario: Revoked token refused** <!-- accepted -->')
    expect(sent.length).toBe(1)
    expect(sent[0]).toContain('every scenario of auth/tokens is decided (1 accepted, 1 amended, 1 rejected)')
    expect(sent[0]).toContain("auth's next cards")
    expect(await ui.find({ type: 'Text', text: '· 1 left in auth/session · 1 left in auth' })).toBeDefined()

    await ui.press({ key: 'bf-back' })
    expect(await ui.find({ key: 'backfill' })).toBeDefined()
    await ui.unmount()
  })
}

test('the backfill tool opens a domain’s cards, and refuses a domain the backfill doesn’t have', async ($, on) => {
  const { ran } = world(on)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const bad = await $.tool.call({ tool: 'mcp__blueprint-ui__backfill', domain: 'nope' } as never)
  expect(String(bad.text)).toContain('Unknown domain "nope"')
  const got = await $.tool.call({ tool: 'mcp__blueprint-ui__backfill', domain: 'auth' } as never)
  expect(typeof got.result).toBe('string')
  expect(String(got.text)).toContain("auth's cards, from 2 drafts")

  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await ui.find({ key: 'bf-accept' })).toBeDefined()
  // A domain without drafts has no cards.
  await $.tool.call({ tool: 'mcp__blueprint-ui__backfill', domain: 'billing' } as never)
  expect(await ui.find({ type: 'Text', text: /^No cards left in billing/ })).toBeDefined()
  await ui.press({ key: 'bf-back' })
  await ui.press({ key: 'backfill' })
  // Back on the chooser: auth alone has drafts, so it opens straight on its cards.
  expect(await ui.find({ key: 'bf-accept' })).toBeDefined()
  await ui.unmount()
  expect(ran).toEqual([])
})

test('with drafts in two domains the view lists them with cards left, and runs a next step', async ($, on) => {
  const { files, ran } = world(on)
  files[`${DIR}/drafts/billing/invoices.md`] = SESSION.replace('auth/session', 'billing/invoices')
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run(typed())
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.press({ key: 'backfill' })

  expect(await ui.find({ key: 'bf-accept' })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: '· 2 drafts · 4 cards left' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: '· 1 draft · 1 card left' })).toBeDefined()
  await ui.press({ key: 'bf-next-1' })
  expect(ran).toEqual(['/blueprint:blueprint-backfill domain billing'])

  await ui.press({ key: 'bf-domain-billing' })
  expect(await ui.find({ type: 'Text', text: 'billing/invoices' })).toBeDefined()
  await ui.press({ key: 'bf-domains' })
  expect(await ui.find({ key: 'bf-domain-auth' })).toBeDefined()
  await ui.unmount()
})
