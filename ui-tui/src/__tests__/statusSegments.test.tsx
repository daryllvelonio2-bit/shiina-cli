import { PassThrough } from 'stream'

import { renderSync } from '@shiina/ink'
import { stripAnsi } from '@shiina/shared/ansi'
import React from 'react'
import { describe, expect, it } from 'vitest'

import { StatusRule } from '../components/appChrome.js'
import { STATUS_SEGMENT_IDS, STATUS_SEGMENTS, resolveStatusSegments } from '../components/statusSegments.js'
import { DEFAULT_DESIGN, resolveDesign } from '../design.js'
import { DEFAULT_THEME } from '../theme.js'

// `StatusRuleProps` is module-private; derive it so the fixture cannot drift
// from the component's real contract.
type StatusRuleProps = React.ComponentProps<typeof StatusRule>

const mountRule = (props: StatusRuleProps) => {
  const stdout = new PassThrough()
  const stdin = new PassThrough()
  const stderr = new PassThrough()
  let output = ''

  Object.assign(stdout, { columns: 200, isTTY: false, rows: 40 })
  Object.assign(stdin, { isTTY: false })
  Object.assign(stderr, { isTTY: false })
  stdout.on('data', chunk => {
    output += chunk.toString()
  })

  const instance = renderSync(<StatusRule {...props} />, {
    patchConsole: false,
    stderr: stderr as unknown as NodeJS.WriteStream,
    stdin: stdin as unknown as NodeJS.ReadStream,
    stdout: stdout as unknown as NodeJS.WriteStream
  })

  return { cleanup: () => instance.unmount(), text: () => stripAnsi(output) }
}

/** Ink writes frames on the next tick — let the tree paint before reading. */
const flush = async () => {
  for (let i = 0; i < 5; i++) {
    await new Promise(resolve => setTimeout(resolve, 5))
  }
}

const props = (overrides: Partial<StatusRuleProps> = {}): StatusRuleProps => ({
  bgCount: 2,
  busy: false,
  cols: 200,
  cwdLabel: '~/repo',
  lastTurnEndedAt: null,
  liveSessionCount: 0,
  model: 'opus-4.8',
  sessionStartedAt: Date.now() - 60_000,
  status: 'ready',
  statusColor: DEFAULT_THEME.color.ok,
  t: DEFAULT_THEME,
  turnStartedAt: null,
  usage: { active_subagents: 0, context_max: 200_000, context_percent: 25, context_used: 50_000, total: 50_000 },
  voiceLabel: '',
  ...overrides
})

describe('status segment registry', () => {
  it('has stable, unique ids in render order', () => {
    expect(new Set(STATUS_SEGMENT_IDS).size).toBe(STATUS_SEGMENT_IDS.length)
    // Order IS drop priority: the low-value readouts must stay at the tail.
    expect(STATUS_SEGMENT_IDS.indexOf('bg')).toBeLessThan(STATUS_SEGMENT_IDS.indexOf('dev_credits'))
    expect(STATUS_SEGMENT_IDS[0]).toBe('focus')
  })

  it('declares the config gates on the segment instead of the render loop', () => {
    for (const spec of STATUS_SEGMENTS) {
      // A segment either carries a `display.status_bar.fields` name or is
      // deliberately unGated; nothing may be added without stating which.
      expect(typeof spec.field === 'string' || spec.field === null).toBe(true)
      expect(spec.id).toMatch(/^[a-z][a-z0-9_]*$/)
    }

    expect(STATUS_SEGMENTS.find(s => s.id === 'cache_hit')?.field).toBe('cache_hit')
    expect(STATUS_SEGMENTS.find(s => s.id === 'bg')?.segsKey).toBe('bg')
  })

  it('keeps the built-in order when the skin does not configure one', () => {
    expect(resolveStatusSegments(undefined).map(s => s.id)).toEqual(STATUS_SEGMENT_IDS)
    expect(resolveStatusSegments(DEFAULT_DESIGN).map(s => s.id)).toEqual(STATUS_SEGMENT_IDS)
  })

  it('applies a skin order and drops ids this build does not know', () => {
    const design = resolveDesign({ status_bar: { segments: ['bg', 'from_the_future', 'voice'] } })

    expect(resolveStatusSegments(design).map(s => s.id)).toEqual(['bg', 'voice'])
  })

  it('falls back to the built-in order when a skin names only unknown ids', () => {
    expect(resolveStatusSegments(resolveDesign({ status_bar: { segments: ['nope'] } })).map(s => s.id)).toEqual(
      STATUS_SEGMENT_IDS
    )
  })
})

describe('StatusRule honours the segment tokens', () => {
  it('renders the configured segments only', async () => {
    const t = { ...DEFAULT_THEME, design: resolveDesign({ status_bar: { segments: ['bg'] } }) }
    const rule = mountRule(props({ t }))

    await flush()

    expect(rule.text()).toContain('2 bg')
    rule.cleanup()
  })

  it('hides a segment the skin leaves out of the list', async () => {
    const t = { ...DEFAULT_THEME, design: resolveDesign({ status_bar: { segments: ['bg'] } }) }
    // A live session count would normally show; the allowlist drops it.
    const rule = mountRule(props({ liveSessionCount: 3, t }))

    await flush()

    expect(rule.text()).toContain('2 bg')
    expect(rule.text()).not.toContain('3 sessions')
    rule.cleanup()
  })

  it('renders the separator and idle glyphs from the design tokens', async () => {
    const t = {
      ...DEFAULT_THEME,
      design: resolveDesign({ glyphs: { idle: '√', separator: ' :: ' } })
    }
    const rule = mountRule(props({ lastTurnEndedAt: 999_000, t }))

    await flush()

    expect(rule.text()).toContain(' :: ')
    expect(rule.text()).toContain('√')
    rule.cleanup()
  })

  it('keeps the built-in chrome when a skin ships no tokens', async () => {
    const rule = mountRule(props())

    await flush()

    expect(rule.text()).toContain(DEFAULT_THEME.design.glyphs.separator)
    expect(rule.text()).toContain('2 bg')
    rule.cleanup()
  })
})
