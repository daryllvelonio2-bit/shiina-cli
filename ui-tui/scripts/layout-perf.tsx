/**
 * Layout rendering-overhead harness (opt-perf evidence, not a CI test).
 *
 *   PATH=../node_modules/.bin:$PATH NODE_ENV=development SHIINA_DEV_PERF=1 \
 *     SHIINA_DEV_PERF_MS=0 SHIINA_DEV_PERF_LOG=/tmp/layout-perf.log \
 *     tsx scripts/layout-perf.tsx
 *
 * Warms each layout up, then measures three phases per layout over one mounted
 * tree — mount, a burst of streaming deltas (new composer object + one appended
 * transcript row per delta), and a live layout switch — and attributes the
 * React commits recorded by PerfPane (`SHIINA_DEV_PERF=1`) to the phase that
 * produced them. Dev-mode React, so absolute numbers are a pessimistic ceiling;
 * compare layouts against each other, not against production.
 */
import { readFileSync, writeFileSync } from 'node:fs'
import { PassThrough } from 'node:stream'

import { renderSync } from '@shiina/ink'
import React from 'react'

import { GatewayProvider } from '../src/app/gatewayContext.js'
import type { AppLayoutComposerProps, AppLayoutProps } from '../src/app/interfaces.js'
import { patchUiState, resetUiState } from '../src/app/uiStore.js'
import { AppLayout } from '../src/components/appLayout.js'
import { LAYOUT_IDS, type LayoutId, layoutRegions } from '../src/domain/layout.js'
import type { GatewayClient } from '../src/gatewayClient.js'
import { DEFAULT_VOICE_RECORD_KEY } from '../src/lib/platform.js'
import { PERF_ENABLED, PERF_LOG_PATH } from '../src/lib/perfPane.js'
import { DEFAULT_THEME } from '../src/theme.js'
import type { Msg } from '../src/types.js'

const COLS = 140
const ROWS = 40
const DELTAS = 25
const MOUNT_REPS = 3

const gatewayStub = {
  gw: { request: () => new Promise<never>(() => {}), send: () => {} } as unknown as GatewayClient,
  rpc: (() => new Promise<never>(() => {})) as never
}

const makeRow = (i: number): Msg =>
  ({
    id: `m${i}`,
    kind: 'message',
    role: i % 2 === 0 ? 'user' : 'assistant',
    text: `row ${i} — the quick brown fox jumps over the lazy dog ${'x'.repeat(i % 40)}`
  }) as unknown as Msg

const rows = Array.from({ length: ROWS }, (_, i) => makeRow(i))

const composerBase: AppLayoutComposerProps = {
  cols: COLS,
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

const buildProps = (input: string, historyRows: Msg[]): AppLayoutProps => ({
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
  composer: { ...composerBase, input, inputBuf: [input] },
  mouseTracking: 'off',
  progress: { showProgressArea: false },
  status: {
    cwdLabel: '~/repo',
    goodVibesTick: 0,
    lastTurnEndedAt: Date.now() - 5_000,
    sessionStartedAt: Date.now() - 60_000,
    sessionTitle: 'perf',
    showStickyPrompt: false,
    statusColor: DEFAULT_THEME.color.ok,
    stickyPrompt: '',
    turnStartedAt: Date.now() - 1_000,
    voiceLabel: ''
  },
  transcript: {
    historyItems: historyRows,
    scrollRef: { current: null },
    virtualHistory: {
      bottomSpacer: 0,
      end: historyRows.length,
      measureRef: () => () => {},
      offsets: [],
      start: 0,
      topSpacer: 0
    },
    virtualRows: historyRows.map((m, index) => ({ index, key: m.id ?? String(index), msg: m }))
  }
})

type Commit = { actualMs?: number; id?: string; src?: string; ts?: number }
type Phase = { commits: Commit[]; from: number; ms: number; name: string; to: number }

const phases: Phase[] = []

const timePhase = (name: string, fn: () => void) => {
  const from = Date.now()
  const start = performance.now()

  fn()

  const ms = performance.now() - start

  phases.push({ commits: [], from, ms, name, to: Date.now() })
}

const mount = (layout: LayoutId, props: AppLayoutProps) => {
  patchUiState({ layout })
  const stdout = new PassThrough()
  const stdin = new PassThrough()
  const stderr = new PassThrough()

  Object.assign(stdout, { columns: COLS, isTTY: false, rows: 40 })
  Object.assign(stdin, { isTTY: true, ref: () => {}, setRawMode: () => {}, unref: () => {} })
  Object.assign(stderr, { isTTY: false })

  return renderSync(
    <GatewayProvider value={gatewayStub}>
      <AppLayout {...props} />
    </GatewayProvider>,
    {
      patchConsole: false,
      stderr: stderr as NodeJS.WriteStream,
      stdin: stdin as NodeJS.ReadStream,
      stdout: stdout as NodeJS.WriteStream
    }
  )
}

const render = (props: AppLayoutProps) => (
  <GatewayProvider value={gatewayStub}>
    <AppLayout {...props} />
  </GatewayProvider>
)

const stat = (samples: number[]) => {
  const sorted = [...samples].sort((a, b) => a - b)
  const mean = sorted.reduce((a, b) => a + b, 0) / (sorted.length || 1)

  return {
    mean: Number(mean.toFixed(2)),
    p50: Number(sorted[Math.floor(sorted.length * 0.5)]?.toFixed(2) ?? 0),
    p95: Number(sorted[Math.max(0, Math.ceil(sorted.length * 0.95) - 1)]?.toFixed(2) ?? 0)
  }
}

if (PERF_ENABLED) {
  writeFileSync(PERF_LOG_PATH, '')
}

// Warm the renderer/module graph so the first measured mount is not the JIT's.
for (const layout of LAYOUT_IDS) {
  resetUiState()
  const warm = mount(layout, buildProps('', rows))

  warm.unmount()
  warm.cleanup()
}

phases.length = 0

const mounts: Record<string, number[]> = {}
const deltas: Record<string, number[]> = {}
const switches: Record<string, number[]> = {}

for (const layout of LAYOUT_IDS) {
  resetUiState()
  mounts[layout] = []
  deltas[layout] = []
  switches[layout] = []

  for (let rep = 0; rep < MOUNT_REPS; rep++) {
    timePhase(`mount:${layout}`, () => {
      const instance = mount(layout, buildProps('', rows))

      instance.unmount()
      instance.cleanup()
    })
  }

  mounts[layout] = phases.filter(p => p.name === `mount:${layout}`).map(p => p.ms)

  const instance = mount(layout, buildProps('', rows))
  let history = rows

  for (let i = 0; i < DELTAS; i++) {
    history = [...rows, makeRow(ROWS + i)]

    timePhase(`deltas:${layout}`, () => {
      instance.rerender(render(buildProps(`typing ${i}`, history)))
    })
  }

  deltas[layout] = phases.filter(p => p.name === `deltas:${layout}`).map(p => p.ms)

  // Live switch on the SAME mounted tree: the config-sync path writes the
  // store; the frame must re-render, never remount the transcript.
  const next = LAYOUT_IDS[(LAYOUT_IDS.indexOf(layout) + 1) % LAYOUT_IDS.length]

  for (let rep = 0; rep < 3; rep++) {
    timePhase(`switch:${layout}`, () => {
      patchUiState({ layout: rep % 2 === 0 ? next : layout })
      instance.rerender(render(buildProps(`typing ${DELTAS}`, history)))
      patchUiState({ layout })
      instance.rerender(render(buildProps(`typing ${DELTAS}`, history)))
    })
  }

  switches[layout] = phases.filter(p => p.name === `switch:${layout}`).map(p => p.ms / 2)

  instance.unmount()
  instance.cleanup()
}

// Attribute the recorded React commits to the phase that produced them by ts.
if (PERF_ENABLED) {
  const lines = readFileSync(PERF_LOG_PATH, 'utf8').trim().split('\n').filter(Boolean)

  for (const line of lines) {
    try {
      const row = JSON.parse(line) as { actualMs?: number; id?: string; src?: string; ts?: number }

      if (row.src !== 'react' || !row.id) {
        continue
      }

      const phase = phases.find(p => (row.ts ?? 0) >= p.from && (row.ts ?? 0) <= p.to)

      phase?.commits.push(row)
    } catch {
      // partial tail line
    }
  }
}

console.log('\n## layout rendering overhead (dev-mode React, cols=%d, %d rows)\n', COLS, ROWS)
console.log('| layout | mount p50 (ms) | delta mean | delta p50 | delta p95 | layout switch (ms) |')
console.log('|---|---|---|---|---|---|')

for (const layout of LAYOUT_IDS) {
  const m = stat(mounts[layout])
  const d = stat(deltas[layout])
  const s = stat(switches[layout])

  console.log(`| ${layout} | ${m.p50} | ${d.mean} | ${d.p50} | ${d.p95} | ${s.p50} |`)
}

console.log('\n### React commits per phase (PerfPane id)\n')
console.log('| phase | pane | commits | mean ms | p95 ms | max ms |')
console.log('|---|---|---|---|---|---|')

const groups = new Map<string, Array<{ actualMs: number; id: string }>>()

for (const phase of phases) {
  for (const commit of phase.commits) {
    const key = `${phase.name.split(':')[0]}:${commit.id}`

    groups.set(key, [...(groups.get(key) ?? []), { actualMs: commit.actualMs ?? 0, id: commit.id ?? '' }])
  }
}

for (const [key, commits] of [...groups.entries()].sort()) {
  const s = stat(commits.map(c => c.actualMs))

  console.log(
    `| ${key} | ${commits[0]?.id ?? ''} | ${commits.length} | ${s.mean} | ${s.p95} | ${Math.max(...commits.map(c => c.actualMs)).toFixed(2)} |`
  )
}

console.log('\nregions:')
for (const layout of LAYOUT_IDS) {
  const spec = layoutRegions(layout, COLS) as unknown as Record<string, unknown>
  const on = Object.entries(spec)
    .filter(([, v]) => v === true)
    .map(([k]) => k)

  console.log(`  ${layout}: sideWidth=${spec.sideWidth} [${on.join(', ')}]`)
}
