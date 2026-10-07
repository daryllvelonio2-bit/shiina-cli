import { describe, expect, it } from 'vitest'

import { applyDesign } from '../domain/applyDesign.js'
import { resolveDesignSpec } from '../domain/designSpec.js'
import { layoutRegions, layoutSections } from '../domain/layout.js'
import { designEquals } from '../design.js'
import { DEFAULT_THEME } from '../theme.js'

// `applyDesign` + the design-file spec. (`__tests__/design.test.ts` covers
// `src/design.ts`, the resolved chrome tokens — a different module.)

describe('resolveDesignSpec', () => {
  it('returns null for anything that is not a design', () => {
    expect(resolveDesignSpec(null)).toBeNull()
    expect(resolveDesignSpec(undefined)).toBeNull()
    expect(resolveDesignSpec({})).toBeNull()
    expect(resolveDesignSpec({ prompt: '>' })).toBeNull() // no name
    expect(resolveDesignSpec('timeline')).toBeNull()
  })

  it('returns null for a design that changes nothing', () => {
    // Load-bearing: uiStore rebuilds `ui.theme` whenever the design identity
    // moves, so a fresh empty spec on every watcher tick would churn every
    // memo() boundary keyed on the theme. `default` arrives exactly like this.
    expect(resolveDesignSpec({ colors: {}, name: 'default' })).toBeNull()
    expect(resolveDesignSpec({ design: {}, layout: {}, name: 'default', spinner: {} })).toBeNull()
  })

  it('parses a real payload', () => {
    const spec = resolveDesignSpec({
      colors: { accent: '#fbbf24' },
      design: { density: 'compact', glyphs: { bullet: '⬤' }, panel: 'bold', rule: '━', status_bar: { segments: null } },
      layout: { regions: { ledger: true }, sections: { thinking: 'collapsed' } },
      name: 'timeline',
      prompt: '▌',
      spinner: { think: ['dna'], tool: ['rain'] }
    })

    expect(spec?.name).toBe('timeline')
    expect(spec?.prompt).toBe('▌')
    expect(spec?.colors).toEqual({ accent: '#fbbf24' })
    expect(spec?.design?.density).toBe('compact')
    expect(spec?.design?.panel).toBe('bold')
    expect(spec?.design?.status_bar).toEqual({ segments: null })
    expect(spec?.layout?.regions).toEqual({ ledger: true })
    expect(spec?.layout?.sections).toEqual({ thinking: 'collapsed' })
    expect(spec?.spinner?.think).toEqual(['dna'])
  })

  it('drops values the renderer cannot honour instead of guessing', () => {
    const spec = resolveDesignSpec({
      colors: { accent: '#fbbf24', bogus: 'not-a-colour', nested: { a: 1 } },
      design: { density: 'enormous', panel: 'spiky', rule: '' },
      layout: { regions: { ledger: 'yes', rails: true } },
      name: 'odd'
    })

    expect(spec?.colors).toEqual({ accent: '#fbbf24' })
    expect(spec?.design?.density).toBeUndefined()
    expect(spec?.design?.panel).toBeUndefined()
    expect(spec?.design?.rule).toBeUndefined()
    // Non-boolean region flags are dropped; real ones survive.
    expect(spec?.layout?.regions).toEqual({ rails: true })
  })
})

describe('applyDesign', () => {
  it('returns the SAME theme object when there is no design', () => {
    // Referential stability is the contract: the frame components memo() on
    // `ui.theme`, so a new-but-equal object would repaint the whole tree.
    expect(applyDesign(DEFAULT_THEME, null)).toBe(DEFAULT_THEME)
  })

  it('applies prompt, density, panel, rule, glyphs and status segments', () => {
    const spec = resolveDesignSpec({
      design: { density: 'compact', glyphs: { bullet: '⬤' }, panel: 'bold', rule: '━', status_bar: { segments: ['model'] } },
      name: 'timeline',
      prompt: '▌'
    })

    const themed = applyDesign(DEFAULT_THEME, spec)

    expect(themed.brand.prompt).toBe('▌')
    expect(themed.design.density).toBe('compact')
    expect(themed.design.borders.panel).toBe('bold')
    expect(themed.design.borders.rule).toBe('━')
    expect(themed.design.glyphs.bullet).toBe('⬤')
    expect(themed.design.statusBar.segments).toEqual(['model'])
  })

  it('applies the alert border independently of the panel border', () => {
    const both = applyDesign(DEFAULT_THEME, resolveDesignSpec({ design: { alert: 'single', panel: 'round' }, name: 'a' }))

    expect(both.design.borders.alert).toBe('single')
    expect(both.design.borders.panel).toBe('round')

    // Setting only `panel` must NOT drag the attention boxes with it: the
    // built-ins are {panel: round, alert: double}, so a design asking for
    // `panel: bold` would otherwise silently restyle every approval prompt.
    const onlyPanel = resolveDesignSpec({ design: { panel: 'bold' }, name: 'b' })
    const themed = applyDesign(DEFAULT_THEME, onlyPanel)

    expect(themed.design.borders.panel).toBe('bold')
    expect(themed.design.borders.alert).toBe(DEFAULT_THEME.design.borders.alert)
  })

  it('rejects an unknown alert style rather than passing it to the renderer', () => {
    const spec = resolveDesignSpec({ design: { alert: 'spiky' }, name: 'c' })

    // `alert: 'spiky'` alone is not a change, so the whole spec is a no-op.
    expect(spec).toBeNull()
  })

  it('applies per-key spacing overrides on top of the density scale', () => {
    const spec = resolveDesignSpec({
      name: 'sp',
      design: { density: 'normal', spacing: { panelPadX: 4, rowGap: 2 } }
    })

    const themed = applyDesign(DEFAULT_THEME, spec)

    // Density still supplies every key the design did not name...
    expect(themed.design.spacing.overlayPadX).toBe(1)
    // ...and the explicit override wins over it.
    expect(themed.design.spacing.panelPadX).toBe(4)
    expect(themed.design.spacing.rowGap).toBe(2)
  })

  it('drops out-of-range spacing values instead of collapsing a layout', () => {
    const spec = resolveDesignSpec({
      name: 'bad-sp',
      design: { spacing: { panelPadX: -3, insetPadX: 99, rowGap: 1.5, overlayPadX: 2 } }
    })

    const themed = applyDesign(DEFAULT_THEME, spec)

    expect(themed.design.spacing.overlayPadX).toBe(2)
    expect(themed.design.spacing.panelPadX).toBe(DEFAULT_THEME.design.spacing.panelPadX)
    expect(themed.design.spacing.rowGap).toBe(DEFAULT_THEME.design.spacing.rowGap)
  })

  it('keeps every glyph the design stayed silent about', () => {
    const spec = resolveDesignSpec({ design: { glyphs: { bullet: '⬤' } }, name: 'partial' })

    const themed = applyDesign(DEFAULT_THEME, spec)

    expect(themed.design.glyphs.bullet).toBe('⬤')
    expect(themed.design.glyphs.check).toBe(DEFAULT_THEME.design.glyphs.check)
  })

  it('overrides only colours the theme actually has', () => {
    // A YAML typo must not inject an unknown field into the render path.
    const spec = resolveDesignSpec({ colors: { accent: '#123456', notARealToken: '#ffffff' }, name: 'colors' })

    const themed = applyDesign(DEFAULT_THEME, spec)

    expect(themed.color.accent).toBe('#123456')
    expect('notARealToken' in themed.color).toBe(false)
  })

  it('leaves untouched fields alone', () => {
    const spec = resolveDesignSpec({ name: 'only-prompt', prompt: '>' })

    const themed = applyDesign(DEFAULT_THEME, spec)

    expect(themed.color).toBe(DEFAULT_THEME.color)
    expect(themed.design.glyphs).toBe(DEFAULT_THEME.design.glyphs)
  })
})

describe('structural overrides', () => {
  it('carries flank, header and indent through to the theme', () => {
    const spec = resolveDesignSpec({
      design: { flank: 'none', header: { case: 'upper', marker: 'rule' }, indent: { unit: '    ' } },
      name: 'structural'
    })

    const themed = applyDesign(DEFAULT_THEME, spec)

    expect(themed.design.flank).toBe('none')
    expect(themed.design.header).toEqual({ ...DEFAULT_THEME.design.header, case: 'upper', marker: 'rule' })
    expect(themed.design.indent).toEqual({ ...DEFAULT_THEME.design.indent, unit: '    ' })
    // A facet the design stayed silent about keeps its built-in value.
    expect(themed.design.header.emphasis).toBe(DEFAULT_THEME.design.header.emphasis)
  })

  it('accepts `none` as a border style', () => {
    const themed = applyDesign(DEFAULT_THEME, resolveDesignSpec({ design: { panel: 'none' }, name: 'borderless' }))

    expect(themed.design.borders.panel).toBe('none')
  })

  it('degrades every malformed structural value to the built-in', () => {
    // Each block is unusable, so nothing changes and the spec stays null —
    // exactly the referential-stability contract `uiStore` relies on.
    expect(resolveDesignSpec({ design: { flank: 'wavy' }, name: 'bad-flank' })).toBeNull()
    expect(resolveDesignSpec({ design: { header: { case: 'shout', marker: 'star' } }, name: 'bad-header' })).toBeNull()
    expect(resolveDesignSpec({ design: { indent: { unit: 'x'.repeat(40) } }, name: 'bad-indent' })).toBeNull()
    expect(resolveDesignSpec({ design: { panel: 'sparkly' }, name: 'bad-panel' })).toBeNull()
  })

  it('lets two designs differ in structure with no colour, glyph or spacing change', () => {
    const flat = applyDesign(
      DEFAULT_THEME,
      resolveDesignSpec({ design: { flank: 'none', header: { marker: 'none' }, indent: { unit: '' } }, name: 'flat' })
    )
    const stepped = applyDesign(
      DEFAULT_THEME,
      resolveDesignSpec(
        { design: { flank: 'rule', header: { marker: 'chevron' }, indent: { unit: '    ' } }, name: 'stepped' }
      )
    )

    expect(flat.color).toBe(stepped.color)
    expect(designEquals(flat.design, stepped.design)).toBe(false)
  })
})

describe('design layout overrides', () => {
  it('regions win over the layout, key by key', () => {
    const base = layoutRegions('workbench', 200)

    expect(base.rails).toBe(true)

    const overridden = layoutRegions('workbench', 200, { regions: { rails: false } })

    expect(overridden.rails).toBe(false)
    expect(overridden.dock).toBe(base.dock) // untouched keys survive
  })

  it('ignores unknown region keys instead of mounting nothing', () => {
    const overridden = layoutRegions('workbench', 200, { regions: { notARegion: true } })

    expect(overridden).toEqual(layoutRegions('workbench', 200))
  })

  it('a single-column host still strips the reserved columns', () => {
    // The host wins: a narrow/phone PTY cannot host a side column however
    // loudly the design asks for one.
    const overridden = layoutRegions('studio', 200, { regions: { sideColumn: true }, singleColumn: true })

    expect(overridden.sideWidth).toBe(0)
    expect(overridden.sideActive).toBe(false)
  })

  it('sections merge key by key', () => {
    const merged = layoutSections('minimal', { thinking: 'expanded' })

    expect(merged.thinking).toBe('expanded')
    expect(merged.tools).toBe(layoutSections('minimal').tools)
  })

  it('returns the spec unchanged when there is no override', () => {
    expect(layoutSections('studio', undefined)).toBe(layoutSections('studio'))
  })
})
