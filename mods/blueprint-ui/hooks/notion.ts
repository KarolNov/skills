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

type Raw = { raw: string; server: string } | Extract<Fetched, { error: string }>

/** Fetches a Notion page through the session's own connection, as the connector returns it. */
async function fetchRaw($: EngineInterface, url: string, names: string[]): Promise<Raw> {
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
  return { raw, server }
}

/** Runs the normalizer on a fetch result: the page's Markdown, or with `--marker` its version marker. */
async function normalize($: EngineInterface, raw: string, flags: string[], cwd: string): Promise<{ text: string } | { error: 'normalize'; detail: string }> {
  const run = await $.process.run(['python3', NORMALIZER, ...flags, '-'], { stdin: raw, timeoutMs: 15000, cwd })
  if (run.exitCode !== 0) {
    const missing = /No such file|can't open file/i.test(run.stderr)
    return {
      error: 'normalize',
      detail: missing ? `${NORMALIZER} is missing. Run /blueprint-setup again to copy it.` : run.stderr.slice(0, 300) || `exit ${run.exitCode}`,
    }
  }
  return { text: run.stdout }
}

/** Fetches a Notion page through the session's own connection and normalizes it as blueprint's baselines are; `root` holds `.blueprint/`. */
export async function fetchPage($: EngineInterface, url: string, names: string[], root: string): Promise<Fetched> {
  const got = await fetchRaw($, url, names)
  if ('error' in got) return got
  const out = await normalize($, got.raw, [], root)
  return 'error' in out ? out : { markdown: out.text, server: got.server }
}

/** The most SVG markup the desktop's `Svg` element takes. */
export const SVG_MAX = 131072

/** The markup from `<svg` on, when `text` is an SVG document the pane can draw. */
export function svgMarkup(text: string): string | undefined {
  const at = text.search(/<svg[\s>]/i)
  if (at < 0) return undefined
  const svg = text.slice(at).trim()
  return svg.length <= SVG_MAX && /<\/svg>$/i.test(svg) ? svg : undefined
}

/**
 * Downloads uploaded SVG files by their `notion-file-block://` references: signed URLs from
 * `notion-get-file-download-urls` on `server`, then each file through the host. Answers the
 * references that came back as drawable SVG; any that didn't are left out (their links stay).
 */
export async function fetchSvgs($: EngineInterface, server: string, refs: string[]): Promise<Record<string, string>> {
  const out: Record<string, string> = {}
  const unique = [...new Set(refs)]
  for (let i = 0; i < unique.length; i += 25) {
    let files: { reference?: unknown; url?: unknown }[] = []
    try {
      const res = await $.mcp.call(server, 'notion-get-file-download-urls', { references: unique.slice(i, i + 25) })
      if (res.isError) continue
      const text = res.content.map(b => ('text' in b && typeof b.text === 'string' ? b.text : '')).join('')
      const parsed = JSON.parse(text) as { files?: unknown }
      if (Array.isArray(parsed.files)) files = parsed.files
    } catch {
      continue
    }
    await Promise.all(
      files.map(async f => {
        if (typeof f.reference !== 'string' || typeof f.url !== 'string' || !/^https:\/\//.test(f.url)) return
        try {
          const got = await $.http.fetch(f.url)
          const svg = got.ok ? svgMarkup(got.text) : undefined
          if (svg) out[f.reference] = svg
        } catch {
          // Left as a link.
        }
      }),
    )
  }
  return out
}

/** A page's version marker, computed as blueprint computes it for `specVersion`; or why it couldn't be. */
export async function fetchMarker($: EngineInterface, url: string, names: string[], root: string): Promise<{ marker: string } | { error: string }> {
  const got = await fetchRaw($, url, names)
  if ('error' in got) {
    return { error: got.error === 'no-server' ? `no Notion connection answered (${got.tried.join(', ')})` : got.detail }
  }
  const out = await normalize($, got.raw, ['--marker'], root)
  if ('error' in out) return { error: out.detail }
  const marker = out.text.trim()
  return /^[0-9a-f]{16}$/.test(marker) ? { marker } : { error: `the normalizer printed no marker (${marker.slice(0, 60)})` }
}
