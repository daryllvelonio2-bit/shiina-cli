import type {
  DesignBorders,
  DesignDensity,
  DesignFlank,
  DesignGlyphs,
  DesignHeader,
  DesignIndent,
  DesignSpacing
} from '../design.js'
import type { ThemeBrand } from '../theme.js'
import type { SectionVisibility } from '../types.js'

/**
 * A TUI design, as it arrives from the design folder.
 *
 * This mirrors the YAML schema documented in `shiina_cli/designs/README.md`,
 * one-for-one: the loader resolves a file (inheritance, dynamic colour, user
 * overrides) and hands the result over the gateway, and this is the shape that
 * lands here. Keep the two in step — the schema table in that README is the
 * contract, this is its TypeScript spelling.
 *
 * Every field is optional. A design declares only what it changes; `default`
 * declares nothing at all, which is what makes "no design" and "the built-in
 * look" the same thing.
 */
export interface DesignSpec {
  name: string
  description?: string
  /** Palette overrides, applied on top of whatever the skin resolved. */
  colors?: Record<string, string>
  /** Composer prompt symbol. */
  prompt?: string
  brand?: Partial<ThemeBrand>
  design?: {
    density?: DesignDensity
    panel?: DesignBorders['panel']
    /** Panels that demand attention (approvals, warnings). */
    alert?: DesignBorders['panel']
    rule?: string
    /** How a title/header is flanked: `rule`, blank `space`, or `none`. */
    flank?: DesignFlank
    glyphs?: Partial<DesignGlyphs>
    header?: Partial<DesignHeader>
    indent?: Partial<DesignIndent>
    /** Per-key overrides on top of the density scale. */
    spacing?: Partial<DesignSpacing>
    /** Thinking block display preferences (e.g. maxLines). */
    thinking?: { maxLines?: number | null }
    /** `null` = built-in order and allowlist. */
    status_bar?: { segments?: string[] | null }
  }
  spinner?: {
    think?: string[]
    tool?: string[]
  }
  layout?: {
    regions?: Record<string, boolean>
    sections?: SectionVisibility
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const BORDER_STYLES = ['single', 'double', 'bold', 'round', 'none'] as const

const borderStyle = (value: unknown): DesignBorders['panel'] | undefined =>
  typeof value === 'string' && (BORDER_STYLES as readonly string[]).includes(value)
    ? (value as DesignBorders['panel'])
    : undefined

const isOneOf = <T extends string>(value: unknown, allowed: readonly T[]): value is T =>
  typeof value === 'string' && (allowed as readonly string[]).includes(value)

const FLANKS = ['rule', 'space', 'none'] as const
const HEADER_CASES = ['upper', 'lower', 'none'] as const
const HEADER_EMPHASES = ['bold', 'dim', 'none'] as const
const HEADER_MARKERS = ['chevron', 'rule', 'none'] as const
const INDENT_MAX = 8

const flankStyle = (value: unknown): DesignFlank | undefined =>
  isOneOf(value, FLANKS) ? value : undefined

/** Only the facets the design actually names, so the rest keep their built-in
 *  value; an unknown value for a named facet is dropped, not guessed. */
const headerMap = (raw: unknown): Partial<DesignHeader> | undefined => {
  if (!isRecord(raw)) {
    return undefined
  }

  const out: Partial<DesignHeader> = {}

  if (isOneOf(raw.case, HEADER_CASES)) {
    out.case = raw.case
  }

  if (isOneOf(raw.emphasis, HEADER_EMPHASES)) {
    out.emphasis = raw.emphasis
  }

  if (isOneOf(raw.marker, HEADER_MARKERS)) {
    out.marker = raw.marker
  }

  return Object.keys(out).length ? out : undefined
}

/** Indent fields are strings; `''` is valid (flat), a long value is dropped so
 *  a typo cannot explode every nested row. */
const indentMap = (raw: unknown): Partial<DesignIndent> | undefined => {
  if (!isRecord(raw)) {
    return undefined
  }

  const out: Partial<DesignIndent> = {}

  for (const key of ['unit', 'stem', 'branch', 'last'] as const) {
    const value = raw[key]

    if (typeof value === 'string' && value.length <= INDENT_MAX) {
      out[key] = value
    }
  }

  return Object.keys(out).length ? out : undefined
}

const str = (value: unknown): string | undefined =>
  typeof value === 'string' && value.trim() ? value : undefined

/** Spacing values are small non-negative integers; anything else is dropped so a
 *  bad number cannot collapse or explode a layout. Mirrors `spacingOf` in design.ts. */
const SPACING_KEYS = [
  'insetPadX',
  'insetPadY',
  'overlayPadX',
  'overlayPadY',
  'panelPadX',
  'panelPadY',
  'rowGap',
  'sectionGap'
] as const satisfies readonly (keyof DesignSpacing)[]

const spacingMap = (raw: Record<string, unknown>): Partial<DesignSpacing> | undefined => {
  const out: Partial<DesignSpacing> = {}

  for (const key of SPACING_KEYS) {
    const value = raw[key]

    if (typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 8) {
      out[key] = value
    }
  }

  return Object.keys(out).length ? out : undefined
}

const strList = (value: unknown): string[] | undefined =>
  Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string' && v.trim() !== '') : undefined

/** Colour values must look like colours; anything else is dropped rather than
 *  handed to the renderer, where a bad string becomes an invisible cell. */
const COLORS = /^(#[0-9a-fA-F]{3,8}|[a-zA-Z]+)$/

const colorMap = (value: unknown): Record<string, string> | undefined => {
  if (!isRecord(value)) {
    return undefined
  }

  const out: Record<string, string> = {}

  for (const [key, raw] of Object.entries(value)) {
    const colour = str(raw)

    if (colour && COLORS.test(colour)) {
      out[key] = colour
    }
  }

  return Object.keys(out).length ? out : undefined
}

/**
 * Normalise a design payload from the gateway.
 *
 * Tolerant by construction: an unparseable or partial payload yields a spec
 * with fewer fields rather than an error, because a malformed design file must
 * degrade to the built-in look — never blank the UI or crash the frame.
 *
 * Returns **null** when the payload carries nothing that would change the
 * appearance. That is not a shortcut: `uiStore` recomputes the theme whenever
 * the design object identity moves, so handing back a fresh empty spec every
 * watcher tick would rebuild `ui.theme` per tick and churn every `memo()`
 * boundary keyed on it.
 */
export const resolveDesignSpec = (raw: unknown): DesignSpec | null => {
  if (!isRecord(raw)) {
    return null
  }

  const name = str(raw.name)

  if (!name) {
    return null
  }

  const design = isRecord(raw.design) ? raw.design : undefined
  const statusBar = design && isRecord(design.status_bar) ? design.status_bar : undefined
  const spinner = isRecord(raw.spinner) ? raw.spinner : undefined
  const layout = isRecord(raw.layout) ? raw.layout : undefined

  const segments = statusBar?.segments

  const spec: DesignSpec = {
    name,
    colors: colorMap(raw.colors),
    description: str(raw.description),
    design: design
      ? {
          alert: borderStyle(design.alert),
          density: design.density === 'compact' || design.density === 'roomy' || design.density === 'normal'
            ? design.density
            : undefined,
          flank: flankStyle(design.flank),
          glyphs: isRecord(design.glyphs) ? (design.glyphs as Partial<DesignGlyphs>) : undefined,
          header: headerMap(design.header),
          indent: indentMap(design.indent),
          panel: borderStyle(design.panel),
          rule: str(design.rule),
          spacing: isRecord(design.spacing) ? spacingMap(design.spacing) : undefined,
          status_bar: statusBar ? { segments: segments === null ? null : strList(segments) } : undefined
        }
      : undefined,
    layout: layout
      ? {
          regions: isRecord(layout.regions)
            ? Object.fromEntries(
                Object.entries(layout.regions).filter((entry): entry is [string, boolean] => typeof entry[1] === 'boolean')
              )
            : undefined,
          sections: isRecord(layout.sections) ? (layout.sections as SectionVisibility) : undefined
        }
      : undefined,
    prompt: str(raw.prompt),
    spinner: spinner ? { think: strList(spinner.think), tool: strList(spinner.tool) } : undefined
  }

  return designChangesAnything(spec) ? spec : null
}

/** Does wearing this spec actually alter the built-in appearance? */
const designChangesAnything = (spec: DesignSpec): boolean =>
  Boolean(
    (spec.colors && Object.keys(spec.colors).length) ||
      spec.prompt ||
      spec.spinner?.think?.length ||
      spec.spinner?.tool?.length ||
      spec.design?.density ||
      spec.design?.panel ||
      spec.design?.alert ||
      spec.design?.rule ||
      spec.design?.flank ||
      (spec.design?.header && Object.keys(spec.design.header).length) ||
      (spec.design?.indent && Object.keys(spec.design.indent).length) ||
      (spec.design?.spacing && Object.keys(spec.design.spacing).length) ||
      (spec.design?.glyphs && Object.keys(spec.design.glyphs).length) ||
      spec.design?.status_bar ||
      (spec.layout?.regions && Object.keys(spec.layout.regions).length) ||
      (spec.layout?.sections && Object.keys(spec.layout.sections).length)
  )
