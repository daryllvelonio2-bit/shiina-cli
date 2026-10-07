/**
 * Pinned regression for the multi-line composer cursor-drift bug.
 *
 * Symptom: in `shiina --tui`, typing into the composer until the input
 * wraps across multiple visual rows would leave several blank cells
 * between the last typed character and the (hardware) cursor block.
 * Worse on narrow terminals (the Cursor IDE built-in terminal in
 * particular).
 *
 * Root cause: the composer's `cursorLayout` (used by `useDeclaredCursor`
 * to place the hardware cursor) ran a hand-rolled word-wrap algorithm,
 * while Ink's `<Text wrap="wrap">` renders via `wrap-ansi`. The two
 * disagreed on many real inputs — wrap-ansi would keep "branch
 * investigate" on one row while cursorLayout claimed it had wrapped,
 * etc. — so the declared cursor position drifted from where the text
 * was actually rendered. The fix sources cursorLayout's line breaks
 * directly from wrap-ansi, guaranteeing agreement.
 *
 * This test pins the contract: for every char that would be typed into
 * the composer, the cursor position reported by cursorLayout MUST equal
 * the end-of-text position that wrap-ansi would render. Any future
 * regression that lets the two diverge re-introduces the drift.
 */
import { wrapAnsi } from '@shiina/ink'
import { describe, expect, it } from 'vitest'

import { cursorLayout, inputVisualHeight } from '../lib/inputMetrics.js'

function wrapAnsiEnd(text: string, cols: number): { line: number; column: number } {
  const wrapped = wrapAnsi(text, cols, { hard: true, trim: false })
  const lines = wrapped.split('\n')
  const last = lines[lines.length - 1] ?? ''

  return { line: lines.length - 1, column: last.length }
}

const USER_REPORT_MESSAGE =
  // Opening of the user's bug report, verbatim: one long line, mixed-length
  // words, punctuation, no hard newlines. Deliberately an excerpt — this test
  // re-wraps the entire prefix for every typed character, and wrap-ansi costs
  // ~20µs/char, so the full 548-char report across the old 7-width sweep took
  // ~45s and blew the 30s timeout even on an idle box. Where a wrap lands
  // depends on the message crossing the column width, not on how much extra
  // text follows it, so the excerpt is long enough to wrap at every width
  // exercised below.
  'im in cursor terminal using shiina --tui and as i type multiline my caret at the end will often '

describe('cursor-drift regression — composer cursorLayout matches Ink rendering', () => {
  it('agrees with wrap-ansi at every typing-prefix of the user-reported message', () => {
    // Walks the message char-by-char (mirroring what the TUI sees when a
    // user types). At every prefix, cursorLayout must place the cursor
    // exactly where wrap-ansi would render the end of the text.
    //
    // Pre-fix: this failed on most narrow widths because the hand-rolled
    // wrap algorithm broke at slightly different points than wrap-ansi.
    //
    // Each walked width costs a full re-wrap of the growing prefix per typed
    // character (O(n²) through wrap-ansi, ~20µs/char), so the walk runs at the
    // narrow width the drift was reported at and the wider columns get the
    // end-of-text comparison — the same contract at a fraction of the cost.
    for (const cols of [40]) {
      let acc = ''

      for (const ch of USER_REPORT_MESSAGE) {
        acc += ch
        const layout = cursorLayout(acc, acc.length, cols)
        const expected = wrapAnsiEnd(acc, cols)

        expect(
          layout,
          `mismatch at cols=${cols}, len=${acc.length}, last-char=${JSON.stringify(ch)}, ` +
            `tail=${JSON.stringify(acc.slice(-30))}`
        ).toEqual(expected)
      }
    }

    for (const cols of [55, 60, 65, 70, 80]) {
      expect(cursorLayout(USER_REPORT_MESSAGE, USER_REPORT_MESSAGE.length, cols)).toEqual(
        wrapAnsiEnd(USER_REPORT_MESSAGE, cols)
      )
    }
  })

  it('keeps cursor on the same row when text exactly fills the terminal width', () => {
    // wrap-ansi does NOT push exact-fill text onto a phantom next line.
    // The previous algorithm did — that's what produced the visible
    // "cursor parked one row below the last char" symptom on narrow
    // terminals at certain message lengths.
    for (const cols of [8, 12, 18, 24]) {
      const text = 'a'.repeat(cols)
      const layout = cursorLayout(text, text.length, cols)
      const inkLines = wrapAnsi(text, cols, { hard: true, trim: false }).split('\n')

      expect(layout.line).toBe(0)
      expect(layout.column).toBe(cols)
      expect(inkLines).toHaveLength(1)
      expect(inputVisualHeight(text, cols)).toBe(1)
    }
  })

  it('does not stuff a trailing whitespace word onto a phantom line', () => {
    // "branch investigate" at cols=20 fits on one row in wrap-ansi. The
    // bug claimed otherwise, parking the cursor at (line=1, col=?) and
    // leaving the user's "branch investigate" rendered alone on row 0
    // with the cursor block several cells past it.
    const text = 'branch investigate'
    const cols = 20

    expect(cursorLayout(text, text.length, cols)).toEqual({ column: text.length, line: 0 })
    expect(cursorLayout(text, text.length, cols)).toEqual(wrapAnsiEnd(text, cols))
  })

  it('agrees with wrap-ansi for word-wrap that pushes a word onto the next line', () => {
    // "hello world" at cols=8 wraps to ["hello ", "world"] in wrap-ansi.
    // The cursor at end-of-text must land at line=1, col=5 — where Ink
    // actually renders the last 'd'. The previous algorithm reported
    // (line=2, col=0) here (phantom extra wrap), which parked the
    // cursor on a row Ink never painted.
    const text = 'hello world'
    const cols = 8

    expect(cursorLayout(text, text.length, cols)).toEqual({ column: 5, line: 1 })
    expect(cursorLayout(text, text.length, cols)).toEqual(wrapAnsiEnd(text, cols))
  })
})
