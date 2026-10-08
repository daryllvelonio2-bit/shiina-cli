import { describe, expect, it } from 'vitest'

import { appendToolShelfMessage, keepRecentStepRows } from '../lib/liveProgress.js'
import type { Msg } from '../types.js'

const shelf = (name: string): Msg => ({ kind: 'trail', role: 'system', text: '', tools: [`Terminal("${name}")`] })
const thought = (text: string): Msg => ({ kind: 'trail', role: 'system', text: '', thinking: text })

describe('appendToolShelfMessage', () => {
  // A later tool call used to be pulled back into an older `Steps` block, so the
  // trail stopped reading as a chronological hierarchy: the call rendered above
  // the thoughts that actually preceded it.
  it('attaches a tool result to the step directly above it', () => {
    const grouped = appendToolShelfMessage(appendToolShelfMessage([shelf('one')], thought('hmm')), shelf('two'))

    expect(grouped).toHaveLength(2)
    expect(grouped[0]?.tools).toHaveLength(1)
    expect(grouped[1]?.thinking).toBe('hmm')
    expect(grouped[1]?.tools).toEqual(['Terminal("two")'])
  })

  it('still folds consecutive tool results into one row set', () => {
    const grouped = appendToolShelfMessage(appendToolShelfMessage([thought('hmm')], shelf('one')), shelf('two'))

    expect(grouped).toHaveLength(1)
    expect(grouped[0]?.tools).toEqual(['Terminal("one")', 'Terminal("two")'])
  })

  it('does not reach past an assistant message', () => {
    // The shelf directly above is the assistant text, so the result must become
    // its own row rather than joining the trail before the answer.
    const grouped = appendToolShelfMessage([shelf('one'), { role: 'assistant', text: 'answer' }], shelf('two'))

    expect(grouped).toHaveLength(3)
    expect(grouped[0]?.tools).toEqual(['Terminal("one")'])
    expect(grouped[2]?.tools).toEqual(['Terminal("two")'])
  })
})

describe('keepRecentStepRows', () => {
  it('keeps only the newest steps and never drops non-step rows', () => {
    const rows: Msg[] = [
      shelf('1'),
      thought('2'),
      shelf('3'),
      thought('4'),
      shelf('5'),
      thought('6'),
      { role: 'assistant', text: 'answer' },
      thought('7')
    ]

    const kept = keepRecentStepRows(rows)

    expect(kept.filter(row => row.kind === 'trail')).toHaveLength(5)
    expect(kept.some(row => row.text === 'answer')).toBe(true)
    // The oldest step (1) rolled out; the newest (7) stayed.
    expect(kept.some(row => row.tools?.[0] === 'Terminal("1")')).toBe(false)
    expect(kept.at(-1)?.thinking).toBe('7')
  })

  it('leaves a short trail alone', () => {
    const rows: Msg[] = [shelf('1'), thought('2')]

    expect(keepRecentStepRows(rows)).toEqual(rows)
  })
})
