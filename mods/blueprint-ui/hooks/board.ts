import type { BlueprintUiCode, BlueprintUiDriftRow, BlueprintUiSpecs } from '../types'
import type { Map, SpecEntry } from './pages'

/** What a row's ▶ button runs: the command without its slash, and its arguments. */
export type Step = { command: 'blueprint-drift' | 'blueprint-sync' | 'blueprint'; args: string; label: string }

/** Which side moved, for the glyph's color: code is a warning, spec is a danger. */
export type Side = 'code' | 'spec' | 'both' | 'none'

/** A capability under Needs attention. */
export type CapRow = {
  name: string
  /** The spec's page id, when it has one, so the name opens it. */
  page?: string
  side: Side
  reason: string
  /** Drift chance and confidence, `0.5 · medium`, when its code or imported code moved. */
  score?: string
  step?: Step
  /** Comments and suggestions pending on its spec page. */
  pending: number
}

/**
 * A capability with nothing to do; `unknown` says why its spec side couldn't be read, and `maybe`
 * marks one possibly affected by code it imports, with its score (`0.13 · medium`).
 */
export type QuietRow = { name: string; page?: string; unknown?: string; maybe?: string; pending: number }

export type ChangeRow = {
  name: string
  status: string
  review?: string
  brief?: string
  pending: number
  step?: Step
}

export type Board = {
  /** Set when the code side couldn't be checked: why, shown in its place. */
  codeError?: string
  isCodeChecked: boolean
  attention: CapRow[]
  changes: ChangeRow[]
  done: ChangeRow[]
  quiet: QuietRow[]
  uncovered: number
  summary: string
}

const OPEN = ['building', 'approved', 'draft'] as const
const FINISHED = new Set(['applied', 'abandoned'])

/** Bare `/blueprint-sync`: every capability whose code or imported code moved, as the skill defaults to. */
export const syncAll = (n: number): Step => ({ command: 'blueprint-sync', args: '', label: `▶ sync all (${n})` })
const sync = (cap: string): Step => ({ command: 'blueprint-sync', args: cap, label: '▶ sync' })
const drift = (cap: string, both: boolean): Step => ({ command: 'blueprint-drift', args: cap, label: both ? '▶ drift → sync' : '▶ drift' })
const apply = (change: string): Step => ({ command: 'blueprint', args: `apply ${change}`, label: '▶ apply' })

const files = (n: number) => `${n} file${n === 1 ? '' : 's'}`

/** A drift chance as drift.py prints it (`0.5`, `0.1306`, `1`), then the confidence. */
export function scoreOf(r: BlueprintUiDriftRow | undefined): string | undefined {
  if (typeof r?.chance !== 'number') return undefined
  const chance = String(Math.round(r.chance * 1e4) / 1e4)
  return r.confidence ? `${chance} · ${r.confidence}` : chance
}

/** The spec side of one capability: moved or not, or unknown with why; not checked is `undefined`. */
function specSide(s: SpecEntry, specs: BlueprintUiSpecs): { moved: boolean } | { unknown: string } | undefined {
  const got = specs.markers[s.name]
  if (!got) return undefined
  if ('error' in got) return { unknown: got.error }
  if (!s.specVersion) return { unknown: 'blueprint.json records no marker for it' }
  return { moved: got.marker !== s.specVersion }
}

/**
 * The status board: capabilities that need a step first, then open changes, then
 * everything quiet. Follows status.md: spec moved → drift (first, if the code or imported code
 * moved too), code or imported code moved, or no spec → sync, no anchors → a note and no button.
 * Possibly affected stays quiet, marked with its score, and gets no button.
 */
export function boardOf(map: Map, code: BlueprintUiCode, specs: BlueprintUiSpecs, pendingOn: (page: string) => number): Board {
  const report = code.status === 'ready' ? new globalThis.Map(code.report.map(r => [r.capability, r])) : undefined
  const attention: CapRow[] = []
  const quiet: QuietRow[] = []

  for (const s of map.specs) {
    const page = s.ref ? `spec:${s.name}` : undefined
    const r = report?.get(s.name)
    const spec = s.ref ? specSide(s, specs) : undefined
    const specMoved = !!spec && 'moved' in spec && spec.moved
    const unknown = spec && 'unknown' in spec ? spec.unknown : undefined
    const pending = page ? pendingOn(page) : 0
    const row = (side: Side, reason: string, step?: Step, score?: string): CapRow => ({
      name: s.name,
      side,
      ...(score ? { score } : {}),
      // A spec that couldn't be read says so here too: its spec side may have moved as well.
      reason: unknown ? `${reason} · spec unknown: ${unknown}` : reason,
      pending,
      ...(page ? { page } : {}),
      ...(step ? { step } : {}),
    })

    if (r?.status === 'no-anchors') {
      attention.push(row('none', 'no anchors: map its code in blueprint.json'))
    } else if (!s.ref || r?.status === 'no-spec') {
      attention.push(row('none', 'no spec yet', sync(s.name)))
    } else if (r?.status === 'code-moved' && specMoved) {
      attention.push(row('both', 'code and spec moved', drift(s.name, true), scoreOf(r)))
    } else if (r?.status === 'deps-moved' && specMoved) {
      attention.push(row('both', 'imports and spec moved', drift(s.name, true), scoreOf(r)))
    } else if (specMoved) {
      attention.push(row('spec', 'spec moved', drift(s.name, false)))
    } else if (r?.status === 'code-moved') {
      attention.push(row('code', `code moved (${files(r.changed?.length ?? 0)})`, sync(s.name), scoreOf(r)))
    } else if (r?.status === 'deps-moved') {
      attention.push(row('code', 'imports moved', sync(s.name), scoreOf(r)))
    } else {
      // Possibly affected stays here, marked, with no step: below the threshold it isn't drift.
      const maybe = r?.status === 'possibly-affected' ? (scoreOf(r) ?? 'possibly affected') : undefined
      quiet.push({ name: s.name, pending, ...(page ? { page } : {}), ...(unknown ? { unknown } : {}), ...(maybe ? { maybe } : {}) })
    }
  }

  const rows: ChangeRow[] = map.changes.map(c => {
    const pending = (c.review ? pendingOn(`change:${c.name}:review`) : 0) + (c.brief ? pendingOn(`change:${c.name}:brief`) : 0)
    const row: ChangeRow = { name: c.name, status: c.status, pending }
    if (c.review) row.review = `change:${c.name}:review`
    if (c.brief) row.brief = `change:${c.name}:brief`
    if (c.status === 'approved' || c.status === 'building') row.step = apply(c.name)
    return row
  })
  const rank = (s: string) => {
    const i = (OPEN as readonly string[]).indexOf(s)
    return i < 0 ? OPEN.length : i
  }
  const changes = rows.filter(r => !FINISHED.has(r.status)).sort((a, b) => rank(a.status) - rank(b.status))
  const done = rows.filter(r => FINISHED.has(r.status))
  const pending = [...rows, ...attention, ...quiet].reduce((n, r) => n + r.pending, 0)

  const board: Board = {
    isCodeChecked: code.status === 'ready',
    attention,
    changes,
    done,
    quiet,
    uncovered: code.status === 'ready' ? code.uncovered : 0,
    summary: summaryOf(attention.length, quiet.filter(q => !q.unknown).length, quiet.filter(q => q.unknown).length, changes, pending, code.status === 'ready'),
  }
  if (code.status === 'error') board.codeError = code.message
  return board
}

/** `2 need attention · 7 in sync · 1 spec unknown · 1 building · 3 pending`, leaving out what is zero. */
function summaryOf(attention: number, quiet: number, unknown: number, open: ChangeRow[], pending: number, isCodeChecked: boolean): string {
  const parts: string[] = []
  if (attention) parts.push(`${attention} need${attention === 1 ? 's' : ''} attention`)
  if (quiet) parts.push(isCodeChecked ? `${quiet} in sync` : `${quiet} not checked`)
  if (unknown) parts.push(`${unknown} spec unknown`)
  const statuses = [...OPEN, ...new Set(open.map(c => c.status).filter(s => !(OPEN as readonly string[]).includes(s)))]
  for (const s of statuses) {
    const n = open.filter(c => c.status === s).length
    if (n) parts.push(`${n} ${s}`)
  }
  if (pending) parts.push(`${pending} pending`)
  return parts.join(' · ') || 'Nothing mapped yet.'
}

/** "just now", "2 min ago", "3 h ago": how long before `now` `iso` was. */
export function ago(iso: string, now: number): string {
  const s = Math.max(0, Math.round((now - Date.parse(iso)) / 1000))
  if (s < 45) return 'just now'
  const m = Math.max(1, Math.round(s / 60))
  if (m < 60) return `${m} min ago`
  const h = Math.round(m / 60)
  return h < 24 ? `${h} h ago` : `${Math.round(h / 24)} d ago`
}

/** The ▶ step's command as this session names it: `name`, or `<plugin>:name` when installed as a plugin. */
export function commandNamed(all: { name: string }[], name: string): string | undefined {
  return (all.find(c => c.name === name) ?? all.find(c => c.name.endsWith(`:${name}`)))?.name
}

/** How many columns the In sync grid takes: as many cells of the longest name as fit across, 1 to 4. */
export function columnsFor(quiet: QuietRow[], bodyColumns: number): number {
  // A cell: the mark, a space, the name, " · n pending" when there is one, and a gap.
  const widest = Math.max(1, ...quiet.map(q => 2 + q.name.length + (q.pending ? ` · ${q.pending} pending`.length : 0) + 3))
  return Math.min(4, Math.max(1, Math.floor(bodyColumns / widest)))
}

/** `items` in rows of `cols`, read across, so the grid's columns line up. */
export function rowsOf<T>(items: T[], cols: number): T[][] {
  const out: T[][] = []
  for (let i = 0; i < items.length; i += cols) out.push(items.slice(i, i + cols))
  return out
}
