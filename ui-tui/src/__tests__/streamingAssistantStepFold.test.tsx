import { PassThrough } from 'stream'

import { renderSync } from '@shiina/ink'
import { stripAnsi } from '@shiina/shared/ansi'
import React from 'react'
import { beforeEach, describe, expect, it } from 'vitest'

import { patchTurnState } from '../app/turnStore.js'
import { StreamingAssistant } from '../components/streamingAssistant.js'

const OLDER_THOUGHT = 'OLDER_BODY'
const NEWEST_THOUGHT = 'NEWEST_BODY'
const MID_TEXT = 'MID_TEXT'

const render = (): string => {
  const stdout = new PassThrough()
  const stdin = new PassThrough()
  const stderr = new PassThrough()
  let output = ''

  Object.assign(stdout, { columns: 100, isTTY: false, rows: 40 })
  Object.assign(stdin, { isTTY: false })
  Object.assign(stderr, { isTTY: false })
  stdout.on('data', (chunk: Buffer) => {
    output += chunk.toString()
  })

  const instance = renderSync(
    React.createElement(StreamingAssistant, {
      cols: 100,
      detailsMode: 'collapsed' as const,
      progress: { showProgressArea: true },
      sections: {}
    }),
    {
      patchConsole: false,
      stderr: stderr as NodeJS.WriteStream,
      stdin: stdin as NodeJS.ReadStream,
      stdout: stdout as NodeJS.WriteStream
    }
  )

  instance.unmount()
  instance.cleanup()
  return stripAnsi(output)
}

describe('StreamingAssistant step folding', () => {
  beforeEach(() => {
    patchTurnState({ streamPendingTools: [], streamSegments: [], streaming: '', tools: [] })
  })

  // The live flag is what holds a `live`-mode section open. Passing it to every
  // live block left each finished step expanded until the whole turn settled —
  // one open block per step, stacked. Only the newest block may be live, so a
  // step folds to its one-line header as soon as the next one appears.
  it('keeps only the newest live block open and folds the steps before it', () => {
    patchTurnState({
      streamSegments: [
        { kind: 'trail', role: 'system', text: '', thinking: OLDER_THOUGHT },
        { role: 'assistant', text: MID_TEXT },
        { kind: 'trail', role: 'system', text: '', thinking: NEWEST_THOUGHT }
      ]
    })

    const output = render()

    expect(output).not.toContain(OLDER_THOUGHT)
    expect(output).toContain(NEWEST_THOUGHT)
    expect(output).toContain(MID_TEXT)
  })
})
