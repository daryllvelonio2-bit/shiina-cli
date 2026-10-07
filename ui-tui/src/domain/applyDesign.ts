import { DEFAULT_DESIGN, DENSITY_SCALES } from '../design.js'
import type { Theme, ThemeColors } from '../theme.js'

import type { DesignSpec } from './designSpec.js'

/**
 * Wear a design on the theme.
 *
 * The frame components all receive `t = ui.theme` and read `t.color.*`,
 * `t.design.*` and `t.brand.prompt`, so applying the design HERE — once, where
 * the theme is resolved — makes every colour, glyph, rule, border, prompt and
 * status-bar honour it without a single component learning that designs exist.
 *
 * Pure and referentially transparent: a missing/empty spec returns the SAME
 * theme object, so the `memo()` boundaries that key on `ui.theme` do not churn.
 * That is also why `default` declaring nothing is meaningful — no design and
 * the built-in look resolve to the identical object.
 *
 * Colours are applied by KEY EXISTENCE, not appended: a design naming a key the
 * theme does not have is ignored rather than injected, so a typo in a YAML file
 * cannot put an unknown field into the render path.
 */
export const applyDesign = (theme: Theme, spec: DesignSpec | null): Theme => {
  if (!spec) {
    return theme
  }

  const design = theme.design ?? DEFAULT_DESIGN

  const colors = Object.entries(spec.colors ?? {}).reduce<Partial<ThemeColors>>((acc, [key, value]) => {
    if (key in theme.color) {
      acc[key as keyof ThemeColors] = value
    }

    return acc
  }, {})

  const density = spec.design?.density
  const glyphs = spec.design?.glyphs
  const panel = spec.design?.panel
  const alert = spec.design?.alert
  const rule = spec.design?.rule
  const flank = spec.design?.flank
  const header = spec.design?.header
  const indent = spec.design?.indent
  const spacing = spec.design?.spacing
  const statusBar = spec.design?.status_bar
  const thinkingDesign = spec.design?.thinking
  const brand = {
    ...theme.brand,
    ...(spec.prompt ? { prompt: spec.prompt } : {}),
    ...(spec.brand ? spec.brand : {})
  }

  return {
    ...theme,
    brand,
    color: Object.keys(colors).length ? { ...theme.color, ...colors } : theme.color,
    design: {
      ...design,
      borders: {
        ...design.borders,
        ...(alert ? { alert } : {}),
        ...(panel ? { panel } : {}),
        ...(rule ? { rule } : {})
      },
      ...(density ? { density, spacing: DENSITY_SCALES[density] } : {}),
      flank: flank ?? design.flank,
      glyphs: glyphs ? { ...design.glyphs, ...glyphs } : design.glyphs,
      header: header ? { ...design.header, ...header } : design.header,
      indent: indent ? { ...design.indent, ...indent } : design.indent,
      // After the density block on purpose: an explicit per-key override wins
      // over the scale the density just installed.
      ...(spacing ? { spacing: { ...(density ? DENSITY_SCALES[density] : design.spacing), ...spacing } } : {}),
      statusBar: statusBar ? { segments: statusBar.segments ?? null } : design.statusBar,
      thinking: thinkingDesign ? { maxLines: thinkingDesign.maxLines } : design.thinking,
      colors: spec.colors ?? design.colors
    }
  }
}
