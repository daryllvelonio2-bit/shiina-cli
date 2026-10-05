import { describe, expect, it } from 'vitest'

import { STREAM_MAX_BATCH_MS } from '../config/timing.js'
import { adaptStreamDelay } from '../lib/streamGovernor.js'

// The streaming governor decides how often a long reply commits. Getting this
// wrong is exactly the reported symptom: commits faster than the machine can
// paint (queue buildup → bursty stutter) or so slow the text crawls.

const FLOOR = 16

describe('adaptStreamDelay', () => {
  it('backs off when a cycle overruns its own delay', () => {
    // 40 ms of work behind a 16 ms delay → the loop is saturated.
    expect(adaptStreamDelay(16, 40, FLOOR)).toBe(26)
  })

  it('keeps backing off until the cycle fits, and stops at the cap', () => {
    let delay = 16

    for (let i = 0; i < 12; i++) {
      delay = adaptStreamDelay(delay, delay * 3, FLOOR)
    }

    expect(delay).toBe(STREAM_MAX_BATCH_MS)

    // At the cap a cycle that finally fits does not push past it.
    expect(adaptStreamDelay(STREAM_MAX_BATCH_MS, STREAM_MAX_BATCH_MS, FLOOR)).toBeLessThanOrEqual(STREAM_MAX_BATCH_MS)
  })

  it('tightens when the cycle comfortably fits', () => {
    expect(adaptStreamDelay(40, 40, FLOOR)).toBe(34)
  })

  it('never decays below the interaction floor', () => {
    let delay = 96

    for (let i = 0; i < 20; i++) {
      delay = adaptStreamDelay(delay, delay, 96)
    }

    expect(delay).toBe(96)
  })

  it('decays back to the base floor after the load clears', () => {
    let delay = 16

    for (let i = 0; i < 8; i++) {
      delay = adaptStreamDelay(delay, 200, FLOOR)
    }

    expect(delay).toBeGreaterThan(FLOOR)

    for (let i = 0; i < 40; i++) {
      delay = adaptStreamDelay(delay, delay, FLOOR)
    }

    expect(delay).toBe(FLOOR)
  })

  it('never goes backwards', () => {
    for (const cycle of [0, 5, 16, 17, 40, 200]) {
      for (const delay of [16, 26, 96, STREAM_MAX_BATCH_MS]) {
        const next = adaptStreamDelay(delay, cycle, FLOOR)

        expect(next).toBeGreaterThan(0)
        expect(next).toBeLessThanOrEqual(STREAM_MAX_BATCH_MS)
      }
    }
  })
})
