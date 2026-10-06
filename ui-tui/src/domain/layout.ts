// Structural TUI layouts — the arrangement of chrome around the transcript.
//
// A layout is selected by `display.layout` in config.yaml, switched live with
// `/layout`, and read here as pure DATA: one `LayoutSpec` table of region
// flags, so the frame components ask "is this region on?" instead of branching
// on layout ids, and every decision is testable without a React runtime.
//
//   minimal    the reading/writing surface: transcript, prompt, one status line
//   workbench  single column — every instrument wraps the composer (default)
//   studio     two panes — a reserved right column holds the live instruments
//
// The ids are a user-facing contract (config value + slash argument), so add to
// the end of LAYOUT_IDS, never rename an existing one.

export const LAYOUT_IDS = ['minimal', 'workbench', 'studio'] as const

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
}

const SPECS: Record<LayoutId, LayoutSpec> = {
  minimal: {
    agentsDock: false,
    dock: false,
    fileChanges: false,
    pet: false,
    rails: false,
    scrollbar: false,
    sideColumn: false,
    statusRule: true,
    stickyPrompt: false,
    todoUnderPrompt: false
  },
  workbench: {
    agentsDock: true,
    dock: true,
    fileChanges: true,
    pet: true,
    rails: true,
    scrollbar: true,
    sideColumn: false,
    statusRule: true,
    stickyPrompt: true,
    todoUnderPrompt: true
  },
  studio: {
    agentsDock: false,
    dock: true,
    fileChanges: true,
    pet: true,
    rails: true,
    scrollbar: true,
    sideColumn: true,
    statusRule: true,
    stickyPrompt: true,
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
  minimal: 'minimal',
  panes: 'studio',
  studio: 'studio',
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
}

/** Resolve a layout id + terminal width into the regions to render. The
 *  single source of truth for the frame components AND their tests: when a
 *  side column cannot be afforded (narrow or single-column hosts) its
 *  instruments fall back to the workbench placement instead of vanishing. */
export const layoutRegions = (id: LayoutId, cols: number, opts: LayoutOptions = {}): LayoutRegions => {
  const spec = layoutSpec(id)
  const sideWidth = !opts.singleColumn && spec.sideColumn ? studioSideWidth(cols) : 0
  const sideActive = sideWidth > 0
  const fallback = spec.sideColumn && !sideActive

  return {
    ...spec,
    agentsDock: spec.agentsDock || fallback,
    rails: spec.rails && !opts.singleColumn,
    sideActive,
    sideWidth,
    todoUnderPrompt: spec.todoUnderPrompt || fallback
  }
}
