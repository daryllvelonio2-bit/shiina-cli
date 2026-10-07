/**
 * Structural layout contract: `display.layout` selects one of four region
 * tables, and the resolver must stay total (a typo can never blank the TUI)
 * while keeping the four arrangements genuinely distinct — in placement AND in
 * how much of a turn's progress each one shows by default.
 */
import { describe, expect, it } from 'vitest'

import { detailsRequested, sectionMode } from '../domain/details.js'
import type { LayoutId } from '../domain/layout.js'
import {
  cycleLayout,
  DEFAULT_LAYOUT,
  LAYOUT_IDS,
  LAYOUT_SPECS,
  layoutRegions,
  layoutSections,
  layoutSpec,
  normalizeLayout,
  parseLayout,
  STUDIO_MIN_COLS,
  studioSideWidth
} from '../domain/layout.js'

describe('layout selection', () => {
  it('normalises config input and falls back to the default on garbage', () => {
    expect(normalizeLayout(' Studio ')).toBe('studio')
    expect(normalizeLayout('zen')).toBe('minimal')
    expect(normalizeLayout('panes')).toBe('studio')
    // A typo, a wrong type or a missing key must keep the current default
    // instead of resolving to undefined and rendering an empty frame.
    expect(normalizeLayout('emacs')).toBe(DEFAULT_LAYOUT)
    expect(normalizeLayout(42)).toBe(DEFAULT_LAYOUT)
    expect(normalizeLayout(undefined)).toBe(DEFAULT_LAYOUT)
    expect(LAYOUT_IDS).toContain(DEFAULT_LAYOUT)
  })

  it('refuses an unknown explicit word so /layout can report usage', () => {
    expect(parseLayout('studioo')).toBeNull()
    expect(parseLayout('')).toBeNull()
    expect(parseLayout(' WorkBench ')).toBe('workbench')
  })

  it('cycles through every layout and returns to the start', () => {
    expect(cycleLayout('minimal')).not.toBe('minimal')

    let id: LayoutId = LAYOUT_IDS[0]

    for (let i = 0; i < LAYOUT_IDS.length; i++) {
      id = cycleLayout(id)
    }

    expect(id).toBe(LAYOUT_IDS[0])
  })
})

describe('layout regions', () => {
  it('every layout is a distinct arrangement', () => {
    const shapes = LAYOUT_IDS.map(id => JSON.stringify(layoutSpec(id)))

    expect(new Set(shapes).size).toBe(LAYOUT_IDS.length)
  })

  it('minimal drops the widget chrome but keeps the status line', () => {
    const r = layoutRegions('minimal', 120)

    expect(r).toMatchObject({
      agentsDock: false,
      dock: false,
      fileChanges: false,
      pet: false,
      rails: false,
      scrollbar: false,
      sideActive: false,
      statusRule: true,
      stickyPrompt: false,
      todoUnderPrompt: false
    })
  })

  it('workbench keeps every instrument in the composer flow', () => {
    const r = layoutRegions('workbench', 120)

    expect(r).toMatchObject({
      agentsDock: true,
      dock: true,
      pet: true,
      rails: true,
      scrollbar: true,
      sideActive: false,
      statusRule: true,
      todoUnderPrompt: true
    })
  })

  it('studio moves the live instruments into a reserved side column', () => {
    const r = layoutRegions('studio', 160)

    expect(r.sideActive).toBe(true)
    expect(r.sideWidth).toBeGreaterThanOrEqual(32)
    // They render in the side pane now — mounting them twice would double the
    // live-agent polling and print two todo lists.
    expect(r.agentsDock).toBe(false)
    expect(r.todoUnderPrompt).toBe(false)
  })

  it('falls back to the composer placement when a side column cannot fit', () => {
    const r = layoutRegions('studio', STUDIO_MIN_COLS - 1)

    expect(r.sideWidth).toBe(0)
    expect(r.sideActive).toBe(false)
    expect(r.agentsDock).toBe(true)
    expect(r.todoUnderPrompt).toBe(true)
  })

  it('degrades to a single column on phone hosts', () => {
    // Phone PTYs are too narrow to afford panes and reserved rails — they must
    // fall back, not fight the terminal.
    const r = layoutRegions('studio', 160, { singleColumn: true })

    expect(r.sideActive).toBe(false)
    expect(r.rails).toBe(false)
    expect(r.agentsDock).toBe(true)
    expect(r.todoUnderPrompt).toBe(true)
  })

  it('never lets the side column starve or swallow the transcript', () => {
    expect(studioSideWidth(0)).toBe(0)
    expect(studioSideWidth(STUDIO_MIN_COLS)).toBeGreaterThanOrEqual(32)
    expect(studioSideWidth(400)).toBeLessThanOrEqual(48)
  })

  it('resolves regions for every declared layout at every width', () => {
    for (const id of LAYOUT_IDS) {
      for (const cols of [0, 60, 100, 400]) {
        const r = layoutRegions(id, cols)

        expect(r.sideWidth).toBe(r.sideActive ? r.sideWidth : 0)
        expect(r.sideWidth).toBeLessThan(cols || 1)
        expect(LAYOUT_SPECS[id]).toBeDefined()
      }
    }
  })

  it('timeline mounts the step ledger and keeps instruments in the flow', () => {
    const r = layoutRegions('timeline', 120)

    expect(r.ledger).toBe(true)
    // The ledger IS the instrument surface here; the agents dock would double
    // the same information.
    expect(r.agentsDock).toBe(false)
    expect(r.rails).toBe(false)
    expect(r.pet).toBe(false)
    expect(r.sideActive).toBe(false)
    expect(r.statusRule).toBe(true)
  })

  it('drops the ledger when the host cannot afford a persistent block', () => {
    // Phone PTYs / inline mode: the ledger's steps fall back to the agents
    // dock rather than eating rows the terminal does not have.
    const r = layoutRegions('timeline', 160, { singleColumn: true })

    expect(r.ledger).toBe(false)
    expect(r.agentsDock).toBe(true)
  })
})

describe('layout progress defaults', () => {
  it('workbench pins the built-in defaults, so existing users see no change', () => {
    // The compatibility guard: workbench's progress profile must stay exactly
    // the built-in SECTION_DEFAULTS (thinking/tools live — open during the
    // turn, folded once settled — activity hidden, subagents falling through
    // to the global mode).
    expect(layoutSections('workbench')).toEqual({
      activity: 'hidden',
      thinking: 'live',
      tools: 'live'
    })
  })

  it('each layout leads with a different amount of progress', () => {
    // A design that only moved panels would produce identical profiles.
    const shapes = LAYOUT_IDS.map(id => JSON.stringify(layoutSections(id)))

    expect(new Set(shapes).size).toBe(LAYOUT_IDS.length)
    expect(layoutSections('minimal').thinking).toBe('collapsed')
    expect(layoutSections('timeline').tools).toBe('live')
    expect(layoutSections('studio').subagents).toBe('live')
  })

  it('layers under the user, never over them', () => {
    const minimal = layoutSections('minimal')

    // The layout applies when the user has said nothing.
    expect(sectionMode('thinking', 'collapsed', undefined, false, minimal)).toBe('collapsed')
    // An explicit display.sections.* win.
    expect(sectionMode('thinking', 'collapsed', { thinking: 'expanded' }, false, minimal)).toBe('expanded')
    // So does an in-session /details.
    expect(sectionMode('thinking', 'expanded', undefined, true, minimal)).toBe('expanded')
  })

  it('never makes a settled turn paint its trail', () => {
    // If the layout's defaults reached detailsRequested(), every layout except
    // workbench would resurrect the chevron rows under past messages — the
    // exact clutter the settled-turn suppression exists to remove. Consumers
    // pass the USER's sections, so a populated profile must stay inert.
    expect(detailsRequested(undefined, false)).toBe(false)
    expect(detailsRequested({}, false)).toBe(false)
  })
})
