import { describe, expect, it } from 'vitest'

import { hapticIntentForInput } from './key-haptics'

describe('hapticIntentForInput', () => {
  it('maps Enter to submit', () => {
    expect(hapticIntentForInput('\r')).toBe('submit')
    expect(hapticIntentForInput('ls -la\r')).toBe('submit')
    expect(hapticIntentForInput('line one\nline two')).toBe('submit')
  })

  it('maps Ctrl-C to cancel', () => {
    expect(hapticIntentForInput('\x03')).toBe('cancel')
  })

  it('maps a lone Escape to tap, but not escape sequences', () => {
    expect(hapticIntentForInput('\x1b')).toBe('tap')
    expect(hapticIntentForInput('\x1b[A')).toBeNull()
    expect(hapticIntentForInput('\x1b[Op')).toBeNull()
  })

  it('stays silent for printable typing', () => {
    expect(hapticIntentForInput('hello world')).toBeNull()
    expect(hapticIntentForInput('')).toBeNull()
    expect(hapticIntentForInput('make build --release')).toBeNull()
  })

  it('prefers submit when a chunk mixes control keys', () => {
    expect(hapticIntentForInput('\x03\r')).toBe('submit')
  })
})
