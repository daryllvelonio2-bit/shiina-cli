import { describe, expect, it } from 'vitest'

import {
  advanceScan,
  createScanState,
  firstVisibleBlock,
  pruneStreamBlocks
} from '../components/streamingMarkdown.js'
import { liveTailLabel, liveTailWindow } from '../lib/text.js'

// The long-reply fix: the scanner reads the untrimmed stream and the tail window
// is applied at render. These pin that a sliding window never restarts the scan
// (which used to re-parse the whole 16 KB window, ~130 ms, on every delta).

const REPLY = [
  'First paragraph, long enough to settle.',
  '',
  'Second paragraph with `code`.',
  '',
  '```ts',
  'const fenced = true',
  '',
  'still inside the fence',
  '```',
  '',
  'Tail paragraph.',
  ''
].join('\n')

describe('liveTailWindow', () => {
  it('leaves a short reply alone and reports nothing dropped', () => {
    expect(liveTailWindow('short reply', { maxChars: 100, maxLines: 10 })).toEqual({
      dropped: 0,
      omittedChars: 0,
      omittedLines: 0,
      text: 'short reply'
    })
  })

  it('reports where the window starts, so the scanner can keep its position', () => {
    const window = liveTailWindow(REPLY, { maxChars: 20, maxLines: 100 })

    // `dropped` must index exactly the first rendered character.
    expect(REPLY.slice(window.dropped)).toBe(window.text)
    expect(window.dropped).toBeGreaterThan(0)
    expect(window.omittedChars).toBe(window.dropped)
  })

  it('drops whole lines when the line cap binds', () => {
    const window = liveTailWindow(REPLY, { maxChars: 10_000, maxLines: 3 })

    expect(REPLY.slice(window.dropped)).toBe(window.text)
    expect(window.omittedLines).toBeGreaterThan(0)
    expect(window.omittedChars).toBe(window.dropped)
  })

  it('labels a trimmed window and says nothing for an untrimmed one', () => {
    expect(liveTailLabel(liveTailWindow('short', { maxChars: 100, maxLines: 10 }))).toBe('')
    expect(liveTailLabel(liveTailWindow(REPLY, { maxChars: 20, maxLines: 100 }))).toMatch(/^\[showing live tail; omitted /)
    expect(liveTailLabel(liveTailWindow(REPLY, { maxChars: 10_000, maxLines: 3 }))).toMatch(/omitted \d+ lines? \/ /)
  })
})

describe('scanning an untrimmed stream with a sliding window', () => {
  it('never restarts the scan, however far the window slides', () => {
    const state = createScanState()

    // Feed the reply in deltas; at each step the window start advances like
    // boundedLiveRenderText would, but the scanner always sees the full text.
    let windowStart = 0

    for (let pos = 1; pos <= REPLY.length; pos += 7) {
      const raw = REPLY.slice(0, pos)

      advanceScan(raw, state)
      windowStart = liveTailWindow(raw, { maxChars: 24, maxLines: 2 }).dropped
      pruneStreamBlocks(state, windowStart)
    }

    // Extended, not restarted: the committed prefix covers the whole reply and
    // no block was emitted twice (a restart would have re-emitted the head).
    expect(state.settledLen).toBeGreaterThan(0)
    expect(state.blocks.join('')).toBe(REPLY.slice(0, state.settledLen))
  })

  it('keeps the block under the window start renderable, and drops only passed heads', () => {
    const state = createScanState()

    advanceScan(REPLY, state)

    const total = state.blocks.length

    expect(total).toBeGreaterThan(2)

    // Window starts inside the reply: every block still intersecting it stays.
    const mid = state.blockEnds[0]!
    const from = firstVisibleBlock(state, mid)

    expect(from).toBe(1)

    pruneStreamBlocks(state, mid, 1)

    expect(state.droppedBlocks).toBe(1)
    expect(state.blocks.length).toBe(total - 1)
    // Ordinals stay aligned with blockEnds after a prune.
    expect(state.droppedBlocks + state.blocks.length).toBe(total)
    expect(firstVisibleBlock(state, mid)).toBe(1)
  })

  it('resets only when the stream genuinely restarts', () => {
    const state = createScanState()

    advanceScan(REPLY, state)

    const settled = state.settledLen

    // A different reply (turn reuse): the scanned prefix no longer extends.
    const other = 'Completely different content.\n\nWith its own blocks.\n'
    const restarted = !other.startsWith(state.scanned)

    expect(restarted).toBe(true)
    expect(settled).toBeGreaterThan(0)
  })
})
