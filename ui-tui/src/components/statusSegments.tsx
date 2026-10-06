import { Box, stringWidth, Text } from '@shiina/ink'
import type { Usage } from '@shiina/shared/gateway-events'
import { useStore } from '@nanostores/react'
import { type ReactNode, useEffect, useState } from 'react'

import { $isStatusRuleOccluded } from '../app/overlayStore.js'
import { DEV_CREDITS_MODE } from '../config/env.js'
import type { Design, DesignGlyphs } from '../design.js'
import { fmtDuration } from '../domain/messages.js'
import type { Theme } from '../theme.js'
import type { StatusBarSegments } from './appChrome.js'

/**
 * The status rule's tail, as data.
 *
 * Adding, reordering, restyling or hiding a segment is a change to this list
 * (or to the skin's `tui.status_bar.segments`) — never a new branch in the
 * 400-line render path. `StatusRule` walks the resolved list in order and
 * charges each segment's width to the tail budget, so array order IS render
 * order AND drop priority: the last entries yield first on a narrow terminal.
 */

/** Bounded width of the elapsed-time clock, derived from `fmtDuration` itself
 *  so the reservation stays consistent with what actually renders. Durations
 *  beyond 100h clip rather than reserving unbounded width. */
export const MAX_DURATION_WIDTH = Math.max(
  stringWidth(fmtDuration(59 * 60_000 + 59_000)), // "59m 59s"
  stringWidth(fmtDuration(99 * 3_600_000 + 59 * 60_000)) // "99h 59m"
)

function SessionDuration({ startedAt }: { startedAt: number }) {
  const [now, setNow] = useState(() => Date.now())
  const isOccluded = useStore($isStatusRuleOccluded)

  useEffect(() => {
    // Paused only while an overlay actually covers the status rule — see
    // FaceTicker.  The `setNow` below already re-seeds from the wall clock
    // on every re-arm, so it doubles as the reveal catch-up.
    if (isOccluded) {
      return
    }

    setNow(Date.now())
    const id = setInterval(() => setNow(Date.now()), 1000)

    return () => clearInterval(id)
  }, [isOccluded, startedAt])

  return fmtDuration(now - startedAt)
}

function IdleSince({ endedAt, glyph }: { endedAt: number; glyph: string }) {
  // Time since the last final agent response. Re-ticks every second like
  // SessionDuration so the read-out stays live while the session idles.
  const [now, setNow] = useState(() => Date.now())
  const isOccluded = useStore($isStatusRuleOccluded)

  useEffect(() => {
    // Paused only while an overlay actually covers the status rule — see
    // FaceTicker.  The `setNow` below re-seeds from the wall clock on reveal
    // so the idle read-out is not frozen when the overlay closes.
    if (isOccluded) {
      return
    }

    setNow(Date.now())
    const id = setInterval(() => setNow(Date.now()), 1000)

    return () => clearInterval(id)
  }, [endedAt, isOccluded])

  return `${glyph} ${fmtDuration(now - endedAt)}`
}

const statusSessionCountLabel = (count: number) => (count === 1 ? '1 session' : `${count} sessions`)

/** Everything a tail segment may read. Kept narrow on purpose: a segment is a
 *  pure function of the session snapshot plus the theme/design tokens. */
export interface StatusSegmentCtx {
  bgCount: number
  busy: boolean
  focus: boolean
  lastTurnEndedAt?: null | number
  liveSessionCount: number
  onSessionCountClick?: () => void
  sessionStartedAt?: null | number
  subagentCount: number
  t: Theme
  usage: Usage
  voiceLabel?: null | string
  /** Drives the voice readout's marker glyph and colour. The glyph itself is
   *  NOT part of `voiceLabel` — it comes from the design's vocabulary. */
  voiceTone?: 'idle' | 'rec' | 'stt'
}

export interface StatusSegmentView {
  /** Node rendered for this segment, including its leading separator. */
  node: ReactNode
  /** Columns charged to the tail budget, EXCLUDING the separator. */
  reserve: number
}

export interface StatusSegmentSpec {
  /** Stable id — the name a skin uses in `tui.status_bar.segments`. */
  id: string
  /** `display.status_bar.fields` gate (classic-CLI parity); null = always on. */
  field: null | string
  /** Terminal-width tier from `statusBarSegments`; undefined = always eligible. */
  segsKey?: keyof StatusBarSegments
  /** Rendered before the budgeted tail and never dropped. */
  pinned?: boolean
  build: (ctx: StatusSegmentCtx) => null | StatusSegmentView
}

const segment = (glyphs: DesignGlyphs, body: ReactNode, color: string, extra?: { dim?: boolean }) => (
  <Text color={color} dim={extra?.dim} wrap="truncate-end">
    {glyphs.separator}
    {body}
  </Text>
)

const bodyWidth = (glyphs: DesignGlyphs, body: string) => stringWidth(body)

/**
 * The built-in tail, in render order. `field` mirrors the classic CLI bar's
 * `display.status_bar.fields` names so one config gates both bars.
 */
export const STATUS_SEGMENTS: StatusSegmentSpec[] = [
  {
    build: ctx => {
      if (!ctx.focus) {
        return null
      }

      const { glyphs } = ctx.t.design

      return {
        node: (
          <Box flexDirection="row" flexShrink={0}>
            <Text color={ctx.t.color.muted}>{glyphs.separator}</Text>
            <Text color={ctx.t.color.warn}>
              {glyphs.focus} focus
            </Text>
          </Box>
        ),
        reserve: bodyWidth(glyphs, `${glyphs.focus} focus`)
      }
    },
    field: null,
    id: 'focus',
    pinned: true
  },
  {
    build: ctx => {
      if (!ctx.sessionStartedAt) {
        return null
      }

      // Live clock: charge the bounded reservation, not the current text width,
      // so the model/context never get shoved as the clock grows.
      return {
        node: segment(ctx.t.design.glyphs, <SessionDuration startedAt={ctx.sessionStartedAt} />, ctx.t.color.muted),
        reserve: MAX_DURATION_WIDTH
      }
    },
    field: 'duration',
    id: 'duration',
    segsKey: 'duration'
  },
  {
    build: ctx => {
      if (ctx.busy || ctx.lastTurnEndedAt == null) {
        return null
      }

      const { glyphs } = ctx.t.design

      return {
        node: segment(glyphs, <IdleSince endedAt={ctx.lastTurnEndedAt} glyph={glyphs.idle} />, ctx.t.color.muted),
        reserve: stringWidth(`${glyphs.idle} `) + MAX_DURATION_WIDTH
      }
    },
    field: null,
    id: 'idle',
    segsKey: 'duration'
  },
  {
    build: ctx => {
      const compressions = typeof ctx.usage.compressions === 'number' ? ctx.usage.compressions : 0

      if (compressions <= 0) {
        return null
      }

      const color =
        compressions >= 10 ? ctx.t.color.error : compressions >= 5 ? ctx.t.color.warn : ctx.t.color.muted

      return {
        node: segment(ctx.t.design.glyphs, <Text color={color}>cmp {compressions}</Text>, ctx.t.color.muted),
        reserve: bodyWidth(ctx.t.design.glyphs, `cmp ${compressions}`)
      }
    },
    field: 'compressions',
    id: 'compressions',
    segsKey: 'compressions'
  },
  {
    build: ctx => {
      const pct = ctx.usage.cache_hit_pct

      if (typeof pct !== 'number') {
        return null
      }

      const color = pct >= 70 ? ctx.t.color.statusGood : pct >= 40 ? ctx.t.color.statusWarn : ctx.t.color.muted
      const text = `${ctx.t.design.glyphs.cache} ${pct}%`

      return {
        node: segment(ctx.t.design.glyphs, <Text color={color}>{text}</Text>, ctx.t.color.muted),
        reserve: stringWidth(text)
      }
    },
    field: 'cache_hit',
    id: 'cache_hit',
    segsKey: 'cacheHit'
  },
  {
    build: ctx => {
      const latency = ctx.usage.avg_latency_s

      if (typeof latency !== 'number') {
        return null
      }

      const text = `${ctx.t.design.glyphs.latency} ${latency.toFixed(1)}s`

      return {
        node: segment(ctx.t.design.glyphs, text, ctx.t.color.muted),
        reserve: stringWidth(text)
      }
    },
    field: 'latency',
    id: 'latency',
    segsKey: 'latency'
  },
  {
    build: ctx => {
      const tps = ctx.usage.avg_tps

      if (typeof tps !== 'number') {
        return null
      }

      const text = `${ctx.t.design.glyphs.tps} ${Math.round(tps)} t/s`

      return {
        node: segment(ctx.t.design.glyphs, text, ctx.t.color.muted),
        reserve: stringWidth(text)
      }
    },
    field: 'tps',
    id: 'tps',
    segsKey: 'tps'
  },
  {
    build: ctx => {
      const label = ctx.voiceLabel

      if (!label) {
        return null
      }

      const tone = ctx.voiceTone ?? 'idle'
      const glyph =
        tone === 'rec' ? ctx.t.design.glyphs.bullet : tone === 'stt' ? ctx.t.design.glyphs.focus : ''
      const text = glyph ? `${glyph} ${label}` : label
      const color = tone === 'rec' ? ctx.t.color.error : tone === 'stt' ? ctx.t.color.warn : ctx.t.color.muted

      return {
        node: segment(ctx.t.design.glyphs, text, color),
        reserve: stringWidth(text)
      }
    },
    field: 'voice',
    id: 'voice',
    segsKey: 'voice'
  },
  {
    build: ctx => {
      if (ctx.liveSessionCount <= 0) {
        return null
      }

      const text = statusSessionCountLabel(ctx.liveSessionCount)
      const clickable = !!ctx.onSessionCountClick

      return {
        node: clickable ? (
          <Box flexShrink={0} onClick={() => ctx.onSessionCountClick?.()}>
            <Text color={ctx.t.color.accent}>
              {ctx.t.design.glyphs.separator} {text}
            </Text>
          </Box>
        ) : (
          <Text color={ctx.t.color.muted}>
            {ctx.t.design.glyphs.separator} {text}
          </Text>
        ),
        reserve: stringWidth(text)
      }
    },
    field: null,
    id: 'session_count'
  },
  {
    build: ctx => {
      if (ctx.bgCount <= 0) {
        return null
      }

      return {
        node: segment(ctx.t.design.glyphs, `${ctx.bgCount} bg`, ctx.t.color.muted),
        reserve: stringWidth(`${ctx.bgCount} bg`)
      }
    },
    field: 'bg_tasks',
    id: 'bg',
    segsKey: 'bg'
  },
  {
    build: ctx => {
      if (ctx.subagentCount <= 0) {
        return null
      }

      const text = `${ctx.t.design.glyphs.chain} ${ctx.subagentCount}`

      return {
        node: segment(ctx.t.design.glyphs, text, ctx.t.color.muted),
        reserve: stringWidth(text)
      }
    },
    field: 'bg_subagents',
    id: 'subagents',
    segsKey: 'subagents'
  },
  {
    build: ctx => {
      // Parked-background reassurance: a top-level delegate_task runs in the
      // background, so the turn ends (idle) while the subagent keeps working and
      // its result re-enters as a fresh turn later. Width-budgeted like every
      // tail segment, so it drops first where ⛓ already carries the signal.
      if (ctx.busy || ctx.subagentCount <= 0) {
        return null
      }

      const text =
        ctx.subagentCount === 1
          ? `${ctx.t.design.glyphs.resume} resumes when subagent finishes`
          : `${ctx.t.design.glyphs.resume} resumes when ${ctx.subagentCount} subagents finish`

      return {
        node: segment(ctx.t.design.glyphs, text, ctx.t.color.muted, { dim: true }),
        reserve: stringWidth(text)
      }
    },
    field: null,
    id: 'resume_hint'
  },
  {
    build: ctx => {
      const micros = ctx.usage.dev_credits_spent_micros

      if (!DEV_CREDITS_MODE || typeof micros !== 'number') {
        return null
      }

      // micros→cents is allowed money math (display formatting) — never parseFloat
      // a *_usd. Signed: a mid-session top-up that raises remaining nets a negative Δ.
      const text = `Δ ${(micros / 10000).toFixed(1)}¢`

      return {
        node: segment(ctx.t.design.glyphs, text, ctx.t.color.accent),
        reserve: stringWidth(text)
      }
    },
    field: null,
    id: 'dev_credits'
  }
]

export const STATUS_SEGMENT_IDS: string[] = STATUS_SEGMENTS.map(s => s.id)

const BY_ID = new Map(STATUS_SEGMENTS.map(spec => [spec.id, spec]))

/**
 * Apply a skin's `tui.status_bar.segments` to the built-in order.
 *
 * `null` (unset) keeps the built-in order and every segment. An explicit list
 * is both the order and the allowlist — unknown ids are ignored rather than
 * fatal, so a skin written for a newer build still renders.
 */
export const resolveStatusSegments = (design: Design | undefined): StatusSegmentSpec[] => {
  const ids = design?.statusBar.segments

  if (!ids || ids.length === 0) {
    return STATUS_SEGMENTS
  }

  const resolved = ids.map(id => BY_ID.get(id)).filter((spec): spec is StatusSegmentSpec => !!spec)

  return resolved.length > 0 ? resolved : STATUS_SEGMENTS
}
