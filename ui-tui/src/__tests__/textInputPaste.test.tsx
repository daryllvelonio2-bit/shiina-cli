import { EventEmitter } from 'node:events'
import { PassThrough } from 'node:stream'

import { renderSync } from '@shiina/ink'
import React, { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { TextInput } from '../components/textInput.js'
import type { PasteEvent } from '../components/textInput.js'

// The TUI pushes the kitty keyboard protocol (ENABLE_KITTY_KEYBOARD in the ink
// fork), so chords arrive as CSI-u sequences — Ctrl+V as ESC[118;5u, not the
// legacy 0x16 byte — and the clipboard chords must match on the decoded key.
// Ctrl+V pastes the clipboard image; Ctrl+Shift+V (and Alt+V) paste text.

class FakeInput extends EventEmitter {
  chunks: string[] = []
  isRaw = false
  isTTY = true
  readableLength = 0

  read() {
    const next = this.chunks.shift() ?? null

    this.readableLength = this.chunks.length

    return next
  }

  ref = vi.fn()

  send(...chunks: string[]) {
    this.chunks.push(...chunks)
    this.readableLength = this.chunks.length
    this.emit('readable')
  }

  setEncoding = vi.fn()

  setRawMode = vi.fn((enabled: boolean) => {
    this.isRaw = enabled
  })

  unref = vi.fn()
}

const settle = (ms = 25) => new Promise(resolve => setTimeout(resolve, ms))

const mount = (onPaste: (e: PasteEvent) => { cursor: number; value: string } | null) => {
  const stdin = new FakeInput()
  const stdout = new PassThrough()
  const stderr = new PassThrough()

  Object.assign(stdout, { columns: 80, isTTY: false, rows: 24 })
  Object.assign(stderr, { columns: 80, isTTY: false, rows: 24 })

  const changes: string[] = []

  function Harness() {
    const [value, setValue] = useState('')

    return (
      <TextInput
        columns={80}
        onChange={next => {
          changes.push(next)
          setValue(next)
        }}
        onPaste={onPaste}
        onSubmit={() => {}}
        value={value}
      />
    )
  }

  const instance = renderSync(React.createElement(Harness), {
    patchConsole: false,
    stderr: stderr as NodeJS.WriteStream,
    stdin: stdin as unknown as NodeJS.ReadStream,
    stdout: stdout as NodeJS.WriteStream
  })

  return { changes, instance, stdin }
}

describe('clipboard chords under the kitty keyboard protocol', () => {
  it('treats Ctrl+V (CSI-u) as an image paste', async () => {
    const events: PasteEvent[] = []
    const { instance, stdin } = mount(e => {
      events.push(e)

      return null
    })

    await settle()

    // kitty CSI-u: codepoint 118 ('v'), modifier 5 = 1 + ctrl bit 4.
    stdin.send('\u001b[118;5u')
    await settle()

    instance.unmount()
    instance.cleanup()

    expect(events).toHaveLength(1)
    expect(events[0]).toMatchObject({ hotkey: true, image: true })
  })

  it('treats Ctrl+Shift+V (CSI-u) as a text paste', async () => {
    const events: PasteEvent[] = []
    const { instance, stdin } = mount(e => {
      events.push(e)

      return null
    })

    await settle()

    // modifier 6 = 1 + ctrl 4 + shift 1.
    stdin.send('\u001b[118;6u')
    await settle()

    instance.unmount()
    instance.cleanup()

    expect(events).toHaveLength(1)
    expect(events[0]).toMatchObject({ hotkey: true, image: false })
  })

  it('still honours the legacy bytes and Alt+V', async () => {
    const events: PasteEvent[] = []
    const { instance, stdin } = mount(e => {
      events.push(e)

      return null
    })

    await settle()

    stdin.send('\u0016')
    await settle()
    stdin.send('\u001bv')
    await settle()

    instance.unmount()
    instance.cleanup()

    expect(events).toHaveLength(2)
    expect(events[0]).toMatchObject({ hotkey: true, image: true })
    expect(events[1]).toMatchObject({ hotkey: true, image: false })
  })

  it('inserts a bracketed paste — how a terminal-native paste arrives', async () => {
    const events: PasteEvent[] = []
    const { changes, instance, stdin } = mount(e => {
      events.push(e)

      return { cursor: e.cursor + e.text.length, value: e.value + e.text }
    })

    await settle()

    stdin.send('\u001b[200~hello from the clipboard\u001b[201~')
    await settle()

    instance.unmount()
    instance.cleanup()

    expect(events[0]).toMatchObject({ bracketed: true, text: 'hello from the clipboard' })
    expect(changes.at(-1)).toBe('hello from the clipboard')
  })
})
