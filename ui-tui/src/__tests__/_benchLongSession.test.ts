/**
 * Long-session streaming bench: how much does ONE repaint cost while a turn is
 * live, and is it the streaming path or the baseline frame cost?
 *
 * Baseline = same mounted tree, no turn: a few $uiState patches (what any timer
 * or status tick costs).
 * Streaming = the real turn controller pumping message deltas through the real
 * stores into the real AppLayout.
 *
 * Node pins the process, so the numbers are comparable to Ink's own
 * SHIINA_DEV_PERF frames (durationMs + phases).
 *
 * Run: npx vitest run src/__tests__/_benchLongSession.test.ts
 * Output: /tmp/bench_long_session.txt
 */
import { appendFileSync, writeFileSync } from 'node:fs'
import { PassThrough } from 'node:stream'

import { renderSync } from '@shiina/ink'
import React from 'react'
import { describe, it } from 'vitest'

import { GatewayProvider } from '../app/gatewayContext.js'
import type { AppLayoutComposerProps, AppLayoutProps } from '../app/interfaces.js'
import { resetOverlayState } from '../app/overlayStore.js'
import { turnController } from '../app/turnController.js'
import { resetTurnState } from '../app/turnStore.js'
import { patchUiState, resetUiState } from '../app/uiStore.js'
import { AppLayout } from '../components/appLayout.js'
import type { GatewayClient } from '../gatewayClient.js'
import { DEFAULT_VOICE_RECORD_KEY } from '../lib/platform.js'
import { DEFAULT_THEME } from '../theme.js'
import type { Msg } from '../types.js'

const OUT = '/tmp/bench_long_session.txt'
writeFileSync(OUT, '')

const rows = (n: number): Msg[] => [
  { kind: 'intro', role: 'system', text: '' },
  ...Array.from({ length: n }, (_, i) => ({
    role: (i % 3 === 0 ? 'user' : 'assistant') as Msg['role'],
    text: `Message ${i}: ${'prose about the work being done here. '.repeat(12)}`
  }))
]

const gatewayStub = {
  gw: { request: () => new Promise<never>(() => {}), send: () => {} } as unknown as GatewayClient,
  rpc: (() => new Promise<never>(() => {})) as never
}

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

const props = (items: Msg[]): AppLayoutProps => ({
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
  progress: { showProgressArea: true },
  status: {
    cwdLabel: '~/repo',
    goodVibesTick: 0,
    lastTurnEndedAt: null,
    sessionStartedAt: Date.now() - 3_600_000,
    sessionTitle: 'bench',
    showStickyPrompt: false,
    statusColor: DEFAULT_THEME.color.ok,
    stickyPrompt: '',
    turnStartedAt: Date.now(),
    voiceLabel: ''
  },
  transcript: {
    historyItems: items,
    scrollRef: {
      current: {
        adjustScrollTop: () => {},
        getLastManualScrollAt: () => 0,
        getPendingDelta: () => 0,
        getScrollHeight: () => items.length * 4,
        getScrollTop: () => 0,
        getViewportHeight: () => 30,
        getViewportTop: () => 0,
        isSticky: () => true,
        scrollBy: () => {},
        scrollTo: () => {},
        scrollToBottom: () => {},
        setClampBounds: () => {},
        subscribe: () => () => {}
      } as never
    },
    virtualHistory: {
      bottomSpacer: 0,
      end: items.length,
      measureRef: () => () => {},
      offsets: items.map((_, i) => i * 4),
      start: Math.max(0, items.length - 40),
      topSpacer: 0
    },
    virtualRows: items.map((msg, index) => ({ index, key: `m${index}`, msg }))
  }
})

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))

interface Frame {
  durationMs: number
  phases?: Record<string, number>
  ts: number
}

const reply = (n: number) => {
  const parts: string[] = []

  while (parts.join('').length < n) {
    parts.push(`Step ${parts.length}: I ran the command and inspected the output.\n\n`)
  }

  return parts.join('')
}

const mount = (items: Msg[], frames: Frame[]) => {
  const stdout = new PassThrough()
  const stdin = new PassThrough()
  const stderr = new PassThrough()

  Object.assign(stdout, { columns: 120, isTTY: false, rows: 40 })
  Object.assign(stdin, { isTTY: true, ref: () => {}, setRawMode: () => {}, unref: () => {} })
  Object.assign(stderr, { isTTY: false })

  return renderSync(
    React.createElement(GatewayProvider, { value: gatewayStub }, React.createElement(AppLayout, props(items))),
    {
      onFrame: (ev: Frame) => frames.push(ev),
      patchConsole: false,
      stderr: stderr as unknown as NodeJS.WriteStream,
      stdin: stdin as unknown as NodeJS.ReadStream,
      stdout: stdout as unknown as NodeJS.WriteStream
    }
  )
}

const stats = (v: number[]) => {
  if (!v.length) {
    return 'n=0'
  }

  const s = [...v].sort((a, b) => a - b)

  const pct = (p: number) => s[Math.min(s.length - 1, Math.floor(s.length * p))]!

  return `n=${String(s.length).padStart(3)} p50=${pct(0.5).toFixed(1)} p95=${pct(0.95).toFixed(1)} max=${s[s.length - 1]!.toFixed(1)}`
}

const PHASES = ['yoga', 'renderer', 'diff', 'optimize', 'write'] as const
const COUNTERS = ['yogaVisited', 'yogaMeasured', 'yogaLive', 'patches'] as const

const report = (label: string, frames: Frame[], extra = '') => {
  appendFileSync(OUT, `\n${label}  frame[${stats(frames.map(f => f.durationMs))}] ${extra}\n`)

  for (const k of PHASES) {
    const vals = frames.map(f => f.phases?.[k]).filter((v): v is number => typeof v === 'number')

    if (vals.length) {
      appendFileSync(OUT, `    ${k.padEnd(9)} ${stats(vals)}\n`)
    }
  }

  for (const k of COUNTERS) {
    const vals = frames.map(f => f.phases?.[k]).filter((v): v is number => typeof v === 'number')

    if (vals.length) {
      appendFileSync(OUT, `    ${k.padEnd(9)} ${stats(vals)}\n`)
    }
  }

  appendFileSync(OUT, `    durationMs samples: ${frames.map(f => f.durationMs.toFixed(0)).join(',')}\n`)
}

describe('bench: long-session streaming', () => {
  it('per-repaint cost: idle baseline vs live streaming', async () => {
    for (const txRows of [400, 800]) {
      for (const replySize of [16_000, 256_000]) {
        resetOverlayState()
        resetUiState()
        resetTurnState()
        turnController.fullReset()

        const items = rows(txRows)
        const frames: Frame[] = []
        const instance = mount(items, frames)

        patchUiState({ sid: `s-${txRows}-${replySize}`, status: 'ready' })
        await sleep(60)

        // ── baseline: repaints with NO turn running (what a timer/status tick costs)
        frames.length = 0

        for (let i = 0; i < 6; i++) {
          patchUiState({ status: `idle tick ${i}` })
          await sleep(40)
        }

        report(`tx=${txRows} BASELINE (idle repaint)`, frames)

        // ── live turn: real deltas through the real controller
        patchUiState({ busy: true, showReasoning: true, status: 'working', streaming: true })
        turnController.startMessage()
        await sleep(60)
        frames.length = 0

        const text = reply(replySize)
        const chunk = 512
        let controllerMs = 0

        for (let off = 0; off < text.length; off += chunk) {
          const t0 = performance.now()

          turnController.recordMessageDelta({ text: text.slice(off, off + chunk) })
          controllerMs += performance.now() - t0
          await sleep(10)
        }

        await sleep(40)
        report(`tx=${txRows} STREAMING reply=${replySize / 1000}KB`, frames, `controllerTotal=${controllerMs.toFixed(1)}ms`)

        instance.unmount()
        instance.cleanup()
        await sleep(20)
      }
    }
  }, 600_000)
})
