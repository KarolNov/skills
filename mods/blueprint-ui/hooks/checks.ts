import { atom, read, update } from 'claude-code'
import type { EngineInterface } from 'claude-code'

import type { BlueprintUiCode, BlueprintUiDriftRow, BlueprintUiSpecs } from '../types'
import { commandNamed } from './board'
import type { Step } from './board'
import { candidates, fetchMarker } from './notion'
import type { Map, SpecEntry } from './pages'

export const DRIFT = '.blueprint/drift.py'

export const NO_CODE: BlueprintUiCode = { status: 'none' }
const code = atom({ plugin: 'blueprint-ui', key: 'code' } as const, NO_CODE, { shape: 'code-1' })
export const NO_SPECS: BlueprintUiSpecs = { markers: {} }
const specs = atom({ plugin: 'blueprint-ui', key: 'specs' } as const, NO_SPECS, { shape: 'specs-1' })
export const NO_STEPS: string[] = []
/** ▶ steps waiting for the session to go idle, by `stepKey`, so their buttons show them as queued. */
const queued = atom({ plugin: 'blueprint-ui', key: 'queued' } as const, NO_STEPS, { shape: 'queued-1' })

/** How many spec pages a check reads at once. */
const SPEC_READS = 3

/** Runs going, by repo root, so a call for another repo starts its own instead of joining this one's. */
const codeRuns = new globalThis.Map<string, Promise<void>>()
const specRuns = new globalThis.Map<string, Promise<void>>()

/** `start()`'s run for this root, or the one already going; it forgets itself when done. */
function joined(runs: typeof codeRuns, root: string, start: () => Promise<void>): Promise<void> {
  const going = runs.get(root)
  if (going) return going
  const run = start()
    .catch(() => undefined) // The pane or session went away mid-check: nothing to show it on.
    .finally(() => runs.delete(root))
  runs.set(root, run)
  return run
}

/** Runs `drift.py check --json` and `unanchored --since <oldest sync>`; a run already going is joined, not repeated. */
export function checkCode($: EngineInterface, map: Map): Promise<void> {
  return joined(codeRuns, map.root, () => runCode($, map))
}

/** After blueprint.json may have changed: checks the code side again, once the board has a code status. */
export async function recheckCode($: EngineInterface, map: Map): Promise<void> {
  if ((await read($, code)).status !== 'none') await checkCode($, map)
}

async function runCode($: EngineInterface, map: Map): Promise<void> {
  await update($, code, (c): BlueprintUiCode => (c.status === 'ready' ? c : { status: 'checking' }))
  const next = await codeStatus($, map)
  await update($, code, () => next)
}

/** Python's own complaint when the script itself isn't there, not a message drift.py prints. */
const MISSING = /can't open file .*drift\.py/i

async function codeStatus($: EngineInterface, map: Map): Promise<BlueprintUiCode> {
  let run
  try {
    run = await $.process.run(['python3', DRIFT, 'check', '--json'], { timeoutMs: 30000, cwd: map.root })
  } catch (err) {
    return { status: 'error', message: `${DRIFT} couldn't run (${String(err)}).` }
  }
  let report: BlueprintUiDriftRow[]
  try {
    // check exits 1 when some code moved: the report is the answer either way.
    report = JSON.parse(run.stdout) as BlueprintUiDriftRow[]
    if (!Array.isArray(report)) throw new Error('not a list')
  } catch {
    if (MISSING.test(run.stderr)) return { status: 'error', message: `${DRIFT} is missing.` }
    return { status: 'error', message: `${DRIFT} check failed: ${run.stderr.trim().slice(0, 200) || `exit ${run.exitCode}`}` }
  }
  return { status: 'ready', report, uncovered: await uncovered($, map), checkedAt: new Date().toISOString() }
}

/** Changed files since the oldest sync that no capability covers; 0 when there is no sync to count from. */
async function uncovered($: EngineInterface, map: Map): Promise<number> {
  const shas = [...new Set(map.specs.flatMap(s => (s.syncedCommit ? [s.syncedCommit] : [])))]
  if (!shas.length) return 0
  try {
    // Newest first, by commit date: the last one is where "since the last sync" starts.
    // A sync commit this clone lacks (squash-merged, gc'd) is skipped rather than failing the whole count.
    const log = await $.process.run(['git', 'log', '--ignore-missing', '--no-walk=sorted', '--format=%H', ...shas], { timeoutMs: 15000, cwd: map.root })
    const oldest = log.stdout.trim().split('\n').filter(Boolean).pop()
    if (log.exitCode !== 0 || !oldest) return 0
    const run = await $.process.run(['python3', DRIFT, 'unanchored', '--since', oldest], { timeoutMs: 30000, cwd: map.root })
    return run.exitCode === 0 ? run.stdout.split('\n').filter(l => l.trim()).length : 0
  } catch {
    return 0
  }
}

/** Reads every spec page's marker, a few at a time, showing progress; pressing again while it runs does nothing. */
export function checkSpecs($: EngineInterface, map: Map, configured: string): Promise<void> {
  return joined(specRuns, map.root, () => runSpecs($, map, configured))
}

export const isCheckingSpecs = (root: string) => specRuns.has(root)

async function runSpecs($: EngineInterface, map: Map, configured: string): Promise<void> {
  const todo = map.specs.filter(s => !!s.ref)
  const total = todo.length
  let done = 0
  const queue = [...todo]
  try {
    await update($, specs, s => ({ ...s, progress: { done, total } }))
    const names = await candidates($, configured)
    const worker = async () => {
      for (let s = queue.shift(); s; s = queue.shift()) {
        const got = await markerOf($, s, names, map.root)
        done += 1
        const name = s.name
        await update($, specs, cur => ({ ...cur, markers: { ...cur.markers, [name]: got }, progress: { done, total } }))
      }
    }
    await Promise.all(Array.from({ length: Math.min(SPEC_READS, total) }, worker))
  } finally {
    await update($, specs, ({ progress: _, ...cur }) => ({ ...cur, checkedAt: new Date().toISOString() }))
  }
}

async function markerOf($: EngineInterface, s: SpecEntry, names: string[], root: string): Promise<{ marker: string } | { error: string }> {
  try {
    return await fetchMarker($, s.ref!, names, root)
  } catch (err) {
    return { error: String(err).slice(0, 200) }
  }
}

/** After a followed write to a spec: re-reads that one marker, once the spec side has been checked this session. */
export async function recheckSpec($: EngineInterface, s: SpecEntry, root: string, configured: string): Promise<void> {
  if (!s.ref || !(await read($, specs)).checkedAt) return
  const got = await markerOf($, s, await candidates($, configured), root)
  await update($, specs, cur => ({ ...cur, markers: { ...cur.markers, [s.name]: got } }))
}

/** Names a step in the queued list: its command and arguments. */
export const stepKey = (step: Pick<Step, 'command' | 'args'>) => `${step.command} ${step.args}`.trim()

/**
 * Runs a ▶ step's command as if typed; a command the session lacks gets a toast and nothing runs.
 * The engine holds the run until the session is idle: until then the step is listed as queued,
 * and pressing it again queues nothing more.
 */
export async function runStep($: EngineInterface, step: Step): Promise<void> {
  const command = commandNamed(await $.command.list(), step.command)
  if (!command) {
    await $.ui.toast(`No /${step.command} command in this session: install the blueprint plugin to run it.`)
    return
  }
  const key = stepKey(step)
  let isNew = false
  await update($, queued, list => {
    if (list.includes(key)) return list
    isNew = true
    return [...list, key]
  })
  if (!isNew) return
  try {
    await $.command.run({ command, args: step.args })
  } catch (err) {
    // Stopping the session (Ctrl+C, Esc) rejects a run that is queued or running: say that, not "didn't start".
    const line = `/${command}${step.args ? ` ${step.args}` : ''}`
    await $.ui.toast(wasStopped(err) ? `${line} was stopped.` : `/${command} didn't start (${String(err)}).`)
  } finally {
    await update($, queued, list => list.filter(k => k !== key)).catch(() => undefined)
  }
}

/** Whether `$.command.run` rejected because the session stopped the run, not because the command failed to start. */
export const wasStopped = (err: unknown) => /\bwas stopped\b/i.test(String(err))
