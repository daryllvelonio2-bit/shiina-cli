/**
 * Render-count contract for the AppLayout memo boundary (OPT-12).
 *
 * A keystroke rebuilds the whole `composer` object — `useComposerState` returns
 * a fresh object on every change. Before this boundary `TranscriptPane` and
 * `StatusRulePane` took that whole object as a prop even though they read only
 * `composer.cols`, so their `memo` shallow compare failed on every keystroke and
 * the transcript aura repainted inside the fast-echo frame. The boundary is now
 * a plain `cols: number` prop: a keystroke bails out of the transcript subtree
 * while the composer still repaints.
 */
import { PassThrough } from 'node:stream'

import { renderSync } from '@shiina/ink'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { GatewayProvider } from '../app/gatewayContext.js'
import type { AppLayoutComposerProps, AppLayoutProps } from '../app/interfaces.js'
import { resetOverlayState } from '../app/overlayStore.js'
import { patchUiState, resetUiState } from '../app/uiStore.js'
import { AppLayout } from '../components/appLayout.js'
import type { GatewayClient } from '../gatewayClient.js'
import { DEFAULT_VOICE_RECORD_KEY } from '../lib/platform.js'
import { DEFAULT_THEME } from '../theme.js'

// Counted through the appChrome leaves that each pane renders exactly once per
// render and nowhere else in the tree:
//   GoodVibesHeart      -> ComposerPane only
//   TranscriptScrollbar -> TranscriptPane only
//   StatusRule          -> StatusRulePane only
const renders = vi.hoisted(() => ({ composer: 0, statusRule: 0, transcript: 0 }))

vi.mock('../components/appChrome.js', async importOriginal => {
  const mod = await importOriginal<typeof import('../components/appChrome.js')>()

  return {
    ...mod,
    GoodVibesHeart: () => {
      renders.composer++

      return null
    },
    StatusRule: () => {
      renders.statusRule++

      return null
    },
    TranscriptScrollbar: () => {
      renders.transcript++

      return null
    }
  }
})

const gatewayStub = {
  gw: {
    request: () => new Promise<never>(() => {}),
    send: () => {}
  } as unknown as GatewayClient,
  rpc: (() => new Promise<never>(() => {})) as never
}

const T0 = 1_800_000_000_000

const composerBase: AppLayoutComposerProps = {
  cols: 120,
  compIdx: 0,
  completions: [],
  empty: false,
  handleTextPaste: () => null,
  input: '',
  inputBuf: [''],
  pagerPageSize: 10,
  queueEditIdx: null,
  queuedDisplay: [],
  submit: () => {},
  updateInput: () => {},
  voiceRecordKey: DEFAULT_VOICE_RECORD_KEY
}

// `transcript` / `status` / `progress` stay the same objects across the two
// renders below, exactly as they are between two keystrokes.
const baseProps: AppLayoutProps = {
  actions: {
    activateLiveSession: () => {},
    answerApproval: () => {},
    answerClarify: () => {},
    answerClarifyQuestion: () => {},
    answerSecret: () => {},
    answerSudo: () => {},
    answerVaultUnlock: () => {},
    clearSelection: () => {},
    closeLiveSession: () => Promise.resolve(null),
    newLiveSession: () => {},
    newPromptSession: () => {},
    onModelSelect: () => {},
    resumeById: () => {},
    setStickyPrompt: () => {}
  },
  composer: composerBase,
  mouseTracking: 'off',
  progress: { showProgressArea: false },
  status: {
    cwdLabel: '~/repo',
    goodVibesTick: 0,
    lastTurnEndedAt: T0 - 5_000,
    sessionStartedAt: T0 - 60_000,
    sessionTitle: '',
    showStickyPrompt: false,
    statusColor: DEFAULT_THEME.color.ok,
    stickyPrompt: '',
    turnStartedAt: null,
    voiceLabel: ''
  },
  transcript: {
    historyItems: [],
    scrollRef: { current: null },
    virtualHistory: {
      bottomSpacer: 0,
      end: 0,
      measureRef: () => () => {},
      offsets: [],
      start: 0,
      topSpacer: 0
    },
    virtualRows: []
  }
}

const withComposer = (composer: AppLayoutComposerProps) => (
  <GatewayProvider value={gatewayStub}>
    <AppLayout {...baseProps} composer={composer} />
  </GatewayProvider>
)

const mounted: Array<() => void> = []

const mount = (composer: AppLayoutComposerProps) => {
  const stdout = new PassThrough()
  const stdin = new PassThrough()
  const stderr = new PassThrough()

  Object.assign(stdout, { columns: 120, isTTY: false, rows: 20 })
  // PromptZone's prompts call `useInput`, which needs raw mode.
  Object.assign(stdin, { isTTY: true, ref: () => {}, setRawMode: () => {}, unref: () => {} })
  Object.assign(stderr, { isTTY: false })

  const instance = renderSync(withComposer(composer), {
    patchConsole: false,
    stderr: stderr as NodeJS.WriteStream,
    stdin: stdin as NodeJS.ReadStream,
    stdout: stdout as NodeJS.WriteStream
  })

  mounted.push(() => {
    instance.unmount()
    instance.cleanup()
  })

  return instance
}

beforeEach(() => {
  renders.composer = 0
  renders.statusRule = 0
  renders.transcript = 0
  resetOverlayState()
  resetUiState()
  patchUiState({ sessionTitle: 'test', sid: 'sid-1', status: 'ready' })
})

afterEach(() => {
  while (mounted.length > 0) {
    mounted.pop()!()
  }

  resetOverlayState()
  resetUiState()
})

describe('AppLayout composer memo boundary', () => {
  it('a keystroke repaints the composer but not the transcript or the status rule', () => {
    const instance = mount(composerBase)
    const baseline = { ...renders }

    expect(baseline.transcript).toBeGreaterThan(0)
    expect(baseline.composer).toBeGreaterThan(0)
    expect(baseline.statusRule).toBeGreaterThan(0)

    // A keystroke: a new `composer` object (differing only in `input`), the
    // transcript / status / progress props identical by reference.
    instance.rerender(withComposer({ ...composerBase, input: 'a' }))

    expect(renders.transcript).toBe(baseline.transcript)
    expect(renders.statusRule).toBe(baseline.statusRule)
    expect(renders.composer).toBeGreaterThan(baseline.composer)
  })
})
