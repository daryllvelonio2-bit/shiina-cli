import { describe, expect, it } from 'vitest'

import {
  DEFAULT_DESIGN,
  DEFAULT_GLYPHS,
  DENSITY_SCALES,
  designEquals,
  resolveDesign
} from '../design.js'

describe('resolveDesign', () => {
  it('returns the defaults for a missing or malformed block', () => {
    expect(resolveDesign(undefined)).toEqual(DEFAULT_DESIGN)
    expect(resolveDesign(null)).toEqual(DEFAULT_DESIGN)
    expect(resolveDesign('nope')).toEqual(DEFAULT_DESIGN)
    expect(resolveDesign([])).toEqual(DEFAULT_DESIGN)
  })

  it('picks the spacing scale from the density preset', () => {
    expect(resolveDesign({ density: 'compact' }).spacing).toEqual(DENSITY_SCALES.compact)
    expect(resolveDesign({ density: 'roomy' }).spacing).toEqual(DENSITY_SCALES.roomy)
    // Unknown density falls back to normal rather than throwing.
    expect(resolveDesign({ density: 'gigantic' }).density).toBe('normal')
    expect(resolveDesign({}).spacing).toEqual(DENSITY_SCALES.normal)
  })

  it('overrides individual spacing tokens on top of the density scale', () => {
    const design = resolveDesign({ density: 'compact', spacing: { overlayPadX: 3 } })

    expect(design.spacing.overlayPadX).toBe(3)
    // The rest of the preset survives.
    expect(design.spacing.panelPadX).toBe(DENSITY_SCALES.compact.panelPadX)
  })

  it('ignores out-of-range or wrong-typed spacing values', () => {
    const design = resolveDesign({
      spacing: { overlayPadX: -1, panelPadX: 99, panelPadY: 1.5, rowGap: '2', sectionGap: 2 }
    })

    expect(design.spacing.overlayPadX).toBe(DEFAULT_DESIGN.spacing.overlayPadX)
    expect(design.spacing.panelPadX).toBe(DEFAULT_DESIGN.spacing.panelPadX)
    expect(design.spacing.panelPadY).toBe(DEFAULT_DESIGN.spacing.panelPadY)
    expect(design.spacing.rowGap).toBe(DEFAULT_DESIGN.spacing.rowGap)
    expect(design.spacing.sectionGap).toBe(2)
  })

  it('overrides glyphs but never blanks one', () => {
    const design = resolveDesign({ glyphs: { chevronOpen: 'v', separator: ' · ', bullet: '', unknown: 'x' } })

    expect(design.glyphs.chevronOpen).toBe('v')
    expect(design.glyphs.separator).toBe(' · ')
    // An empty override would make the chrome unreadable — keep the default.
    expect(design.glyphs.bullet).toBe(DEFAULT_GLYPHS.bullet)
    expect(Object.keys(design.glyphs).sort()).toEqual(Object.keys(DEFAULT_GLYPHS).sort())
  })

  it('accepts a known border preset and a single-character rule only', () => {
    expect(resolveDesign({ borders: { panel: 'double', rule: '═' } }).borders).toEqual({
      // `alert` is unset, so it follows `panel`.
      alert: 'double',
      panel: 'double',
      rule: '═'
    })
    expect(resolveDesign({ borders: { panel: 'sparkly', rule: '──' } }).borders).toEqual(DEFAULT_DESIGN.borders)
  })

  it('rejects an unknown alert style and keeps the built-in one', () => {
    const design = resolveDesign({ borders: { alert: 'sparkly', panel: 'bold' } })

    expect(design.borders.alert).toBe(DEFAULT_DESIGN.borders.alert)
    expect(design.borders.panel).toBe('bold')
  })

  it('treats an empty segment list as "unset" and dedupes an explicit one', () => {
    expect(resolveDesign({ status_bar: { segments: [] } }).statusBar.segments).toBeNull()
    expect(resolveDesign({ status_bar: { segments: ['bg', 'bg', 7, 'bg'] } }).statusBar.segments).toEqual(['bg'])
    expect(resolveDesign({ status_bar: { segments: 'bg' } }).statusBar.segments).toBeNull()
  })

  it('keeps an explicit segment order verbatim (order and allowlist)', () => {
    expect(resolveDesign({ status_bar: { segments: ['bg', 'duration'] } }).statusBar.segments).toEqual([
      'bg',
      'duration'
    ])
  })
})

describe('designEquals', () => {
  it('detects a glyph-only difference so the chrome still repaints', () => {
    const restyled = resolveDesign({ glyphs: { separator: ' | ' } })

    expect(designEquals(DEFAULT_DESIGN, DEFAULT_DESIGN)).toBe(true)
    expect(designEquals(DEFAULT_DESIGN, restyled)).toBe(false)
  })

  it('detects a segment-order difference and a density difference', () => {
    expect(designEquals(DEFAULT_DESIGN, resolveDesign({ status_bar: { segments: ['bg'] } }))).toBe(false)
    expect(designEquals(DEFAULT_DESIGN, resolveDesign({ density: 'roomy' }))).toBe(false)
  })

  it('treats two resolutions of the same block as equal', () => {
    const block = { density: 'roomy', glyphs: { chevronOpen: 'v' }, status_bar: { segments: ['bg', 'voice'] } }

    expect(designEquals(resolveDesign(block), resolveDesign(block))).toBe(true)
    expect(designEquals(DEFAULT_DESIGN, resolveDesign(block))).toBe(false)
  })
})
