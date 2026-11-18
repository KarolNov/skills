import type { EngineInterface } from 'claude-code'

export const NORMALIZER = '.blueprint/notion_normalize.py'

/** The names a Notion connector goes by: the CLI lists it as `claude.ai Notion`, the desktop app as `Notion`. */
export function serverNames(configured: string): string[] {
  return [...new Set([configured.trim(), 'claude.ai Notion', 'Notion'].filter(Boolean))]
}

const FETCH_TOOL = /^mcp__(.+)__notion-fetch$/

/**
 * The servers to try, in order: the configured name, then every connected
 * server that has a `notion-fetch` tool (by the tool-name spelling, which
 * `$.mcp.call` accepts), then the usual names.
 */
export async function candidates($: EngineInterface, configured: string): Promise<string[]> {
  const [first, ...rest] = serverNames(configured)
  let found: string[] = []
  try {
    found = (await $.tool.list()).flatMap(t => {
      const m = t.mcp ? FETCH_TOOL.exec(t.name) : null
      return m ? [m[1]!] : []
    })
  } catch {
    // No listing: the names alone.
  }
  return [...new Set([first!, ...found, ...rest])]
}

export type Fetched = { markdown: string; server: string } | { error: 'no-server'; tried: string[]; detail: string } | { error: 'fetch' | 'normalize'; detail: string }

/** Fetches a Notion page through the session's own connection and normalizes it as blueprint's baselines are. */
export async function fetchPage($: EngineInterface, url: string, names: string[]): Promise<Fetched> {
  let raw: string | undefined
  let server = ''
  let lastError = ''
  for (const name of names) {
    try {
      const res = await $.mcp.call(name, 'notion-fetch', { id: url })
      const text = res.content.map(b => ('text' in b && typeof b.text === 'string' ? b.text : '')).join('\n')
      if (res.isError) return { error: 'fetch', detail: text.slice(0, 300) || 'Notion returned an error.' }
      raw = text
      server = name
      break
    } catch (err) {
      lastError = String(err)
    }
  }
  if (raw === undefined) return { error: 'no-server', tried: names, detail: lastError.slice(0, 300) }

  const run = await $.process.run(['python3', NORMALIZER, '-'], { stdin: raw, timeoutMs: 15000 })
  if (run.exitCode !== 0) {
    const missing = /No such file|can't open file/i.test(run.stderr)
    return {
      error: 'normalize',
      detail: missing ? `${NORMALIZER} is missing. Run /blueprint-setup again to copy it.` : run.stderr.slice(0, 300) || `exit ${run.exitCode}`,
    }
  }
  return { markdown: run.stdout, server }
}
