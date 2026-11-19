import type { BlueprintUiGroup, BlueprintUiSplit } from '../types'

/** The tool apply calls to show a PR plan in the pane: `mcp__blueprint-ui__split`. */
export const SPLIT_TOOL = 'split'

export const SPLIT_SPEC = {
  name: SPLIT_TOOL,
  description:
    "Show a blueprint change's PR plan in the blueprint pane, as a tree of branches with a ▶ start button for each group that can start now. " +
    'Call it from /blueprint apply when proposing a split (isApproved false), again once the user approves (isApproved true), ' +
    "and whenever a group's state changes (its session started, its PR opened or merged). Each call replaces the change's plan.",
  inputSchema: {
    type: 'object',
    properties: {
      change: { type: 'string', description: "The change's name, as in blueprint.json." },
      defaultBranch: { type: 'string', description: 'The default branch groups are cut from, such as main.' },
      isApproved: { type: 'boolean', description: 'Whether the user approved the plan; before that the pane shows it without start buttons.' },
      groups: {
        type: 'array',
        description: 'In plan order, Specs last.',
        items: {
          type: 'object',
          properties: {
            id: { type: 'string', description: '"1", "2", … or "specs".' },
            name: { type: 'string' },
            tasks: { type: 'string', description: "The brief's task numbers, such as \"1, 2\"." },
            base: { type: 'string', description: 'The default branch, or the id of the group it is stacked on.' },
            prompt: {
              type: 'string',
              description:
                'The prompt its new session starts with: `/blueprint apply <change> <group>` on the first line, then two or three sentences on what the group builds, its base branch and the files it touches.',
            },
            status: { type: 'string', enum: ['planned', 'started', 'pr', 'merged'] },
            pr: { type: 'string', description: "Its PR's link, once open." },
          },
          required: ['id', 'name', 'tasks', 'base', 'prompt'],
        },
      },
    },
    required: ['change', 'groups'],
  },
}

const STATUSES = new Set(['planned', 'started', 'pr', 'merged'])

/** The tool's input, checked: a plan, or why it was refused. */
export function splitOf(input: unknown): BlueprintUiSplit | { error: string } {
  const i = (input ?? {}) as Record<string, unknown>
  if (typeof i.change !== 'string' || !i.change.trim()) return { error: 'change must name the change.' }
  if (!Array.isArray(i.groups) || !i.groups.length) return { error: 'groups must list at least one group.' }
  const defaultBranch = typeof i.defaultBranch === 'string' && i.defaultBranch.trim() ? i.defaultBranch.trim() : 'main'
  const groups: BlueprintUiGroup[] = []
  for (const raw of i.groups as Record<string, unknown>[]) {
    const id = String(raw?.id ?? '').trim()
    if (!id) return { error: 'every group needs an id.' }
    if (groups.some(g => g.id === id)) return { error: `group ${id} is listed twice.` }
    const status = STATUSES.has(String(raw.status)) ? (raw.status as BlueprintUiGroup['status']) : 'planned'
    groups.push({
      id,
      name: String(raw.name ?? id),
      tasks: String(raw.tasks ?? ''),
      base: String(raw.base ?? defaultBranch).trim() || defaultBranch,
      prompt: String(raw.prompt ?? ''),
      status,
      ...(typeof raw.pr === 'string' && raw.pr ? { pr: raw.pr } : {}),
    })
  }
  for (const g of groups) {
    if (g.base === g.id) return { error: `group ${g.id} can't be stacked on itself.` }
    if (g.base !== defaultBranch && !groups.some(o => o.id === g.base)) return { error: `group ${g.id}'s base "${g.base}" is neither ${defaultBranch} nor a group.` }
  }
  return { change: i.change.trim(), defaultBranch, isApproved: i.isApproved === true, groups }
}

export const isSpecs = (g: BlueprintUiGroup) => g.id.toLowerCase() === 'specs'

/**
 * Whether a group can start now: approved, not yet started, and either cut from the default branch
 * or stacked on a group whose PR is open. Specs waits for every other group to merge.
 */
export function isReady(split: BlueprintUiSplit, g: BlueprintUiGroup): boolean {
  if (!split.isApproved || g.status !== 'planned') return false
  if (isSpecs(g)) return split.groups.every(o => o === g || o.status === 'merged')
  if (g.base === split.defaultBranch) return true
  const base = split.groups.find(o => o.id === g.base)
  return !!base && (base.status === 'pr' || base.status === 'merged')
}

/** One line of the tree: its drawn prefix (`│   └── `) and its group. */
export type TreeRow = { prefix: string; group: BlueprintUiGroup }

/**
 * The plan as a tree under the default branch: a stacked group under its base, parallel ones as
 * siblings, Specs last under the default branch since it merges last.
 */
export function treeOf(split: BlueprintUiSplit): TreeRow[] {
  const rows: TreeRow[] = []
  const seen = new Set<string>()
  const walk = (base: string, lead: string) => {
    const kids = split.groups.filter(g => g.base === base && !isSpecs(g) && !seen.has(g.id))
    const all = base === split.defaultBranch ? [...kids, ...split.groups.filter(isSpecs)] : kids
    all.forEach((g, i) => {
      const last = i === all.length - 1
      rows.push({ prefix: `${lead}${last ? '└── ' : '├── '}`, group: g })
      seen.add(g.id)
      if (!isSpecs(g)) walk(g.id, `${lead}${last ? '    ' : '│   '}`)
    })
  }
  walk(split.defaultBranch, '')
  return rows
}

/** How a group's state reads beside it. */
export function stateOf(split: BlueprintUiSplit, g: BlueprintUiGroup): string {
  const stacked = g.base === split.defaultBranch ? '' : `stacked on ${g.base}`
  switch (g.status) {
    case 'starting':
      return 'starting…'
    case 'started':
      return 'in its session'
    case 'pr':
      return 'PR open'
    case 'merged':
      return 'merged'
  }
  if (isSpecs(g)) return 'after every group merges'
  if (isReady(split, g)) return stacked ? `ready · ${stacked}` : 'ready'
  if (!split.isApproved) return stacked || `from ${split.defaultBranch}`
  return `waits for group ${g.base}'s PR`
}

/** What a ▶ start press sends Claude: start each group in its own new session, with the prompt apply wrote. */
export function startPrompt(split: BlueprintUiSplit, groups: BlueprintUiGroup[]): string {
  const one = (g: BlueprintUiGroup) => {
    const base = g.base === split.defaultBranch ? split.defaultBranch : `group ${g.base}'s branch`
    return `Group ${g.id}: ${g.name} (tasks ${g.tasks}, cut from ${base}):\n\n${g.prompt.trim()}`
  }
  const head =
    groups.length === 1
      ? `Start group ${groups[0]!.id} of the blueprint change ${split.change} in a new session, in its own worktree, with this prompt.`
      : `Start these ${groups.length} groups of the blueprint change ${split.change}, each in its own new session and worktree, with these prompts.`
  const tail = `Then call the blueprint-ui split tool to mark ${groups.length === 1 ? 'it' : 'them'} started. Where sessions can't be started here, give me the prompts to paste instead.`
  return `${head}\n\n${groups.map(one).join('\n\n---\n\n')}\n\n${tail}`
}
