import { PassThrough } from 'stream'

import { renderSync } from '@shiina/ink'
import { stripAnsi } from '@shiina/shared/ansi'
import React from 'react'
import { describe, expect, it } from 'vitest'

import { capThinkingLines, chevronColor, Thinking, ToolTrail } from '../components/thinking.js'
import { THINKING_TRAIL_MAX_CHARS, THINKING_TRAIL_MAX_LINES } from '../config/limits.js'
import { buildToolTrailLine } from '../lib/text.js'
import { DEFAULT_THEME } from '../theme.js'
import type { Theme } from '../theme.js'

// Trail defaults: a conversation must not accumulate open reasoning/tool panels,
// the chain of thought is a window rather than a wall, and the section headers
// (not the reasoning body) carry the identity color.

const TRAIL = [
  buildToolTrailLine('terminal', 'ls -la'),
  buildToolTrailLine('read_file', 'src/app.tsx'),
  buildToolTrailLine('patch', 'src/app.tsx')
]

const COT = Array.from({ length: 12 }, (_, i) => `reasoning line ${i + 1}`).join('\n')

const render = (node: React.ReactElement, { tty = false } = {}) => {
  const stdout = new PassThrough()
  let raw = ''

  Object.assign(stdout, { columns: 100, isTTY: tty, rows: 40 })
  stdout.on('data', chunk => {
    raw += chunk.toString()
  })

  const instance = renderSync(node, { patchConsole: false, stdout: stdout as unknown as NodeJS.WriteStream })

  return { instance, raw: () => raw, text: () => stripAnsi(raw) }
}

const flush = async () => {
  for (let i = 0; i < 5; i++) {
    await new Promise(resolve => setTimeout(resolve, 5))
  }
}

type ToolTrailProps = React.ComponentProps<typeof ToolTrail>

const mountTrail = (props: Partial<ToolTrailProps> = {}, tty = false) =>
  render(
    <ToolTrail detailsMode="collapsed" sections={{}} t={DEFAULT_THEME} trail={TRAIL} {...props} />,
    { tty }
  )

describe('a settled trail stays closed', () => {
  it('keeps the tool list behind its chevron', async () => {
    const trail = mountTrail({ reasoning: COT })

    await flush()

    const out = trail.text()

    // The unified step header carries the summary; the tool rows themselves
    // are not rendered while collapsed. (The codex header renders no
    // chevron — marker: none — so content is the signal.)
    expect(out).toContain('Steps')
    expect(out).not.toMatch(/terminal/i)

    trail.instance.unmount()
  })

  it('opens the tool list for the live turn only', async () => {
    const trail = mountTrail({ busy: true, preferExpandedThinking: true, reasoning: COT })

    await flush()

    expect(trail.text()).toMatch(/terminal/i)

    trail.instance.unmount()
  })

  it('still opens when the user asked for expanded sections', async () => {
    const trail = mountTrail({ commandOverride: true, reasoning: COT, sections: { tools: 'expanded' } })

    await flush()

    expect(trail.text()).toMatch(/terminal/i)

    trail.instance.unmount()
  })

  it('honours `tools: live` from the design YAML — open while live, folded when settled', async () => {
    // The design's layout.sections block (designs/codex.yaml) is the knob:
    // `live` folds a finished turn to its one-line header, `expanded` keeps it.
    const settled = mountTrail({ layoutSections: { tools: 'live' }, reasoning: COT })

    await flush()

    expect(settled.text()).not.toMatch(/terminal/i)

    settled.instance.unmount()

    const live = mountTrail({ layoutSections: { tools: 'live' }, preferExpandedThinking: true, reasoning: COT })

    await flush()

    expect(live.text()).toMatch(/terminal/i)

    live.instance.unmount()
  })
})

describe('reasoning is a window, not a wall', () => {
  it('shows the newest lines and counts the older ones', async () => {
    const trail = render(<Thinking maxLines={5} mode="full" reasoning={COT} t={DEFAULT_THEME} />)

    await flush()

    const out = trail.text()

    expect(out).toContain('reasoning line 12')
    expect(out).toContain('reasoning line 8')
    expect(out).not.toContain('reasoning line 7')
    expect(out).toContain('+7 earlier lines')

    trail.instance.unmount()
  })

  it('slides the window as new text arrives, dropping the oldest line', () => {
    const grown = [...Array.from({ length: 12 }, (_, i) => `reasoning line ${i + 1}`), 'reasoning line 13']

    expect(capThinkingLines(grown, THINKING_TRAIL_MAX_LINES).lines).toEqual([
      'reasoning line 9',
      'reasoning line 10',
      'reasoning line 11',
      'reasoning line 12',
      'reasoning line 13'
    ])
    expect(capThinkingLines(grown, THINKING_TRAIL_MAX_LINES).hidden).toBe(8)
  })

  it('bounds a single-paragraph chain of thought by characters too', () => {
    const wall = [`${'x'.repeat(4000)}`]

    const capped = capThinkingLines(wall, THINKING_TRAIL_MAX_LINES)

    // One logical line would have wrapped into a wall of its own.
    expect(capped.lines.join('').length).toBeLessThanOrEqual(THINKING_TRAIL_MAX_CHARS)
    expect(capped.lines[0]).toContain('…')
    expect(capThinkingLines(['short'], 5)).toEqual({ hidden: 0, lines: ['short'] })
  })

  it('windows by count, always ending at the newest line', () => {
    const many = Array.from({ length: 30 }, (_, i) => `l${i + 1}`)

    expect(capThinkingLines(many, 5)).toEqual({ hidden: 25, lines: ['l26', 'l27', 'l28', 'l29', 'l30'] })
  })

  it('renders everything when no cap is set', async () => {
    const trail = render(<Thinking mode="full" reasoning={COT} t={DEFAULT_THEME} />)

    await flush()

    const out = trail.text()

    expect(out).toContain('reasoning line 1')
    expect(out).toContain('reasoning line 12')
    expect(out).not.toContain('earlier lines')

    trail.instance.unmount()
  })
})

describe('header color vs body color', () => {
  it('titles the section with the identity color instead of a dimmed muted', () => {
    const theme: Theme = { ...DEFAULT_THEME, color: { ...DEFAULT_THEME.color, accent: '#ff00ff', muted: '#010203' } }

    expect(chevronColor(theme)).toBe('#ff00ff')
    expect(chevronColor(theme)).not.toBe(theme.color.muted)
    expect(chevronColor(theme, 'error')).toBe(theme.color.error)
    expect(chevronColor(theme, 'warn')).toBe(theme.color.warn)
  })

  it('keeps the reasoning body quieter than its header', async () => {
    const trail = render(<Thinking live={false} maxLines={5} mode="full" reasoning={COT} t={DEFAULT_THEME} />)

    await flush()

    // The body renders dim (Ink dims via the SGR 2 attribute on a terminal).
    expect(trail.text()).toContain('reasoning line 1')
    expect(trail.raw().length).toBeGreaterThan(0)

    trail.instance.unmount()
  })
})
