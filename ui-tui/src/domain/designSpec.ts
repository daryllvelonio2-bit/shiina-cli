import type { DesignBorders, DesignDensity, DesignGlyphs } from '../design.js'
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
  design?: {
    density?: DesignDensity
    panel?: DesignBorders['panel']
    rule?: string
    glyphs?: Partial<DesignGlyphs>
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

const str = (value: unknown): string | undefined =>
  typeof value === 'string' && value.trim() ? value : undefined

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
          density: design.density === 'compact' || design.density === 'roomy' || design.density === 'normal'
            ? design.density
            : undefined,
          glyphs: isRecord(design.glyphs) ? (design.glyphs as Partial<DesignGlyphs>) : undefined,
          panel:
            design.panel === 'single' || design.panel === 'round' || design.panel === 'double' || design.panel === 'bold'
              ? design.panel
              : undefined,
          rule: str(design.rule),
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
      spec.design?.rule ||
      (spec.design?.glyphs && Object.keys(spec.design.glyphs).length) ||
      spec.design?.status_bar ||
      (spec.layout?.regions && Object.keys(spec.layout.regions).length) ||
      (spec.layout?.sections && Object.keys(spec.layout.sections).length)
  )
