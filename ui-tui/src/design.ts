/**
 * Chrome design tokens — the third axis of a TUI redesign, next to colour
 * (`theme.ts`) and words (`content/`).
 *
 * Spacing, glyphs, borders and the status-rule layout live here so restyling
 * the chrome is a token edit, not a hunt through 1,000-line renderers. The
 * tokens ride along with the skin (`tui:` in the skin YAML → `SkinPayload` →
 * `theme.design`), so every component that already receives `t` can read them
 * without new plumbing, and a user restyle needs no code change.
 *
 * Anything a designer may reasonably change belongs here; anything that only
 * exists once (a one-off label) does not.
 */

/** Vertical rhythm presets. `normal` reproduces the pre-token chrome. */
export interface DesignSpacing {
  /** Padding between a panel's content and its border. */
  panelPadX: number
  panelPadY: number
  /** Padding inside an overlay/dialog box. */
  overlayPadX: number
  overlayPadY: number
  /** Padding inside a compact bordered box (prompts, pickers, side panes). */
  insetPadX: number
  insetPadY: number
  /** Gap between stacked list rows. */
  rowGap: number
  /** Space above a section heading. */
  sectionGap: number
}

export type DesignDensity = 'compact' | 'normal' | 'roomy'

export const DENSITY_SCALES: Record<DesignDensity, DesignSpacing> = {
  compact: { insetPadX: 1, insetPadY: 0, overlayPadX: 1, overlayPadY: 0, panelPadX: 1, panelPadY: 0, rowGap: 0, sectionGap: 0 },
  normal: { insetPadX: 1, insetPadY: 0, overlayPadX: 1, overlayPadY: 1, panelPadX: 2, panelPadY: 1, rowGap: 0, sectionGap: 1 },
  roomy: { insetPadX: 2, insetPadY: 0, overlayPadX: 2, overlayPadY: 1, panelPadX: 3, panelPadY: 1, rowGap: 1, sectionGap: 2 }
}

/**
 * The single-character vocabulary of the chrome. Components must render these
 * tokens instead of inline literals so a glyph restyle is one edit — and so a
 * terminal with poor Unicode coverage can be accommodated in one place.
 */
export interface DesignGlyphs {
  /** Opens a collapsed section. */
  chevronClosed: string
  /** Closes an expanded section. */
  chevronOpen: string
  /** Tool-call / list bullet. */
  bullet: string
  /** Completed step. */
  check: string
  /** Not-yet-started step. */
  pending: string
  /** Active row marker. */
  active: string
  /** Status-rule segment separator (includes its own spacing). */
  separator: string
  /** Inline separator between display segments — compact meta lines, list
   *  joins (`d2 · 7 agents`). Includes its own spacing, like `separator`. */
  dotSeparator: string
  /** A filled meter cell (usage / context bars). */
  barFill: string
  /** The unfilled remainder of a meter. */
  barEmpty: string
  /** Major tick on a timeline ruler. */
  rulerTick: string
  /** Leading status-rule dash (includes its trailing space). */
  statusHead: string
  /** Subagent/delegation count. */
  chain: string
  /** Cache-hit readout. */
  cache: string
  /** Average-latency readout. */
  latency: string
  /** Tokens-per-second readout. */
  tps: string
  /** Focus-view badge. */
  focus: string
  /** Idle clock / turn finished. */
  idle: string
  /** "Resumes when the subagent finishes" hint. */
  resume: string
  /** Unavailable / not-authenticated marker. */
  off: string
  /** The currently-selected entry. */
  selected: string
  /** Failed / disabled / negative marker. */
  cross: string
  /** A running/working row. */
  progress: string
  /** A starting/loading row. */
  ellipsis: string
  /** A row waiting on input. */
  waiting: string
  /** A warning marker. */
  warn: string
  /** Attention: an approval, a destructive confirm, a crashed widget. */
  alert: string
  /** A refused / rejected request. */
  blocked: string
  /** Work in progress: the busy tab marker, a scheduled change. */
  busy: string
  /** A checked checklist item. */
  checkboxOn: string
  /** An unchecked checklist item. */
  checkboxOff: string
  /** Opens a collapsible block that is not an `Accordion` (`<summary>`). */
  disclosure: string
  /** A filled dot: markdown list items, masked input. */
  dot: string
  /** Interrupted / cancelled. */
  halt: string
  /** Partially complete (a subagent finalizing). */
  partial: string
  /** Timed out. */
  timeout: string
  /** A vertical chrome line: tree rails, the blockquote rail, a scroll track. */
  railVertical: string
  /** A tree rail that continues below this row. */
  railTee: string
  /** A tree rail that ends at this row. */
  railElbow: string
  /** The scrollbar's thumb (a heavier vertical than the track). */
  scrollThumb: string
}

export const DEFAULT_GLYPHS: DesignGlyphs = {
  active: '⏺',
  alert: '⚠',
  barEmpty: '░',
  barFill: '█',
  blocked: '⊘',
  bullet: '•',
  busy: '⏳',
  cache: '◎',
  chain: '⛓',
  check: '✔',
  checkboxOff: '☐',
  checkboxOn: '☑',
  chevronClosed: '›',
  chevronOpen: '⌄',
  cross: '✘',
  disclosure: '▶',
  dot: '•',
  dotSeparator: ' · ',
  ellipsis: '⋯',
  focus: '◉',
  halt: '■',
  idle: '✔',
  latency: '◷',
  off: '◌',
  partial: '◐',
  pending: '⋅',
  progress: '⏺',
  railElbow: ' ',
  railTee: ' ',
  railVertical: ' ',
  resume: '↩',
  rulerTick: '┼',
  scrollThumb: '┃',
  selected: '❯',
  separator: '  ',
  statusHead: '',
  timeout: '⌛',
  tps: '↑',
  waiting: '◦',
  warn: '!'
}

/**
 * Box-drawing border language. `none` draws no box at all: the panel keeps its
 * content and padding but reclaims the border cells, so a borderless design is
 * a real layout choice rather than a recoloured box.
 */
export type DesignBorderStyle = 'single' | 'round' | 'double' | 'bold' | 'none'

/** Line-drawing characters for rules and separators. */
export interface DesignBorders {
  /** Horizontal rule character (status rule, title flanking). */
  rule: string
  /** Native box-drawing border style for panels and overlays. */
  panel: DesignBorderStyle
  /** Panels that demand attention (approvals, warnings). Defaults to `panel`. */
  alert: DesignBorderStyle
}

export const DEFAULT_BORDERS: DesignBorders = { alert: 'single', panel: 'single', rule: '─' }

/**
 * Status-rule layout. `segments === null` keeps the built-in order and shows
 * every segment whose own gate passes; an explicit array is both the order and
 * the allowlist (ids left out are hidden).
 */
export interface DesignStatusBar {
  segments: string[] | null
}

/** How a title is flanked by decoration — the lines beside a header. */
export type DesignFlank = 'rule' | 'space' | 'none'

/** Header label transform. */
export type DesignHeaderCase = 'upper' | 'lower' | 'none'

/** Header weight. */
export type DesignHeaderEmphasis = 'bold' | 'dim' | 'none'

/** The decoration a header is drawn with before its label. */
export type DesignHeaderMarker = 'chevron' | 'rule' | 'none'

export interface DesignHeader {
  /** Label transform: `upper`, `lower`, or as authored. */
  case: DesignHeaderCase
  /** Weight: `bold`, `dim`, or plain. */
  emphasis: DesignHeaderEmphasis
  /** Leading decoration: the expand chevron, a rule dash, or nothing. */
  marker: DesignHeaderMarker
}

export const DEFAULT_HEADER: DesignHeader = { case: 'none', emphasis: 'dim', marker: 'none' }

/**
 * One nesting step of the tree and ledger chrome.
 *
 * Every field is a string, so a design can be flat (`''`) or deeply stepped;
 * `unit` is repeated once per depth, which makes its width the indent width.
 */
export interface DesignIndent {
  /** One nesting level, repeated per depth. `''` flattens the tree. */
  unit: string
  /** The rail drawn inside a level whose branch continues. */
  stem: string
  /** Lead before a non-final child. */
  branch: string
  /** Lead before the final child. */
  last: string
}

export const DEFAULT_INDENT: DesignIndent = { branch: '  ', last: '  ', stem: '  ', unit: '  ' }

export interface DesignThinking {
  /** Maximum lines to display in the thinking trail. 0 or null = unlimited / show all. */
  maxLines?: number | null
}

export interface Design {
  borders: DesignBorders
  density: DesignDensity
  flank: DesignFlank
  glyphs: DesignGlyphs
  header: DesignHeader
  indent: DesignIndent
  spacing: DesignSpacing
  statusBar: DesignStatusBar
  thinking?: DesignThinking
  colors?: Record<string, string>
}

export const DEFAULT_DESIGN: Design = {
  borders: DEFAULT_BORDERS,
  density: 'normal',
  flank: 'space',
  glyphs: DEFAULT_GLYPHS,
  header: DEFAULT_HEADER,
  indent: DEFAULT_INDENT,
  spacing: DENSITY_SCALES.normal,
  statusBar: { segments: null },
  thinking: { maxLines: null }
}

/**
 * The decoration a header is drawn with before its label. `rule` reuses the
 * status-rule lead so a "flat" design can head sections the same way it heads
 * the status line; `none` leaves the label bare (the row is still clickable).
 */
export const headerLead = (header: DesignHeader, open: boolean, glyphs: DesignGlyphs): string => {
  if (header.marker === 'rule') {
    return glyphs.statusHead
  }

  if (header.marker === 'none') {
    return ''
  }

  return `${open ? glyphs.chevronOpen : glyphs.chevronClosed} `
}

/** A header label after its case transform. */
export const headerLabel = (header: DesignHeader, title: string): string =>
  header.case === 'upper' ? title.toUpperCase() : header.case === 'lower' ? title.toLowerCase() : title

/** The `bold`/`dim` props a header's Text node should carry. */
export const headerEmphasis = (header: DesignHeader): { bold?: true; dim?: true } =>
  header.emphasis === 'bold' ? { bold: true } : header.emphasis === 'dim' ? { dim: true } : {}

/**
 * The decoration flanking a title, `count` cells wide: a drawn `rule`, blank
 * `space` (keeps the title centred but draws nothing), or nothing at all.
 */
export const flankFill = (flank: DesignFlank, rule: string, count: number): string =>
  count <= 0 ? '' : flank === 'rule' ? rule.repeat(count) : flank === 'space' ? ' '.repeat(count) : ''

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const densityOf = (value: unknown): DesignDensity =>
  value === 'compact' || value === 'roomy' ? value : 'normal'

/** Only tokens the chrome actually renders are overridable, and only with a
 *  non-empty string: a skin typo must not blank a glyph. */
const glyphsOf = (raw: unknown): DesignGlyphs => {
  if (!isRecord(raw)) {
    return DEFAULT_GLYPHS
  }

  const glyphs = { ...DEFAULT_GLYPHS }

  for (const key of Object.keys(DEFAULT_GLYPHS) as (keyof DesignGlyphs)[]) {
    const value = raw[key]

    if (typeof value === 'string' && value.length > 0) {
      glyphs[key] = value
    }
  }

  return glyphs
}

const isOneOf = <T extends string>(value: unknown, allowed: readonly T[]): value is T =>
  typeof value === 'string' && (allowed as readonly string[]).includes(value)

const BORDER_STYLES = ['single', 'double', 'bold', 'round', 'none'] as const

const borderStyleOf = (value: unknown, fallback: DesignBorderStyle): DesignBorderStyle =>
  isOneOf(value, BORDER_STYLES) ? value : fallback

const bordersOf = (raw: unknown): DesignBorders => {
  if (!isRecord(raw)) {
    return DEFAULT_BORDERS
  }

  const panel = borderStyleOf(raw.panel, DEFAULT_BORDERS.panel)

  return {
    // `alert` is independent of `panel` on purpose: the built-ins are
    // {panel: round, alert: double}, so deriving one from the other would make
    // "panel: round" silently restyle the approval boxes. A design that wants
    // them to match sets the same value for both.
    alert: borderStyleOf(raw.alert, DEFAULT_BORDERS.alert),
    panel,
    rule: typeof raw.rule === 'string' && raw.rule.length === 1 ? raw.rule : DEFAULT_BORDERS.rule
  }
}

const spacingOf = (raw: unknown, density: DesignDensity): DesignSpacing => {
  const scale = DENSITY_SCALES[density]

  if (!isRecord(raw)) {
    return scale
  }

  const spacing = { ...scale }

  for (const key of Object.keys(scale) as (keyof DesignSpacing)[]) {
    const value = raw[key]

    if (typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 8) {
      spacing[key] = value
    }
  }

  return spacing
}

const statusBarOf = (raw: unknown): DesignStatusBar => {
  const segments = isRecord(raw) ? raw.segments : undefined

  if (!Array.isArray(segments)) {
    return { segments: null }
  }

  // Dedupe: a repeated id would render the segment twice and double-charge the
  // width budget.
  const ids = [...new Set(segments.filter((id): id is string => typeof id === 'string' && !!id))]

  return { segments: ids.length > 0 ? ids : null }
}

const FLANKS = ['rule', 'space', 'none'] as const
const HEADER_CASES = ['upper', 'lower', 'none'] as const
const HEADER_EMPHASES = ['bold', 'dim', 'none'] as const
const HEADER_MARKERS = ['chevron', 'rule', 'none'] as const

const flankOf = (value: unknown): DesignFlank => (isOneOf(value, FLANKS) ? value : DEFAULT_DESIGN.flank)

/** Each header facet falls back independently, so `case: upper` alone still
 *  keeps the built-in emphasis and marker. */
const headerOf = (raw: unknown): DesignHeader => {
  if (!isRecord(raw)) {
    return DEFAULT_HEADER
  }

  return {
    case: isOneOf(raw.case, HEADER_CASES) ? raw.case : DEFAULT_HEADER.case,
    emphasis: isOneOf(raw.emphasis, HEADER_EMPHASES) ? raw.emphasis : DEFAULT_HEADER.emphasis,
    marker: isOneOf(raw.marker, HEADER_MARKERS) ? raw.marker : DEFAULT_HEADER.marker
  }
}

const INDENT_KEYS = ['unit', 'stem', 'branch', 'last'] as const satisfies readonly (keyof DesignIndent)[]
const INDENT_MAX = 8

const indentOf = (raw: unknown): DesignIndent => {
  if (!isRecord(raw)) {
    return DEFAULT_INDENT
  }

  const indent = { ...DEFAULT_INDENT }

  for (const key of INDENT_KEYS) {
    const value = raw[key]

    // Unlike a glyph, `''` is meaningful here: it is how a design goes flat.
    // The cap keeps a fat-fingered value from exploding every nested row.
    if (typeof value === 'string' && value.length <= INDENT_MAX) {
      indent[key] = value
    }
  }

  return indent
}

/**
 * Build the chrome design from a skin's `tui:` section.
 *
 * Unknown keys, wrong types and out-of-range values fall back per token rather
 * than rejecting the block: a half-authored restyle should still render, and a
 * typo must never take the chrome down.
 */
export const resolveDesign = (raw: unknown): Design => {
  if (!isRecord(raw)) {
    return DEFAULT_DESIGN
  }

  const density = densityOf(raw.density)

  return {
    borders: bordersOf(raw.borders),
    density,
    flank: flankOf(raw.flank),
    glyphs: glyphsOf(raw.glyphs),
    header: headerOf(raw.header),
    indent: indentOf(raw.indent),
    spacing: spacingOf(raw.spacing, density),
    statusBar: statusBarOf(raw.status_bar)
  }
}

/** Token equality for the theme commit path (a glyph-only skin edit still repaints). */
export const designEquals = (a: Design, b: Design): boolean => {
  if (a === b) {
    return true
  }

  if (
    a.density !== b.density ||
    a.borders.panel !== b.borders.panel ||
    a.borders.alert !== b.borders.alert ||
    a.borders.rule !== b.borders.rule ||
    a.flank !== b.flank ||
    a.header.case !== b.header.case ||
    a.header.emphasis !== b.header.emphasis ||
    a.header.marker !== b.header.marker
  ) {
    return false
  }

  if ((a.statusBar.segments ?? []).join('|') !== (b.statusBar.segments ?? []).join('|')) {
    return false
  }

  for (const key of Object.keys(a.glyphs) as (keyof DesignGlyphs)[]) {
    if (a.glyphs[key] !== b.glyphs[key]) {
      return false
    }
  }

  for (const key of Object.keys(a.indent) as (keyof DesignIndent)[]) {
    if (a.indent[key] !== b.indent[key]) {
      return false
    }
  }

  for (const key of Object.keys(a.spacing) as (keyof DesignSpacing)[]) {
    if (a.spacing[key] !== b.spacing[key]) {
      return false
    }
  }

  return true
}
