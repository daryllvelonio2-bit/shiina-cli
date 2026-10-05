/**
 * Structural layout contract: `display.layout` selects one of three region
 * tables, and the resolver must stay total (a typo can never blank the TUI)
 * while keeping the three arrangements genuinely distinct.
 */
import { describe, expect, it } from 'vitest'

import {
  cycleLayout,
  DEFAULT_LAYOUT,
  LAYOUT_IDS,
  LAYOUT_SPECS,
  layoutRegions,
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

    let id = LAYOUT_IDS[0]

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

  it('degrades to a single column on inline / phone hosts', () => {
    // INLINE_MODE writes into the host's native scrollback and phone PTYs are
    // too narrow for panes — both must fall back, not fight the terminal.
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
})
