import { describe, expect, it } from 'vitest'

import {
  DEFAULT_BORDERS,
  DEFAULT_DESIGN,
  DEFAULT_GLYPHS,
  DEFAULT_HEADER,
  DEFAULT_INDENT,
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

  it('keeps vertical padding inside dialogs and panels in the built-in default', () => {
    // A compact default zeroes overlayPadY/panelPadY, which visually shrinks
    // every popup (approval, secret, sudo, vault unlock) — the regression this
    // guards. The contract is "dialogs breathe", not a specific density name.
    expect(DEFAULT_DESIGN.spacing.overlayPadY).toBeGreaterThan(0)
    expect(DEFAULT_DESIGN.spacing.panelPadY).toBeGreaterThan(0)
  })

  it('overrides individual spacing tokens on top of the density scale', () => {
    const design = resolveDesign({ density: 'compact', spacing: { overlayPadX: 3 } })

    expect(design.spacing.overlayPadX).toBe(3)
    // The rest of the preset survives.
    expect(design.spacing.panelPadX).toBe(DENSITY_SCALES.compact.panelPadX)
  })

  it('ignores out-of-range or wrong-typed spacing values', () => {
    const design = resolveDesign({
      density: 'compact',
      spacing: { overlayPadX: -1, panelPadX: 99, panelPadY: 1.5, rowGap: '2', sectionGap: 2 }
    })

    // The rejected values fall back to THIS design's density preset (compact),
    // not to the built-in default's own scale.
    expect(design.spacing.overlayPadX).toBe(DENSITY_SCALES.compact.overlayPadX)
    expect(design.spacing.panelPadX).toBe(DENSITY_SCALES.compact.panelPadX)
    expect(design.spacing.panelPadY).toBe(DENSITY_SCALES.compact.panelPadY)
    expect(design.spacing.rowGap).toBe(DENSITY_SCALES.compact.rowGap)
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
      alert: DEFAULT_DESIGN.borders.alert,
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

  it('parses the flank style and degrades an unknown one', () => {
    expect(resolveDesign({ flank: 'space' }).flank).toBe('space')
    expect(resolveDesign({ flank: 'none' }).flank).toBe('none')
    expect(resolveDesign({ flank: 'wavy' }).flank).toBe(DEFAULT_DESIGN.flank)
  })

  it('parses each header facet on its own and degrades a bad one', () => {
    expect(resolveDesign({ header: { case: 'upper', emphasis: 'dim', marker: 'rule' } }).header).toEqual({
      case: 'upper',
      emphasis: 'dim',
      marker: 'rule'
    })
    // One bad facet does not drag the others off their default.
    expect(resolveDesign({ header: { case: 'shout', emphasis: 'dim', marker: 'star' } }).header).toEqual({
      ...DEFAULT_HEADER,
      emphasis: 'dim'
    })
    expect(resolveDesign({ header: { case: 'lower' } }).header).toEqual({ ...DEFAULT_HEADER, case: 'lower' })
  })

  it('parses the indent unit and keeps an empty value, because flat is meaningful', () => {
    expect(resolveDesign({ indent: { unit: '', stem: '', branch: '', last: '' } }).indent).toEqual({
      unit: '',
      stem: '',
      branch: '',
      last: ''
    })
    expect(resolveDesign({ indent: { unit: '    ' } }).indent.unit).toBe('    ')
    // An implausibly long step is dropped whole rather than exploding every row.
    expect(resolveDesign({ indent: { unit: 'x'.repeat(20) } }).indent).toEqual(DEFAULT_INDENT)
  })

  it('accepts `none` as a border style and still rejects an unknown one', () => {
    expect(resolveDesign({ borders: { alert: 'none', panel: 'none' } }).borders).toEqual({
      alert: 'none',
      panel: 'none',
      rule: DEFAULT_BORDERS.rule
    })
    expect(resolveDesign({ borders: { panel: 'sparkly' } }).borders).toEqual(DEFAULT_BORDERS)
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

  it('detects a structural difference that changes no colour and no glyph', () => {
    const restructured = resolveDesign({ flank: 'none', header: { marker: 'none' }, indent: { unit: '' } })

    expect(designEquals(DEFAULT_DESIGN, restructured)).toBe(false)
  })

  it('detects an alert-border-only difference, which used to slip through', () => {
    expect(designEquals(DEFAULT_DESIGN, resolveDesign({ borders: { alert: 'none' } }))).toBe(false)
  })
})
