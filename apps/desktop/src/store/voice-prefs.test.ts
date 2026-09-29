import { describe, expect, it, vi } from 'vitest'

vi.mock('@/shiina', () => ({
  getShiinaConfigRecord: vi.fn(async () => ({})),
  saveShiinaConfig: vi.fn(async () => undefined)
}))

import { saveShiinaConfig } from '@/shiina'

import { $voiceStopPhrase, applyVoiceStopPhraseFromConfig } from './voice-prefs'

it('keeps the desktop toggle local across config refreshes', async () => {
  for (const fails of [false, true]) {
    for (const enabled of [false, true]) {
      localStorage.clear()
      vi.resetModules()
      const prefs = await import('./voice-prefs')
      const write = vi.spyOn(localStorage, 'setItem')

      if (fails) {
        write.mockImplementation(() => {
          throw new DOMException('Full', 'QuotaExceededError')
        })
      }

      vi.mocked(saveShiinaConfig).mockClear()

      try {
        await prefs.setAutoSpeakReplies(enabled)
        prefs.applyAutoSpeakFromConfig({ voice: { auto_tts: !enabled } })
        expect(prefs.$autoSpeakReplies.get()).toBe(enabled)
        expect(saveShiinaConfig).not.toHaveBeenCalled()
        expect(localStorage.getItem('shiina.desktop.autoSpeakReplies')).toBe(fails ? null : String(enabled))
      } finally {
        write.mockRestore()
      }
    }
  }
})

it('migrates the legacy preference once, not on every refresh', async () => {
  for (const fails of [false, true]) {
    for (const enabled of [false, true]) {
      localStorage.clear()
      vi.resetModules()
      const prefs = await import('./voice-prefs')
      const write = vi.spyOn(localStorage, 'setItem')

      if (fails) {
        write.mockImplementation(() => {
          throw new DOMException('Denied', 'SecurityError')
        })
      }

      try {
        prefs.applyAutoSpeakFromConfig(null)
        expect(localStorage.getItem('shiina.desktop.autoSpeakReplies')).toBeNull()
        prefs.applyAutoSpeakFromConfig({ voice: { auto_tts: enabled } })
        prefs.applyAutoSpeakFromConfig({ voice: { auto_tts: !enabled } })
        expect(prefs.$autoSpeakReplies.get()).toBe(enabled)
        expect(localStorage.getItem('shiina.desktop.autoSpeakReplies')).toBe(fails ? null : String(enabled))
      } finally {
        write.mockRestore()
      }
    }
  }
})

describe('applyVoiceStopPhraseFromConfig', () => {
  it('defaults to "stop" when the key is absent (backend default applies)', () => {
    applyVoiceStopPhraseFromConfig({ voice: {} })
    expect($voiceStopPhrase.get()).toBe('stop')

    applyVoiceStopPhraseFromConfig(null)
    expect($voiceStopPhrase.get()).toBe('stop')
  })

  it('uses the first configured phrase so a custom phrase renders correctly', () => {
    applyVoiceStopPhraseFromConfig({ voice: { stop_phrases: ['goodbye shiina', 'stop'] } })
    expect($voiceStopPhrase.get()).toBe('goodbye shiina')
  })

  it('coerces a bare string like the backend does', () => {
    applyVoiceStopPhraseFromConfig({ voice: { stop_phrases: 'halt' } })
    expect($voiceStopPhrase.get()).toBe('halt')
  })

  it('null phrase when stop phrases are disabled — no notice is shown', () => {
    applyVoiceStopPhraseFromConfig({ voice: { stop_phrases: [] } })
    expect($voiceStopPhrase.get()).toBeNull()
  })

  it('malformed entries are skipped; all-blank list disables', () => {
    applyVoiceStopPhraseFromConfig({ voice: { stop_phrases: ['  ', ''] } })
    expect($voiceStopPhrase.get()).toBeNull()
  })
})
