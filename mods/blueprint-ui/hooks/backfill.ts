import { atom, update } from 'claude-code'
import type { EngineInterface } from 'claude-code'

import type { BlueprintUiBackfill, BlueprintUiBackfillReport } from '../types'
import { parentOf } from './pages'

/** The progress folder `/blueprint-backfill` keeps until it finishes. */
export const BACKFILL_DIR = '.blueprint/backfill'
export const PROGRESS = `${BACKFILL_DIR}/progress.json`
/** A capability's draft: `drafts/auth/tokens.md`, or `drafts/tokens.md` for a bare one. */
export const draftPath = (capability: string) => `${BACKFILL_DIR}/drafts/${capability}.md`
export const domainPath = (domain: string) => `${BACKFILL_DIR}/domains/${domain}.progress.json`

export const NO_BACKFILL: BlueprintUiBackfill = { status: 'none' }
const backfill = atom({ plugin: 'blueprint-ui', key: 'backfill' } as const, NO_BACKFILL, { shape: 'backfill-1' })

const SCRIPT = 'skills/blueprint/scripts/backfill.py'

/** Where backfill.py was found, by repo root. */
const scripts = new globalThis.Map<string, string>()

/** `path` inside the folder `dir`. */
export const inRoot = (dir: string, path: string) => `${dir.replace(/\/+$/, '')}/${path}`

/**
 * backfill.py lives in the blueprint plugin, not in `.blueprint/`: looked for in the repo itself
 * (the skills repo), in a folder above this plugin's (a checkout of it), then in the blueprint
 * plugin Claude Code installed, by `installed_plugins.json` above this plugin's install folder.
 */
export async function scriptFor($: EngineInterface, root: string): Promise<string | undefined> {
  const known = scripts.get(root)
  if (known) return known
  const exists = (p: string) => $.fs.exists(p).catch(() => false)
  const found = async (): Promise<string | undefined> => {
    if (await exists(inRoot(root, SCRIPT))) return inRoot(root, SCRIPT)
    for (let dir: string | undefined = $.plugin.root; dir; dir = parentOf(dir)) {
      if (await exists(inRoot(dir, SCRIPT))) return inRoot(dir, SCRIPT)
      const list = inRoot(dir, 'installed_plugins.json')
      if (!(await exists(list))) continue
      for (const path of installedScripts(await $.fs.read(list).catch(() => ''), $.plugin.root)) {
        if (await exists(path)) return path
      }
    }
    return undefined
  }
  const path = await found()
  if (path) scripts.set(root, path)
  return path
}

/** backfill.py in each installed blueprint plugin, the one from this plugin's own marketplace first. */
export function installedScripts(text: string, pluginRoot: string): string[] {
  let json: { plugins?: Record<string, { installPath?: string }[]> }
  try {
    json = JSON.parse(text)
  } catch {
    return []
  }
  const plugins = json.plugins ?? {}
  const mine = Object.entries(plugins).find(([k, v]) => k.startsWith('blueprint-ui@') && v.some(i => i.installPath === pluginRoot))
  const market = mine?.[0].slice('blueprint-ui@'.length)
  const keys = Object.keys(plugins)
    .filter(k => k.startsWith('blueprint@'))
    .sort((a, b) => Number(b === `blueprint@${market}`) - Number(a === `blueprint@${market}`))
  return keys.flatMap(k => (plugins[k] ?? []).flatMap(i => (i.installPath ? [inRoot(i.installPath, SCRIPT)] : [])))
}

/** `backfill.py status --json`, once `.blueprint/backfill/progress.json` exists; none otherwise. */
export async function backfillStatus($: EngineInterface, root: string): Promise<BlueprintUiBackfill> {
  if (!(await $.fs.exists(inRoot(root, PROGRESS)).catch(() => false))) return NO_BACKFILL
  const script = await scriptFor($, root)
  if (!script) return { status: 'error', message: 'backfill.py not found: install the blueprint plugin' }
  let run
  try {
    run = await $.process.run(['python3', script, 'status', '--json'], { timeoutMs: 30000, cwd: root })
  } catch (err) {
    return { status: 'error', message: `backfill.py couldn't run (${String(err)})` }
  }
  try {
    const report = JSON.parse(run.stdout) as BlueprintUiBackfillReport | { active: false }
    if (!report.active) return NO_BACKFILL
    if (!Array.isArray(report.domains)) throw new Error('no domains')
    return { status: 'ready', report, checkedAt: new Date().toISOString() }
  } catch {
    return { status: 'error', message: run.stderr.trim().slice(0, 200) || `backfill.py status failed (exit ${run.exitCode})` }
  }
}

/** Reads the backfill's status into the pane's state. */
export async function checkBackfill($: EngineInterface, root: string): Promise<void> {
  const next = await backfillStatus($, root)
  await update($, backfill, () => next)
}

// ---- a draft and its cards ---------------------------------------------------------------

type Range = { start: number; end: number }
export type Scenario = Range & { name: string; decision?: 'accepted' | 'amended' }
export type Requirement = Range & { name: string; statement: Range; scenarios: Scenario[] }
export type Draft = { lines: string[]; purpose?: Range; requirements: Requirement[] }

const SCENARIO = /^- \*\*Scenario:\s*(.+?)\*\*(.*)$/
const REQUIREMENT = /^###\s+Requirement:\s*(.+?)\s*$/
const VERIFY = /<!--\s*verify:\s*([\s\S]*?)\s*-->/g
const DECISION = /\s*<!--\s*(accepted|amended)\s*-->/g

/** `[start, end)` with blank lines trimmed off both ends. */
function trimmed(lines: string[], start: number, end: number): Range {
  while (start < end && !lines[start]!.trim()) start++
  while (end > start && !lines[end - 1]!.trim()) end--
  return { start, end }
}

/** A draft in the capability spec's shape: its Purpose, and each requirement with its statement and scenarios. */
export function parseDraft(text: string): Draft {
  const lines = text.split('\n')
  const isHeading = (l: string, max: number) => new RegExp(`^#{1,${max}}\\s`).test(l)
  const draft: Draft = { lines, requirements: [] }
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]!
    if (/^##\s+Purpose\s*$/.test(line)) {
      let end = i + 1
      while (end < lines.length && !isHeading(lines[end]!, 6)) end++
      draft.purpose = trimmed(lines, i + 1, end)
      continue
    }
    const req = REQUIREMENT.exec(line)
    if (!req) continue
    let end = i + 1
    while (end < lines.length && !isHeading(lines[end]!, 3)) end++
    const scenarios: Scenario[] = []
    for (let j = i + 1; j < end; j++) {
      const m = SCENARIO.exec(lines[j]!)
      if (!m) continue
      let k = j + 1
      // A scenario runs over its indented lines; a blank line inside it doesn't end it.
      while (k < end && (!lines[k]!.trim() || /^\s/.test(lines[k]!))) k++
      const range = trimmed(lines, j, k)
      const decision = /<!--\s*accepted\s*-->/.test(m[2]!) ? 'accepted' : /<!--\s*amended\s*-->/.test(m[2]!) ? 'amended' : undefined
      scenarios.push({ ...range, name: m[1]!.trim(), ...(decision ? { decision } : {}) })
      j = k - 1
    }
    const firstScenario = scenarios[0]?.start ?? end
    draft.requirements.push({ start: i, end, name: req[1]!, statement: trimmed(lines, i + 1, firstScenario), scenarios })
  }
  return draft
}

const textOf = (d: Draft, r: Range | undefined) => (r ? d.lines.slice(r.start, r.end).join('\n') : '')
const verifiesIn = (text: string) => [...text.matchAll(VERIFY)].map(m => m[1]!.trim()).filter(Boolean)
/** Text as the card shows it: no verify marks (they are the card's questions) and no decision marks. */
export const shown = (text: string) =>
  text
    .replace(VERIFY, '')
    .replace(DECISION, '')
    .split('\n')
    .map(l => l.trimEnd())
    .filter((l, i, all) => l.trim() || (i > 0 && all[i - 1]!.trim()))
    .join('\n')
    .trim()

/** One scenario put to the user, with its requirement's statement and, on the capability's first card, its Purpose. */
export type Card = {
  capability: string
  requirement: string
  name: string
  /** The statement, editable on the requirement's first card. */
  statement: string
  isFirstOfRequirement: boolean
  /** The Purpose, on the capability's first card only. */
  purpose?: string
  /** The scenario's lines, as the draft holds them without marks. */
  scenario: string
  /** The verify marks in what the card shows: the questions to settle. */
  verify: string[]
}

/** The first undecided scenario in document order, as a card; none when every scenario is decided. */
export function cardOf(capability: string, d: Draft): Card | undefined {
  let isFirstOfCapability = true
  for (const r of d.requirements) {
    for (const [i, s] of r.scenarios.entries()) {
      if (!s.decision) {
        const isFirstOfRequirement = i === 0
        const statement = textOf(d, r.statement)
        const purpose = isFirstOfCapability && d.purpose ? textOf(d, d.purpose) : undefined
        const scenario = textOf(d, s)
        return {
          capability,
          requirement: r.name,
          name: s.name,
          statement: shown(statement),
          isFirstOfRequirement,
          ...(purpose !== undefined ? { purpose: shown(purpose) } : {}),
          scenario: shown(scenario),
          verify: [...(purpose ? verifiesIn(purpose) : []), ...verifiesIn(statement), ...verifiesIn(scenario)],
        }
      }
      isFirstOfCapability = false
    }
  }
  return undefined
}

/** Scenarios decided in the draft and still undecided. */
export function countsOf(d: Draft): { decided: number; undecided: number } {
  const all = d.requirements.flatMap(r => r.scenarios)
  const decided = all.filter(s => s.decision).length
  return { decided, undecided: all.length - decided }
}

export type Decision = { kind: 'accept' } | { kind: 'reject' } | { kind: 'amend'; scenario: string; statement?: string; purpose?: string }
export const reviewKey = { accept: 'accepted', amend: 'amended', reject: 'rejected' } as const

/** `lines` without verify marks; a line left empty by it goes. */
function unverified(lines: string[]): string[] {
  return lines.flatMap(l => {
    const out = l.replace(VERIFY, '').trimEnd()
    return out.trim() || !l.trim() ? [out] : []
  })
}

/** Text typed into a field, as lines for the draft: trailing spaces and marks dropped. */
const typed = (text: string) => text.replace(VERIFY, '').replace(DECISION, '').replace(/\s+$/, '').split('\n').map(l => l.trimEnd())

/**
 * The draft with one decision applied, as pass 3 of /blueprint-backfill writes it: accept and amend
 * mark the scenario and drop the verify marks the card showed; reject deletes the scenario, and its
 * requirement when it was the last one. A scenario not found or already decided is an error.
 */
export function decide(text: string, capability: string, name: string, decision: Decision): { text: string } | { error: string } {
  const d = parseDraft(text)
  const card = cardOf(capability, d)
  if (!card || card.name !== name) return { error: `${name} is no longer the next card of ${capability}: the draft changed.` }
  const req = d.requirements.find(r => r.name === card.requirement)!
  const sc = req.scenarios.find(s => s.name === name)!
  const lines = [...d.lines]
  // Edits go from the bottom of the file up, so the ranges above stay where they were.
  const splice = (r: Range, next: string[]) => lines.splice(r.start, r.end - r.start, ...next)
  const slice = (r: Range) => lines.slice(r.start, r.end)

  if (decision.kind === 'reject') {
    if (req.scenarios.length === 1) {
      splice(req, [])
    } else {
      splice(sc, [])
      // Don't leave two blank lines where the scenario was.
      if (sc.start > 0 && !lines[sc.start - 1]?.trim() && !lines[sc.start]?.trim() && sc.start < lines.length) lines.splice(sc.start, 1)
    }
    return { text: lines.join('\n') }
  }

  let scenario = unverified(slice(sc))
  if (decision.kind === 'amend') {
    scenario = typed(decision.scenario)
    const m = SCENARIO.exec(scenario[0] ?? '')
    if (!m) return { error: 'Keep the first line as `- **Scenario: <name>**`.' }
    const renamed = m[1]!.trim()
    const taken = d.requirements.some(r => r.scenarios.some(s => s !== sc && s.name.toLowerCase() === renamed.toLowerCase()))
    if (taken) return { error: `${capability} already has a scenario named "${renamed}".` }
  }
  scenario[0] = `${scenario[0]!.trimEnd()} <!-- ${decision.kind === 'amend' ? 'amended' : 'accepted'} -->`
  splice(sc, scenario)
  const statement = decision.kind === 'amend' && card.isFirstOfRequirement && decision.statement !== undefined ? typed(decision.statement) : unverified(slice(req.statement))
  if (req.statement.end > req.statement.start || statement.some(l => l.trim())) splice(req.statement, statement)
  if (card.purpose !== undefined && d.purpose) {
    splice(d.purpose, decision.kind === 'amend' && decision.purpose !== undefined ? typed(decision.purpose) : unverified(slice(d.purpose)))
  }
  return { text: lines.join('\n') }
}

/** The domain progress file with one more decision counted on the capability's `review`. */
export function counted(text: string, capability: string, kind: Decision['kind']): string {
  const json = JSON.parse(text) as { capabilities?: Record<string, { review?: Record<string, number> }> }
  const caps = (json.capabilities ??= {})
  const cap = (caps[capability] ??= {})
  const review = (cap.review = { accepted: 0, amended: 0, rejected: 0, ...cap.review })
  review[reviewKey[kind]] = (review[reviewKey[kind]] ?? 0) + 1
  return JSON.stringify(json, null, 2) + '\n'
}

/** A domain's capabilities in the order its progress file lists them; drafts it doesn't list follow, by name. */
export function orderOf(progressText: string | undefined, drafts: string[]): string[] {
  let listed: string[] = []
  try {
    listed = Object.keys((JSON.parse(progressText ?? '{}') as { capabilities?: object }).capabilities ?? {})
  } catch {
    // Unreadable: the drafts by name.
  }
  return [...listed.filter(c => drafts.includes(c)), ...drafts.filter(c => !listed.includes(c)).sort()]
}

/** What a capability's review came to, from its progress file. */
export function reviewOf(progressText: string | undefined, capability: string): { accepted: number; amended: number; rejected: number } {
  try {
    const r = (JSON.parse(progressText ?? '{}') as { capabilities?: Record<string, { review?: Record<string, number> }> }).capabilities?.[capability]?.review
    return { accepted: r?.accepted ?? 0, amended: r?.amended ?? 0, rejected: r?.rejected ?? 0 }
  } catch {
    return { accepted: 0, amended: 0, rejected: 0 }
  }
}

/** The message Claude gets once a capability's last card is decided in the pane. */
export function decidedPrompt(domain: string, capability: string, review: { accepted: number; amended: number; rejected: number }, leftInDomain: number): string {
  const counts = `${review.accepted} accepted, ${review.amended} amended, ${review.rejected} rejected`
  const tail = leftInDomain
    ? `The pane keeps showing ${domain}'s next cards: after the spec, end your turn.`
    : `That was ${domain}'s last card: finish pass 3 for ${domain}.`
  return (
    `Backfill review in the blueprint pane: every scenario of ${capability} is decided (${counts}), saved in ${draftPath(capability)} and ${domainPath(domain)}, not yet committed. ` +
    `Write its spec now (/blueprint-backfill pass 3, step 3), committing the decisions with it. ${tail}`
  )
}

/** The pane tool pass 3 calls to put a domain's cards in the Backfill view. */
export const BACKFILL_TOOL = 'backfill'
export const BACKFILL_SPEC = {
  name: BACKFILL_TOOL,
  description:
    "Open the blueprint pane's Backfill view on a domain's scenario cards, for /blueprint-backfill pass 3's review. " +
    'The user decides each card there (Accept, Amend or Reject); the pane saves each decision to the draft and the domain progress file before the next card, ' +
    "and sends you a message when a capability's last card is decided, so you write its spec. After calling it, end your turn.",
  inputSchema: {
    type: 'object',
    properties: { domain: { type: 'string', description: "The domain whose drafts to review, as named in backfill.py status." } },
    required: ['domain'],
  },
} as const
