// TUI layouts — the arrangement of chrome around the transcript AND the way a
// turn's progress reads inside it.
//
// A layout is selected by `display.layout` in config.yaml, switched live with
// `/layout`, and read here as pure DATA: one `LayoutSpec` table, so the frame
// components ask "is this region on?" / "how does progress read?" instead of
// branching on layout ids, and every decision is testable without a React
// runtime.
//
//   minimal    the reading surface — transcript, prompt, one status line, and
//              progress folded to a single compact row
//   workbench  single column — every instrument wraps the composer; the
//              long-standing default shape (progress streams open)
//   studio     two panes — a reserved right column holds the live instruments
//   timeline   progress-forward — the turn's steps stay visible as a running
//              ledger under the transcript, chrome kept quiet
//
// Two axes, deliberately separate:
//   * REGIONS (`LayoutSpec`) say where chrome sits.
//   * PROGRESS (`LayoutSpec.sections`) says how much of the agent's work shows
//     by default — the reasoning, tool calls and subagent trees a design leads
//     with. It layers exactly where `SECTION_DEFAULTS` used to sit (see
//     domain/details.ts), so an explicit `display.sections.*` or `/details`
//     still wins, and settled turns still paint nothing unless asked.
//
// The ids are a user-facing contract (config value + slash argument), so add to
// the end of LAYOUT_IDS, never rename an existing one.

import type { SectionVisibility } from '../types.js'

export const LAYOUT_IDS = ['minimal', 'workbench', 'studio', 'timeline'] as const

export type LayoutId = (typeof LAYOUT_IDS)[number]

export const DEFAULT_LAYOUT: LayoutId = 'workbench'

export interface LayoutSpec {
  /** Ambient corner-widget rails reserve columns beside the transcript. */
  rails: boolean
  /** Ambient widget dock rows ride above/below the composer. */
  dock: boolean
  /** Floating pet overlay in the bottom-right corner. */
  pet: boolean
  /** The one-line status rule (spinner, model, cwd, notices). */
  statusRule: boolean
  /** Live file-changes strip above the status rule. */
  fileChanges: boolean
  /** Live subagent board above the composer. */
  agentsDock: boolean
  /** Live todo panel pinned to the latest user row. */
  todoUnderPrompt: boolean
  /** Sticky-prompt echo above the composer. */
  stickyPrompt: boolean
  /** Transcript scrollbar gutter column. */
  scrollbar: boolean
  /** A reserved right-hand instrument column (agents + todo live there). */
  sideColumn: boolean
  /** The live step ledger — the running turn's steps as a persistent list. */
  ledger: boolean
  /** Default per-section progress visibility. Absent keys fall through to the
   *  global details mode, matching the pre-layout behaviour. */
  sections: SectionVisibility
}

const SPECS: Record<LayoutId, LayoutSpec> = {
  // Reading and typing. Progress is present but folded to one compact row per
  // section: the transcript is the point, not the instrument panel.
  minimal: {
    agentsDock: false,
    dock: false,
    fileChanges: false,
    ledger: false,
    pet: false,
    rails: false,
    scrollbar: false,
    sections: { activity: 'hidden', subagents: 'hidden', thinking: 'collapsed', tools: 'collapsed' },
    sideColumn: false,
    statusRule: true,
    stickyPrompt: false,
    todoUnderPrompt: false
  },
  // The compatibility default — its section defaults are byte-for-byte the
  // built-in ones (thinking/tools expanded, activity hidden, subagents falling
  // through to the global mode), so an existing user sees no change at all.
  workbench: {
    agentsDock: true,
    dock: true,
    fileChanges: true,
    ledger: false,
    pet: true,
    rails: true,
    scrollbar: true,
    sections: { activity: 'hidden', thinking: 'live', tools: 'live' },
    sideColumn: false,
    statusRule: true,
    stickyPrompt: true,
    todoUnderPrompt: true
  },
  // Panes. The reserved column already carries the team, so subagent trees
  // stream open too — the pane is where a delegation is watched.
  studio: {
    agentsDock: false,
    dock: true,
    fileChanges: true,
    ledger: false,
    pet: true,
    rails: true,
    scrollbar: true,
    sections: { activity: 'hidden', subagents: 'live', thinking: 'live', tools: 'live' },
    sideColumn: true,
    statusRule: true,
    stickyPrompt: true,
    todoUnderPrompt: false
  },
  // Progress-forward. The ledger keeps the turn's steps on screen, tool calls
  // and subagent trees stay open, and the reasoning stays a compact running
  // line instead of a wall of prose.
  timeline: {
    agentsDock: false,
    dock: true,
    fileChanges: true,
    ledger: true,
    pet: false,
    rails: false,
    scrollbar: true,
    sections: { activity: 'collapsed', subagents: 'live', thinking: 'collapsed', tools: 'live' },
    sideColumn: false,
    statusRule: true,
    stickyPrompt: false,
    todoUnderPrompt: false
  }
}

export const LAYOUT_SPECS: Readonly<Record<LayoutId, LayoutSpec>> = SPECS

/** Aliases accepted from config.yaml / slash arguments. Unknown words fall
 *  back to the default instead of failing: a typo must not blank the TUI. */
const LAYOUT_ALIASES: Record<string, LayoutId> = {
  bare: 'minimal',
  default: 'workbench',
  full: 'workbench',
  ledger: 'timeline',
  minimal: 'minimal',
  panes: 'studio',
  steps: 'timeline',
  studio: 'studio',
  timeline: 'timeline',
  workbench: 'workbench',
  zen: 'minimal'
}

export const normalizeLayout = (raw: unknown): LayoutId =>
  typeof raw === 'string' ? (parseLayout(raw) ?? DEFAULT_LAYOUT) : DEFAULT_LAYOUT

/** Strict resolver for user input — null (not the default) on an unknown word,
 *  so an explicit `/layout studioo` reports usage instead of silently moving. */
export const parseLayout = (raw: string): LayoutId | null => {
  const word = raw.trim().toLowerCase()

  return word ? (LAYOUT_ALIASES[word] ?? null) : null
}

export const layoutSpec = (id: LayoutId): LayoutSpec => SPECS[id] ?? SPECS[DEFAULT_LAYOUT]

/** Default per-section progress visibility for a layout.
 *
 *  ``override`` is a design's `layout.sections` block and wins key-by-key, so a
 *  design can say "this one opens the tool trail" without restating the rest.
 *  Absent keys still fall through to the global details mode. */
export const layoutSections = (id: LayoutId, override?: SectionVisibility): SectionVisibility => {
  const spec = layoutSpec(id).sections

  return override ? { ...spec, ...override } : spec
}

/** Next layout in the cycle — bare `/layout` walks this order. */
export const cycleLayout = (id: LayoutId): LayoutId => LAYOUT_IDS[(LAYOUT_IDS.indexOf(id) + 1) % LAYOUT_IDS.length]

// Below STUDIO_MIN_COLS a side column would starve the transcript, so studio
// degrades to its single-column instrument placement instead of rendering a
// sliver.
export const STUDIO_MIN_COLS = 100
const STUDIO_SIDE_MIN = 32
const STUDIO_SIDE_MAX = 48
const STUDIO_SIDE_FRACTION = 0.26

export const studioSideWidth = (cols: number): number =>
  cols < STUDIO_MIN_COLS
    ? 0
    : Math.min(STUDIO_SIDE_MAX, Math.max(STUDIO_SIDE_MIN, Math.round(cols * STUDIO_SIDE_FRACTION)))

export interface LayoutRegions extends LayoutSpec {
  /** Rendered width of the reserved instrument column (0 = not rendered). */
  sideWidth: number
  /** True when the side column is actually rendered at this width. */
  sideActive: boolean
}

export interface LayoutOptions {
  /** Inline mode (native scrollback) and phone PTYs: panes and reserved rails
   *  fight the host terminal, so degrade to the single-column arrangement. */
  singleColumn?: boolean
  /** A design's `layout.regions` block. Boolean keys win over the built-in
   *  spec, so a design file can rearrange the chrome with no code change. */
  regions?: Record<string, boolean>
}

// The region flags a design may override. Anything outside this list is ignored
// rather than written onto the spec, so a typo cannot mount a phantom region.
const REGION_KEYS = [
  'agentsDock',
  'dock',
  'fileChanges',
  'ledger',
  'pet',
  'rails',
  'scrollbar',
  'sideColumn',
  'statusRule',
  'stickyPrompt',
  'todoUnderPrompt'
] as const

/** Fold a design's region overrides onto a layout spec before the derived
 *  fallbacks run, so "the design asked for no side column" behaves exactly like
 *  the layout itself declaring it. */
const withRegionOverrides = (spec: LayoutSpec, over?: Record<string, boolean>): LayoutSpec => {
  if (!over) {
    return spec
  }

  let out = spec

  for (const key of REGION_KEYS) {
    const value = over[key]

    if (typeof value === 'boolean' && out[key] !== value) {
      out = { ...out, [key]: value }
    }
  }

  return out
}

/** Resolve a layout id + terminal width into the regions to render. The
 *  single source of truth for the frame components AND their tests: when a
 *  side column cannot be afforded (narrow or single-column hosts) its
 *  instruments fall back to the workbench placement instead of vanishing. */
export const layoutRegions = (id: LayoutId, cols: number, opts: LayoutOptions = {}): LayoutRegions => {
  const spec = withRegionOverrides(layoutSpec(id), opts.regions)
  const sideWidth = !opts.singleColumn && spec.sideColumn ? studioSideWidth(cols) : 0
  const sideActive = sideWidth > 0
  const fallback = spec.sideColumn && !sideActive
  // A reserved column or a phone PTY leaves no room for a persistent ledger;
  // its steps fall back to the instruments the layout would otherwise wrap.
  const ledger = spec.ledger && !opts.singleColumn && !sideActive

  return {
    ...spec,
    agentsDock: spec.agentsDock || fallback || (spec.ledger && !ledger),
    ledger,
    rails: spec.rails && !opts.singleColumn,
    sideActive,
    sideWidth,
    todoUnderPrompt: spec.todoUnderPrompt || fallback
  }
}
