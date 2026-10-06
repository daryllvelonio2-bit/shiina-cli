/**
 * Structural wiring contract for the three layouts: a layout id alone must
 * decide WHICH regions mount, and the transcript must receive the same message
 * content whichever layout is active (layouts are presentational transforms
 * over the shared stores).
 *
 * Leaves are mocked to count mounts — StatusRule (status rule row),
 * TranscriptScrollbar (transcript gutter), LiveAgentsPanel and LiveTodoPanel
 * (the instruments that move between the composer flow and studio's side
 * column) — so the assertions are about structure, not pixels.
 */
import { PassThrough } from 'node:stream'

import { renderSync } from '@shiina/ink'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { GatewayProvider } from '../app/gatewayContext.js'
import type { AppLayoutComposerProps, AppLayoutProps } from '../app/interfaces.js'
import { resetOverlayState } from '../app/overlayStore.js'
import { $petBox } from '../app/petFlashStore.js'
import { patchUiState, resetUiState } from '../app/uiStore.js'
import { AppLayout } from '../components/appLayout.js'
import type { LayoutId } from '../domain/layout.js'
import type { GatewayClient } from '../gatewayClient.js'
import { DEFAULT_VOICE_RECORD_KEY } from '../lib/platform.js'
import { DEFAULT_THEME } from '../theme.js'
import type { Msg } from '../types.js'

const renders = vi.hoisted(() => ({
  agents: 0,
  ledger: 0,
  messageCols: [] as number[],
  messages: [] as string[],
  statusRule: 0,
  todo: 0,
  transcript: 0
}))

// The ledger subscribes to the turn store; the frame test only cares whether the
// region mounts, so stub it rather than driving a live turn.
vi.mock('../components/stepLedger.js', () => ({
  StepLedger: () => {
    renders.ledger++

    return null
  }
}))

vi.mock('../components/agentsPanel.js', async importOriginal => {
  const mod = await importOriginal<typeof import('../components/agentsPanel.js')>()

  return {
    ...mod,
    LiveAgentsPanel: () => {
      renders.agents++

      return null
    }
  }
})

vi.mock('../components/appChrome.js', async importOriginal => {
  const mod = await importOriginal<typeof import('../components/appChrome.js')>()

  return {
    ...mod,
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

vi.mock('../components/messageLine.js', async importOriginal => {
  const mod = await importOriginal<typeof import('../components/messageLine.js')>()

  return {
    ...mod,
    MessageLine: (props: { cols: number; msg: Msg }) => {
      renders.messageCols.push(props.cols)
      renders.messages.push(String((props.msg as { text?: string }).text ?? props.msg.role))

      return null
    }
  }
})

vi.mock('../components/streamingAssistant.js', async importOriginal => {
  const mod = await importOriginal<typeof import('../components/streamingAssistant.js')>()

  return {
    ...mod,
    LiveTodoPanel: () => {
      renders.todo++

      return null
    },
    StreamingAssistant: () => null
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

const msg = (role: 'assistant' | 'user', text: string): Msg =>
  ({ id: text, kind: 'message', role, text }) as unknown as Msg

const userMsg = msg('user', 'parity marker')
const assistantMsg = msg('assistant', 'reply marker')

const props = (cols: number): AppLayoutProps => ({
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
  composer: { ...composerBase, cols },
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
    historyItems: [userMsg, assistantMsg],
    scrollRef: { current: null },
    virtualHistory: {
      bottomSpacer: 0,
      end: 2,
      measureRef: () => () => {},
      offsets: [],
      start: 0,
      topSpacer: 0
    },
    virtualRows: [
      { index: 0, key: 'a', msg: userMsg },
      { index: 1, key: 'b', msg: assistantMsg }
    ]
  }
})

const mounted: Array<() => void> = []

const mount = (layout: LayoutId, cols: number) => {
  patchUiState({ layout })
  const stdout = new PassThrough()
  const stdin = new PassThrough()
  const stderr = new PassThrough()

  Object.assign(stdout, { columns: cols, isTTY: false, rows: 20 })
  Object.assign(stdin, { isTTY: true, ref: () => {}, setRawMode: () => {}, unref: () => {} })
  Object.assign(stderr, { isTTY: false })

  let output = ''
  stdout.on('data', (chunk: Buffer) => {
    output += String(chunk)
  })

  const instance = renderSync(
    <GatewayProvider value={gatewayStub}>
      <AppLayout {...props(cols)} />
    </GatewayProvider>,
    {
      patchConsole: false,
      stderr: stderr as NodeJS.WriteStream,
      stdin: stdin as NodeJS.ReadStream,
      stdout: stdout as NodeJS.WriteStream
    }
  )

  mounted.push(() => {
    instance.unmount()
    instance.cleanup()
  })

  return { output: () => output }
}

/** Ink throttles paints and buffers each frame (synchronized output) and the
 *  test stream delivers the bytes asynchronously, so a sync read after a mount
 *  or a store switch can land before any output arrives. Let the throttle
 *  window and the stream flush settle before asserting on the painted frame. */
const flushPaint = () => new Promise(resolve => setTimeout(resolve, 50))

beforeEach(() => {
  renders.agents = 0
  renders.ledger = 0
  renders.messageCols = []
  renders.messages = []
  renders.statusRule = 0
  renders.todo = 0
  renders.transcript = 0
  resetOverlayState()
  resetUiState()
  patchUiState({ statusBar: 'top', status: 'ready' })
  $petBox.set(null)
})

afterEach(() => {
  while (mounted.length > 0) {
    mounted.pop()!()
  }

  resetOverlayState()
  resetUiState()
})

describe('layout frame', () => {
  it('minimal keeps the status line but mounts no widget chrome', () => {
    mount('minimal', 120)

    expect(renders.statusRule).toBeGreaterThan(0)
    expect(renders.transcript).toBe(0)
    expect(renders.agents).toBe(0)
    expect(renders.todo).toBe(0)
  })

  it('workbench keeps the instrument gutter and the composer agent dock', () => {
    const { output } = mount('workbench', 120)

    expect(renders.statusRule).toBeGreaterThan(0)
    expect(renders.transcript).toBeGreaterThan(0)
    expect(renders.agents).toBeGreaterThan(0)
    expect(output()).not.toContain('instruments')
  })

  it('timeline mounts the step ledger instead of the agents dock', () => {
    mount('timeline', 120)

    // The ledger is this design's instrument surface; mounting the dock too
    // would print the same steps twice.
    expect(renders.ledger).toBeGreaterThan(0)
    expect(renders.agents).toBe(0)
    expect(renders.transcript).toBeGreaterThan(0)
    expect(renders.statusRule).toBeGreaterThan(0)
  })

  it('studio moves the instruments into the reserved side column', async () => {
    const { output } = mount('studio', 160)

    // The agents board and todo list mount — in the side pane, so the
    // composer-flow copies must not appear a second time.
    expect(renders.agents).toBeGreaterThan(0)
    expect(renders.todo).toBeGreaterThan(0)
    await flushPaint()
    expect(output()).toContain('instruments')
  })

  it('does not reserve the floating pet gutter in studio', () => {
    // The pet floats bottom-right, which in studio is the reserved side
    // column — the transcript must not give up ~petBox.width of wrap on top
    // of the column it already lost.
    const pet = { height: 4, width: 24 }
    // The pet-applied paint is the narrowest one: PetPane clears $petBox just
    // after the first render when no pet is installed in this harness.
    const narrowest = () => Math.min(...renders.messageCols)

    $petBox.set(pet)
    mount('studio', 160)
    const studioWithPet = narrowest()

    renders.messageCols = []
    $petBox.set(null)
    mount('studio', 160)
    const studioWithoutPet = narrowest()

    expect(studioWithPet).toBe(studioWithoutPet)
    // Non-vacuous: studio did narrow the transcript for its side column.
    expect(studioWithPet).toBeLessThan(160)

    // Control: workbench still clears the pet, so it never covers its text.
    renders.messageCols = []
    $petBox.set(pet)
    mount('workbench', 160)

    expect(narrowest()).toBeLessThan(160)
  })

  it('an explicit studio switch re-renders the frame without dropping content', async () => {
    const { output } = mount('workbench', 160)

    expect(output()).not.toContain('instruments')

    // Live switch through the same store the config-sync poll writes.
    patchUiState({ layout: 'studio' })
    await flushPaint()

    expect(output()).toContain('instruments')
    // The transcript rows are still handed to the renderer after the switch —
    // only the arrangement changed. (MessageLine is stubbed to null here, so
    // the marker is asserted on the props, not the painted frame.)
    expect([...new Set(renders.messages)]).toEqual(['parity marker', 'reply marker'])
  })

  it('renders identical message content in every layout', () => {
    // One mount can commit several passes (store subscriptions, measure refs),
    // so compare the rendered message sequence, not the pass count.
    const rendered = (list: string[]) => [...new Set(list)]

    mount('minimal', 120)
    const minimalMsgs = rendered(renders.messages)
    const minimalCols = rendered(renders.messageCols.map(String))

    renders.messages = []
    renders.messageCols = []
    mount('workbench', 120)

    // Same cols budget => byte-identical message props; layouts are pure
    // presentational transforms, the transcript content never changes.
    expect(minimalMsgs).toEqual(['parity marker', 'reply marker'])
    expect(rendered(renders.messages)).toEqual(minimalMsgs)
    expect(rendered(renders.messageCols.map(String))).toEqual(minimalCols)

    renders.messages = []
    renders.messageCols = []
    mount('studio', 160)

    expect(rendered(renders.messages)).toEqual(minimalMsgs)
  })
})
