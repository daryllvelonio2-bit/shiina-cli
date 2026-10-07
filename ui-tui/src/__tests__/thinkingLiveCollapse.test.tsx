import { PassThrough } from 'stream'

import { renderSync } from '@shiina/ink'
import { stripAnsi } from '@shiina/shared/ansi'
import React from 'react'
import { describe, expect, it } from 'vitest'

import { ToolTrail } from '../components/thinking.js'
import { DEFAULT_THEME } from '../theme.js'

const flushEffects = async () => {
  // Passive effects + the re-render they trigger need a few macrotask
  // turns (React's scheduler uses MessageChannel) before the next frame
  // paints — setTimeout(0)-class waits, not setImmediate (which can land
  // in the wrong phase and observe the pre-effect frame).
  for (let i = 0; i < 10; i++) {
    await new Promise(resolve => setTimeout(resolve, 5))
  }
}

const mountTrail = (reasoningActive: boolean, sections?: Record<string, string>) => {
  const stdout = new PassThrough()
  const stdin = new PassThrough()
  const stderr = new PassThrough()
  let output = ''

  Object.assign(stdout, { columns: 60, isTTY: false, rows: 20 })
  Object.assign(stdin, { isTTY: false })
  Object.assign(stderr, { isTTY: false })
  stdout.on('data', chunk => {
    output += chunk.toString()
  })

  const instance = renderSync(
    <ToolTrail
      reasoning="Parsing the widget sample."
      reasoningActive={reasoningActive}
      sections={sections ?? { thinking: 'collapsed' }}
      t={DEFAULT_THEME}
    />,
    {
      patchConsole: false,
      stderr: stderr as NodeJS.WriteStream,
      stdin: stdin as NodeJS.ReadStream,
      stdout: stdout as NodeJS.WriteStream
    }
  )

  // The codex header renders no chevron (marker: none), so the real
  // open/closed signal is whether the panel BODY (reasoning text) survives
  // in the latest repaint's tail — a collapsed repaint rewrites that region
  // without the body.
  const bodyVisible = () => stripAnsi(output).slice(-240).includes('Parsing the widget')

  // For rerender transitions: measure only the repaints after a mark, since
  // the accumulated stream keeps earlier frames' body text forever.
  const mark = () => output.length
  const since = (m: number) => output.slice(m)

  return { bodyVisible, instance, mark, since }
}

describe('ToolTrail — collapsed mode auto-expands while reasoning is live', () => {
  it('opens when reasoningActive is true under sections.thinking: collapsed', async () => {
    const { bodyVisible, instance } = mountTrail(true)

    await flushEffects()

    expect(bodyVisible()).toBe(true)

    instance.unmount()
    instance.cleanup()
  })

  it('collapses when reasoningActive is false under sections.thinking: collapsed', async () => {
    const { bodyVisible, instance } = mountTrail(false)

    await flushEffects()

    expect(bodyVisible()).toBe(false)

    instance.unmount()
    instance.cleanup()
  })

  it('closes the panel when the reasoning phase ends mid-turn (rerender)', async () => {
    const { bodyVisible, instance, mark, since } = mountTrail(true)

    await flushEffects()

    expect(bodyVisible()).toBe(true)

    // Reasoning phase finished (final answer / tool call started) — the
    // turn's reasoningActive drops and the panel must collapse. Measure
    // only the post-rerender repaint (the accumulated stream keeps the
    // earlier open frame's body text forever).
    const m = mark()
    instance.rerender(
      <ToolTrail
        reasoning="Parsing the widget sample."
        reasoningActive={false}
        sections={{ thinking: 'collapsed' }}
        t={DEFAULT_THEME}
      />
    )

    await flushEffects()

    const post = since(m)

    // The close repaint must have occurred, and it must not re-emit the body.
    // The final painted frame (sync-output delimited) must be collapsed —
    // the render-phase repaint before the collapse effect still shows the
    // body, so only the LAST frame is authoritative.
    expect(post.length).toBeGreaterThan(0)
    const frames = post.split('\u001b[?2026h')
    const lastFrame = stripAnsi(frames[frames.length - 1] ?? '')
    expect(lastFrame.includes('Parsing the widget')).toBe(false)

    instance.unmount()
    instance.cleanup()
  })

  it('leaves expanded-mode panels fully manual (no forced collapse)', async () => {
    const { bodyVisible, instance } = mountTrail(false, { thinking: 'expanded' })

    await flushEffects()

    // `expanded` is a manual preference: reasoningActive=false must NOT
    // force it closed (the auto behavior only applies to `collapsed`).
    expect(bodyVisible()).toBe(true)

    instance.unmount()
    instance.cleanup()
  })
})
