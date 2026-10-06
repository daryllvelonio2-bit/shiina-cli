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
  const statusBar = spec.design?.status_bar

  return {
    ...theme,
    brand: spec.prompt ? { ...theme.brand, prompt: spec.prompt } : theme.brand,
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
      glyphs: glyphs ? { ...design.glyphs, ...glyphs } : design.glyphs,
      statusBar: statusBar ? { segments: statusBar.segments ?? null } : design.statusBar
    }
  }
}
