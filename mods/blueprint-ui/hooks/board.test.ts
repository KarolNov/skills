import { expect, test } from 'claude-code/testing'

import type { BlueprintUiCode, BlueprintUiDriftRow, BlueprintUiSpecs } from '../types'
import { ago, boardOf, columnsFor, commandNamed, rowsOf } from './board'
import { pagesOf } from './pages'

const MAP = pagesOf(
  JSON.stringify({
    docs: { backend: 'notion' },
    specs: {
      'a/code': { ref: 'https://notion.so/a', specVersion: 'aaaa' },
      'b/spec': { ref: 'https://notion.so/b', specVersion: 'bbbb' },
      'c/both': { ref: 'https://notion.so/c', specVersion: 'cccc' },
      'd/quiet': { ref: 'https://notion.so/d', specVersion: 'dddd' },
      'e/noref': { ref: null },
      'f/noanchors': { ref: 'https://notion.so/f', specVersion: 'ffff' },
    },
    changes: {
      shipped: { review: 'https://notion.so/r1', brief: 'https://notion.so/b1', status: 'applied' },
      wip: { review: 'https://notion.so/r2', brief: 'https://notion.so/b2', status: 'building' },
      idea: { review: 'https://notion.so/r3', status: 'draft' },
      ready: { review: 'https://notion.so/r4', brief: 'https://notion.so/b4', status: 'approved' },
      dropped: { review: 'https://notion.so/r5', status: 'abandoned' },
    },
  }),
)

const code = (report: BlueprintUiDriftRow[], uncovered = 0): BlueprintUiCode => ({ status: 'ready', report, uncovered, checkedAt: '2026-01-01T00:00:00Z' })
const NO_SPECS: BlueprintUiSpecs = { markers: {} }
const none = () => 0

const DRIFT: BlueprintUiDriftRow[] = [
  { capability: 'a/code', status: 'code-moved', changed: ['x', 'y', 'z'] },
  { capability: 'b/spec', status: 'in-sync' },
  { capability: 'c/both', status: 'code-moved', changed: ['w'] },
  { capability: 'd/quiet', status: 'in-sync' },
  { capability: 'e/noref', status: 'no-spec' },
  { capability: 'f/noanchors', status: 'no-anchors' },
]
const SPECS: BlueprintUiSpecs = {
  markers: { 'a/code': { marker: 'aaaa' }, 'b/spec': { marker: 'NEW1' }, 'c/both': { marker: 'NEW2' }, 'd/quiet': { marker: 'dddd' }, 'f/noanchors': { marker: 'ffff' } },
  checkedAt: '2026-01-01T00:00:00Z',
}

// @scenario blueprint/ui: Both sides moved
test('each capability gets the reason and next step status.md gives it', () => {
  const b = boardOf(MAP, code(DRIFT), SPECS, none)
  const by = Object.fromEntries(b.attention.map(r => [r.name, r]))
  expect(by['a/code']).toMatchObject({ side: 'code', reason: 'code moved (3 files)', step: { command: 'blueprint-sync', args: 'a/code', label: '▶ sync' } })
  expect(by['b/spec']).toMatchObject({ side: 'spec', reason: 'spec moved', step: { command: 'blueprint-drift', args: 'b/spec', label: '▶ drift' } })
  expect(by['c/both']).toMatchObject({ side: 'both', reason: 'code and spec moved', step: { command: 'blueprint-drift', label: '▶ drift → sync' } })
  expect(by['e/noref']).toMatchObject({ side: 'none', reason: 'no spec yet', step: { command: 'blueprint-sync' } })
  expect(by['e/noref']!.page).toBeUndefined()
  expect(by['f/noanchors']!.step).toBeUndefined()
  expect(b.quiet.map(q => q.name)).toEqual(['d/quiet'])
})

test('imports moved needs a sync with its score; possibly affected stays quiet, marked, with no step', () => {
  const report: BlueprintUiDriftRow[] = [
    { capability: 'a/code', status: 'deps-moved', chance: 0.5, confidence: 'medium', reasons: [] },
    { capability: 'b/spec', status: 'deps-moved', chance: 0.75, confidence: 'low', reasons: [] },
    { capability: 'c/both', status: 'code-moved', changed: ['w'], chance: 1, confidence: 'high', reasons: [] },
    { capability: 'd/quiet', status: 'possibly-affected', chance: 0.1306, confidence: 'medium', reasons: [] },
    { capability: 'e/noref', status: 'no-spec' },
    { capability: 'f/noanchors', status: 'no-anchors' },
  ]
  const b = boardOf(MAP, code(report), SPECS, none)
  const by = Object.fromEntries(b.attention.map(r => [r.name, r]))
  expect(by['a/code']).toMatchObject({ side: 'code', reason: 'imports moved', score: '0.5 · medium', step: { command: 'blueprint-sync', args: 'a/code', label: '▶ sync' } })
  // Imported code and spec both moved: drift first, as when the code itself moved.
  expect(by['b/spec']).toMatchObject({ side: 'both', reason: 'imports and spec moved', score: '0.75 · low', step: { command: 'blueprint-drift', label: '▶ drift → sync' } })
  expect(by['c/both']).toMatchObject({ reason: 'code and spec moved', score: '1 · high' })
  expect(by['d/quiet']).toBeUndefined()
  expect(b.quiet).toEqual([{ name: 'd/quiet', page: 'spec:d/quiet', maybe: '0.1306 · medium', pending: 0 }])
  // An older drift.py gives no chance: the row reads as before.
  expect(boardOf(MAP, code(DRIFT), SPECS, none).attention.find(r => r.name === 'a/code')!.score).toBeUndefined()
})

test('before Check specs only the code side counts, and an unread spec stays quiet with its reason', () => {
  const b = boardOf(MAP, code(DRIFT), NO_SPECS, none)
  expect(b.attention.find(r => r.name === 'b/spec')).toBeUndefined()
  expect(b.attention.find(r => r.name === 'c/both')).toMatchObject({ reason: 'code moved (1 file)' })
  const failed = boardOf(MAP, code(DRIFT), { markers: { 'd/quiet': { error: 'timeout' } } }, none)
  expect(failed.quiet.find(q => q.name === 'd/quiet')).toEqual({ name: 'd/quiet', page: 'spec:d/quiet', unknown: 'timeout', pending: 0 })
})

test('changes: open ones by status with ▶ apply when ready, finished ones fold under Done', () => {
  const pending = (p: string) => (p === 'change:wip:review' ? 2 : p === 'change:wip:brief' ? 1 : 0)
  const b = boardOf(MAP, code(DRIFT), SPECS, pending)
  expect(b.changes.map(c => [c.name, c.status, c.step?.args])).toEqual([
    ['wip', 'building', 'apply wip'],
    ['ready', 'approved', 'apply ready'],
    ['idea', 'draft', undefined],
  ])
  expect(b.changes[0]).toMatchObject({ pending: 3, review: 'change:wip:review', brief: 'change:wip:brief' })
  expect(b.changes[2]!.brief).toBeUndefined()
  expect(b.done.map(c => c.name)).toEqual(['shipped', 'dropped'])
})

test('the summary counts what needs attention, what is in sync, open changes and pending', () => {
  const b = boardOf(MAP, code(DRIFT, 2), SPECS, p => (p === 'change:idea:review' ? 3 : 0))
  expect(b.summary).toBe('5 need attention · 1 in sync · 1 building · 1 approved · 1 draft · 3 pending')
  expect(b.uncovered).toBe(2)
})

// @scenario blueprint/ui: Everything in sync
test('everything in sync: no attention, every capability quiet, the applied change under Done', () => {
  const map = pagesOf(
    JSON.stringify({
      specs: { one: { ref: 'https://notion.so/1', specVersion: 'x' }, two: { ref: 'https://notion.so/2', specVersion: 'y' } },
      changes: { only: { review: 'https://notion.so/r', status: 'applied' } },
    }),
  )
  const b = boardOf(map, code([{ capability: 'one', status: 'in-sync' }, { capability: 'two', status: 'in-sync' }]), NO_SPECS, none)
  expect(b.attention).toEqual([])
  expect(b.changes).toEqual([])
  expect(b.quiet.map(q => q.name)).toEqual(['one', 'two'])
  expect(b.done.map(c => c.name)).toEqual(['only'])
  expect(b.summary).toBe('2 in sync')
})

test('code side unavailable: the board says why and counts capabilities as not checked', () => {
  const b = boardOf(MAP, { status: 'error', message: 'drift.py is missing' }, NO_SPECS, none)
  expect(b.codeError).toBe('drift.py is missing')
  expect(b.isCodeChecked).toBe(false)
  expect(b.summary.startsWith('1 needs attention · 5 not checked')).toBe(true)
})

test('command names and times', () => {
  expect(commandNamed([{ name: 'blueprint:blueprint-sync' }, { name: 'blueprint:blueprint' }], 'blueprint')).toBe('blueprint:blueprint')
  expect(commandNamed([{ name: 'blueprint-drift' }], 'blueprint-drift')).toBe('blueprint-drift')
  expect(commandNamed([{ name: 'blueprint' }], 'blueprint-sync')).toBeUndefined()
  const now = Date.parse('2026-01-01T00:10:00Z')
  expect(ago('2026-01-01T00:09:50Z', now)).toBe('just now')
  expect(ago('2026-01-01T00:08:00Z', now)).toBe('2 min ago')
})

test('the In sync grid: columns that fit the widest name, rows read across', () => {
  const q = (name: string, pending = 0) => ({ name, pending })
  const names = ['blueprint/propose', 'blueprint/apply', 'distribution'].map(n => q(n))
  expect(columnsFor(names, 60)).toBe(2) // 22 wide each
  expect(columnsFor(names, 120)).toBe(4)
  expect(columnsFor(names, 20)).toBe(1)
  expect(columnsFor([q('a', 12)], 40)).toBe(2)
  expect(rowsOf([1, 2, 3, 4, 5], 2)).toEqual([[1, 2], [3, 4], [5]])
})
