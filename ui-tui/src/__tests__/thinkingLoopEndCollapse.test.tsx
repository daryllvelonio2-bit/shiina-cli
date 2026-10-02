import { PassThrough } from 'stream'

import { renderSync } from '@shiina/ink'
import { stripAnsi } from '@shiina/shared/ansi'
import React from 'react'
import { describe, expect, it } from 'vitest'

import { ToolTrail } from '../components/thinking.js'
import { DEFAULT_THEME } from '../theme.js'

/**
 * Loop-end hygiene: when the turn finishes, the panel must read as one compact
 * summary — every auto section closed — while a section the user pinned open via
 * /details stays open.
 */

const flushEffects = async () => {
  for (let i = 0; i < 10; i++) {
    await new Promise(resolve => setTimeout(resolve, 5))
  }
}

const mountTrail = (props: { busy: boolean; reasoningActive?: boolean; sections?: Record<string, string> }) => {
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

  const node = (p: typeof props) => (
    <ToolTrail
      busy={p.busy}
      reasoning="Live reasoning text."
      reasoningActive={p.reasoningActive ?? false}
      sections={p.sections ?? { thinking: 'collapsed' }}
      t={DEFAULT_THEME}
    />
  )

  const instance = renderSync(node(props), {
    patchConsole: false,
    stderr: stderr as unknown as NodeJS.WriteStream,
    stdin: stdin as unknown as NodeJS.ReadStream,
    stdout: stdout as unknown as NodeJS.WriteStream
  })

  const finalChevronOpen = () => stripAnsi(output).lastIndexOf('▾ ') > stripAnsi(output).lastIndexOf('▸ ')

  return { finalChevronOpen, instance, node }
}

describe('ToolTrail — the loop finishing collapses every section', () => {
  it('collapses an auto thinking section when busy falls', async () => {
    const { finalChevronOpen, instance, node } = mountTrail({ busy: true, reasoningActive: true })

    await flushEffects()

    expect(finalChevronOpen()).toBe(true)

    instance.rerender(node({ busy: false, reasoningActive: false }))

    await flushEffects()

    expect(finalChevronOpen()).toBe(false)

    instance.unmount()
    instance.cleanup()
  })

  it('leaves a section the user pinned expanded via /details alone', async () => {
    const pinned = { thinking: 'expanded' }
    const { finalChevronOpen, instance, node } = mountTrail({ busy: true, sections: pinned })

    await flushEffects()

    expect(finalChevronOpen()).toBe(true)

    instance.rerender(node({ busy: false, sections: pinned }))

    await flushEffects()

    expect(finalChevronOpen()).toBe(true)

    instance.unmount()
    instance.cleanup()
  })
})
