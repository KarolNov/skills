import { expect, test } from 'claude-code/testing'

import { cardOf, counted, countsOf, decide, decidedPrompt, installedScripts, orderOf, parseDraft, reviewOf } from './backfill'
import { backfillLineOf, backfillStep } from './board'

const DRAFT = `# auth/tokens

## Purpose
Issue, refresh and revoke API tokens. <!-- verify: are revoked tokens kept? -->

## Requirements

### Requirement: Token expiry
Tokens SHALL expire one hour after they are issued.

- **Scenario: Expired token rejected**
  - **GIVEN** a token issued more than an hour ago
  - **WHEN** it is presented
  - **THEN** the request is refused with 401 <!-- verify: or 403? -->
- **Scenario: Fresh token accepted**
  - **WHEN** a token under an hour old is presented
  - **THEN** the request goes through

### Requirement: Revoke
A revoked token SHALL be refused. <!-- verify: at once, or after the cache expires? -->

- **Scenario: Revoked token refused**
  - **WHEN** a revoked token is presented
  - **THEN** the request is refused
`

const apply = (text: string, name: string, d: Parameters<typeof decide>[3]) => {
  const got = decide(text, 'auth/tokens', name, d)
  if ('error' in got) throw new Error(got.error)
  return got.text
}

test('the first card: the Purpose, its requirement statement as editable, and every verify mark it shows as a question', () => {
  const card = cardOf('auth/tokens', parseDraft(DRAFT))!
  expect(card).toMatchObject({
    capability: 'auth/tokens',
    requirement: 'Token expiry',
    name: 'Expired token rejected',
    statement: 'Tokens SHALL expire one hour after they are issued.',
    isFirstOfRequirement: true,
    purpose: 'Issue, refresh and revoke API tokens.',
    verify: ['are revoked tokens kept?', 'or 403?'],
  })
  expect(card.scenario).toBe(
    '- **Scenario: Expired token rejected**\n  - **GIVEN** a token issued more than an hour ago\n  - **WHEN** it is presented\n  - **THEN** the request is refused with 401',
  )
  expect(countsOf(parseDraft(DRAFT))).toEqual({ decided: 0, undecided: 3 })
})

test('accept marks the scenario and drops the verify marks the card showed; the next card shows no Purpose', () => {
  const text = apply(DRAFT, 'Expired token rejected', { kind: 'accept' })
  expect(text).toContain('- **Scenario: Expired token rejected** <!-- accepted -->')
  expect(text).toContain('Issue, refresh and revoke API tokens.\n')
  expect(text).not.toContain('are revoked tokens kept')
  expect(text).not.toContain('or 403?')
  // A mark the card didn't show stays for its own card.
  expect(text).toContain('<!-- verify: at once, or after the cache expires? -->')
  const next = cardOf('auth/tokens', parseDraft(text))!
  expect(next).toMatchObject({ name: 'Fresh token accepted', isFirstOfRequirement: false, verify: [] })
  expect(next.purpose).toBeUndefined()
  expect(countsOf(parseDraft(text))).toEqual({ decided: 1, undecided: 2 })
})

test('reject deletes the scenario and keeps the marks it showed: the next card is the first again', () => {
  const text = apply(DRAFT, 'Expired token rejected', { kind: 'reject' })
  expect(text).not.toContain('Expired token rejected')
  expect(text).not.toContain('more than an hour ago')
  const next = cardOf('auth/tokens', parseDraft(text))!
  expect(next).toMatchObject({ name: 'Fresh token accepted', isFirstOfRequirement: true, purpose: 'Issue, refresh and revoke API tokens.' })
  expect(next.verify).toEqual(['are revoked tokens kept?'])
  expect(text).toContain('**Scenario: Fresh token accepted**')
})

test('rejecting a requirement’s last scenario drops the requirement', () => {
  let text = apply(DRAFT, 'Expired token rejected', { kind: 'accept' })
  text = apply(text, 'Fresh token accepted', { kind: 'accept' })
  expect(cardOf('auth/tokens', parseDraft(text))).toMatchObject({ requirement: 'Revoke', isFirstOfRequirement: true, verify: ['at once, or after the cache expires?'] })
  text = apply(text, 'Revoked token refused', { kind: 'reject' })
  expect(text).not.toContain('Requirement: Revoke')
  expect(text).not.toContain('A revoked token SHALL be refused.')
  expect(text.trimEnd().endsWith('- **THEN** the request goes through')).toBe(true)
  expect(parseDraft(text).requirements.map(r => r.name)).toEqual(['Token expiry'])
  expect(cardOf('auth/tokens', parseDraft(text))).toBeUndefined()
})

test('amend writes the new scenario, statement and Purpose, marked amended', () => {
  const text = apply(DRAFT, 'Expired token rejected', {
    kind: 'amend',
    scenario: '- **Scenario: Expired token rejected**\n  - **WHEN** a token over an hour old is presented\n  - **THEN** the request is refused with 401',
    statement: 'Tokens SHALL expire 60 minutes after they are issued.',
    purpose: 'Issue and revoke API tokens.',
  })
  expect(text).toContain('## Purpose\nIssue and revoke API tokens.\n\n## Requirements')
  expect(text).toContain('### Requirement: Token expiry\nTokens SHALL expire 60 minutes after they are issued.\n\n- **Scenario: Expired token rejected** <!-- amended -->\n  - **WHEN** a token over an hour old is presented\n')
  expect(text).not.toContain('GIVEN** a token issued more than')
  expect(cardOf('auth/tokens', parseDraft(text))!.name).toBe('Fresh token accepted')
})

test('a decision on a card that is no longer next, or an amend that breaks the scenario line, saves nothing', () => {
  expect(decide(DRAFT, 'auth/tokens', 'Fresh token accepted', { kind: 'accept' })).toMatchObject({ error: expect.stringContaining('no longer the next card') })
  expect(decide(DRAFT, 'auth/tokens', 'Expired token rejected', { kind: 'amend', scenario: 'refused with 403' })).toMatchObject({ error: expect.stringContaining('Scenario: <name>') })
  expect(decide(DRAFT, 'auth/tokens', 'Expired token rejected', { kind: 'amend', scenario: '- **Scenario: Fresh token accepted**\n  - **THEN** x' })).toMatchObject({
    error: expect.stringContaining('already has a scenario named'),
  })
  // Unindented steps, or a second scenario, would break the draft's structure.
  expect(decide(DRAFT, 'auth/tokens', 'Expired token rejected', { kind: 'amend', scenario: '- **Scenario: Expired token rejected**\n- **THEN** x' })).toMatchObject({
    error: expect.stringContaining('Indent every line'),
  })
  expect(decide(DRAFT, 'auth/tokens', 'Expired token rejected', { kind: 'amend', scenario: '- **Scenario: A**\n  - **THEN** x\n- **Scenario: B**' })).toMatchObject({
    error: expect.stringContaining('Indent every line'),
  })
})

test('a statement written where there was none keeps a blank line before the scenario', () => {
  const bare = DRAFT.replace('Tokens SHALL expire one hour after they are issued.\n\n', '')
  const text = apply(bare, 'Expired token rejected', { kind: 'amend', scenario: '- **Scenario: Expired token rejected**\n  - **THEN** 401', statement: 'Tokens SHALL expire.' })
  expect(text).toContain('### Requirement: Token expiry\nTokens SHALL expire.\n\n- **Scenario: Expired token rejected** <!-- amended -->')
})

test('each decision counts on the capability in the domain progress file, in its own shape', () => {
  const file = JSON.stringify({ domain: 'auth', passes: { '2': 'done', '3': 'in-progress' }, capabilities: { 'auth/tokens': { purpose: 'x', anchors: [] }, 'auth/session': {} } }, null, 2) + '\n'
  const once = counted(file, 'auth/tokens', 'reject')
  expect(JSON.parse(once).capabilities['auth/tokens']).toEqual({ purpose: 'x', anchors: [], review: { accepted: 0, amended: 0, rejected: 1 } })
  expect(reviewOf(counted(once, 'auth/tokens', 'amend'), 'auth/tokens')).toEqual({ accepted: 0, amended: 1, rejected: 1 })
  expect(once.endsWith('}\n')).toBe(true)
  // A capability the file doesn't list isn't made up.
  expect(() => counted(file, 'auth/billing', 'accept')).toThrow("isn't one of the domain's capabilities")
  expect(orderOf(file, ['auth/session', 'auth/z', 'auth/tokens', 'auth/a'])).toEqual(['auth/tokens', 'auth/session', 'auth/a', 'auth/z'])
  expect(orderOf(undefined, ['b', 'a'])).toEqual(['a', 'b'])
})

test('the message to Claude once a capability is decided', () => {
  const r = { accepted: 2, amended: 1, rejected: 1 }
  expect(decidedPrompt('auth', 'auth/tokens', r, 4)).toContain('every scenario of auth/tokens is decided (2 accepted, 1 amended, 1 rejected)')
  expect(decidedPrompt('auth', 'auth/tokens', r, 4)).toContain("auth's next cards")
  expect(decidedPrompt('auth', 'auth/tokens', r, 0)).toContain('finish pass 3 for auth')
})

test('backfill.py is found in the installed blueprint plugin, from this plugin’s own marketplace first', () => {
  const list = JSON.stringify({
    plugins: {
      'blueprint@other': [{ installPath: '/p/cache/other/blueprint/1' }],
      'blueprint@mine': [{ installPath: '/p/cache/mine/blueprint/2' }],
      'blueprint-ui@mine': [{ installPath: '/p/cache/mine/blueprint-ui/0.5.0' }],
    },
  })
  expect(installedScripts(list, '/p/cache/mine/blueprint-ui/0.5.0')).toEqual([
    '/p/cache/mine/blueprint/2/skills/blueprint/scripts/backfill.py',
    '/p/cache/other/blueprint/1/skills/blueprint/scripts/backfill.py',
  ])
  expect(installedScripts('not json', '/x')).toEqual([])
})

test('the board line and the next steps backfill.py names', () => {
  expect(backfillLineOf({ status: 'none' })).toBeUndefined()
  expect(backfillLineOf({ status: 'error', message: 'boom' })).toEqual({ line: 'Backfill in progress', error: 'boom' })
  expect(backfillStep('/blueprint-backfill domain auth')).toEqual({ command: 'blueprint-backfill', args: 'domain auth', label: '▶ run' })
  expect(backfillStep('/blueprint-backfill')).toMatchObject({ args: '' })
  expect(backfillStep('/blueprint-sync')).toBeUndefined()
})
