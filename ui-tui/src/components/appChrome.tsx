import { Box, type ScrollBoxHandle, stringWidth, Text } from '@shiina/ink'
import { compactNumber } from '@shiina/shared/format'
import type { Usage } from '@shiina/shared/gateway-events'
import { useStore } from '@nanostores/react'
import { type ReactNode, type RefObject, Fragment, useEffect, useMemo, useRef, useState } from 'react'
import unicodeSpinners from 'unicode-animations'

import { $delegationState } from '../app/delegationStore.js'
import type { BatteryInfo, IndicatorStyle, Notice } from '../app/interfaces.js'
import { $isStatusRuleOccluded } from '../app/overlayStore.js'
import { $uiState } from '../app/uiStore.js'
import { useTurnSelector } from '../app/turnStore.js'
import { DEV_CREDITS_MODE } from '../config/env.js'
import { FACES } from '../content/faces.js'
import { VERBS } from '../content/verbs.js'
import { flankFill } from '../design.js'
import type { DesignGlyphs } from '../design.js'
import { fmtDuration } from '../domain/messages.js'
import { stickyPromptFromViewport } from '../domain/viewport.js'
import { buildSubagentTree, treeTotals, widthByDepth } from '../lib/subagentTree.js'
import { useScrollbarSnapshot, useViewportSnapshot } from '../lib/viewportStore.js'
import type { Theme } from '../theme.js'
import type { Msg } from '../types.js'

import { scrollbarColors } from './overlayPrimitives.js'
import { MAX_DURATION_WIDTH, resolveStatusSegments, type StatusSegmentCtx } from './statusSegments.js'

const FACE_TICK_MS = 2500
const HEART_COLORS = ['#ff5fa2', '#ff4d6d']

// Keep verb segment width stable so status-bar content to the right doesn't
// jitter when the ticker rotates between short/long verbs.
export const VERB_PAD_LEN = VERBS.reduce((max, v) => Math.max(max, v.length), 0) + 1 // + ellipsis
export const padVerb = (verb: string) => `${verb}…`.padEnd(VERB_PAD_LEN, ' ')

// Compact alternates for the `emoji` and `ascii` indicator styles.
// Each entry is a fixed-width (display-width) glyph.
const EMOJI_FRAMES = ['★ ', '🌀', '🤔', '✨', '🍵', '🔮']
const ASCII_FRAMES = ['|', '/', '-', '\\']

// Faster tick for spinner-style indicators — they read as motion only
// at frame rates closer to their authored interval.
const SPINNER_TICK_MS = 100

interface IndicatorRender {
  frame: string
  intervalMs: number
  // When false, FaceTicker hides the rotating verb and just shows the
  // glyph + duration.  Lets `unicode` stay minimal while the other
  // styles keep the verb-rotation flavour users associate with the
  // running… status.
  showVerb: boolean
}

const renderIndicator = (style: IndicatorStyle, tick: number): IndicatorRender => {
  if (style === 'kaomoji') {
    return { frame: FACES[tick % FACES.length] ?? '', intervalMs: FACE_TICK_MS, showVerb: false }
  }

  if (style === 'emoji') {
    return {
      frame: EMOJI_FRAMES[tick % EMOJI_FRAMES.length] ?? '★ ',
      intervalMs: SPINNER_TICK_MS * 6,
      showVerb: false
    }
  }

  if (style === 'ascii') {
    return {
      frame: ASCII_FRAMES[tick % ASCII_FRAMES.length] ?? '|',
      intervalMs: SPINNER_TICK_MS,
      showVerb: false
    }
  }

  // 'unicode' — braille spinner (fixed 1-col).  Authored interval is
  // ~80ms; honour it but bound below at a safe minimum so React
  // re-renders stay reasonable.  This style is for users who want
  // the cleanest possible status, so no verb rotation either.
  const spinner = unicodeSpinners.braille
  const frame = spinner.frames[tick % spinner.frames.length] ?? '⠋'

  return { frame, intervalMs: Math.max(SPINNER_TICK_MS, spinner.interval), showVerb: false }
}

// `FACES` / `EMOJI_FRAMES` are static, so measure their widest glyph once at
// module load instead of rescanning on every status render.
const KAOMOJI_FRAME_WIDTH = FACES.reduce((max, f) => Math.max(max, stringWidth(f)), 1)
const EMOJI_FRAME_WIDTH = EMOJI_FRAMES.reduce((max, f) => Math.max(max, stringWidth(f)), 1)

const indicatorFrameWidth = (style: IndicatorStyle): number => {
  if (style === 'kaomoji') {
    return KAOMOJI_FRAME_WIDTH
  }

  if (style === 'emoji') {
    return EMOJI_FRAME_WIDTH
  }

  // 'ascii' and 'unicode' are single-column glyphs.
  return 1
}

// Display width to reserve for the busy indicator so its verb + elapsed-time
// tail can't shove the model off-screen on narrow terminals. Style-aware:
// `unicode` is a bare 1-col braille spinner with no verb, while kaomoji/emoji/
// ascii add a fixed-width verb; any style adds a bounded elapsed-time tail.
// Mirrors FaceTicker's `frame + verbSegment + durationSegment` layout.
export const busyIndicatorWidth = (style: IndicatorStyle, hasDuration: boolean, dotSeparator: string): number => {
  const { showVerb } = renderIndicator(style, 0)
  const verb = showVerb ? 1 + VERB_PAD_LEN : 0
  // The separator plus the bounded clock (e.g. `59m 59s`).
  const duration = hasDuration ? stringWidth(dotSeparator) + MAX_DURATION_WIDTH : 0

  return indicatorFrameWidth(style) + verb + duration
}

function FaceTicker({
  color,
  dotSeparator,
  startedAt,
  style,
  verbOverride
}: {
  color: string
  dotSeparator: string
  startedAt?: null | number
  style: IndicatorStyle
  verbOverride?: string
}) {
  const [tick, setTick] = useState(() => Math.floor(Math.random() * 1000))
  const [verbTick, setVerbTick] = useState(() => Math.floor(Math.random() * VERBS.length))
  const [now, setNow] = useState(() => Date.now())
  const isOccluded = useStore($isStatusRuleOccluded)

  // Pre-compute cadence + verb-visibility for the active style so an
  // `/indicator` switch re-arms the interval (and skips the verb timer
  // for verb-less styles like `unicode`) without leaving the previous
  // timer dangling. A frozen override (idle compaction) always shows the
  // verb so "compacting…" is visible even in unicode style (#97239).
  const { intervalMs, showVerb } = renderIndicator(style, 0)
  const freezeVerb = Boolean(verbOverride)
  const displayVerb = freezeVerb || showVerb

  useEffect(() => {
    // An overlay is painted OVER the status rule (the modal widget slot, or a
    // floating panel growing up over the top rule), so every tick below is a
    // re-render nobody can see — in an Ink TUI that churn reads as the dialog
    // tearing.  Arm nothing while occluded.  The effect re-runs when the rule
    // is revealed again and re-seeds `now` from the wall clock, so the elapsed
    // read-out resumes live rather than frozen at the moment it was covered.
    // See `$isStatusRuleOccluded` for why this is NOT `$isBlocked`.
    if (isOccluded) {
      return
    }

    setNow(Date.now())

    const glyph = setInterval(() => setTick(n => n + 1), intervalMs)
    const clock = setInterval(() => setNow(Date.now()), 1000)
    // Verb timer is gated on `displayVerb` — `unicode` style hides the verb
    // entirely, so cycling `verbTick` would be an avoidable re-render. A
    // frozen override does not rotate.
    const verb = displayVerb && !freezeVerb ? setInterval(() => setVerbTick(n => n + 1), FACE_TICK_MS) : null

    return () => {
      clearInterval(glyph)
      clearInterval(clock)

      if (verb !== null) {
        clearInterval(verb)
      }
    }
  }, [displayVerb, freezeVerb, intervalMs, isOccluded])

  const { frame } = renderIndicator(style, tick)
  const verb = verbOverride ?? VERBS[verbTick % VERBS.length] ?? ''
  const verbSegment = displayVerb ? ` ${padVerb(verb)}` : ''
  // Leading space keeps a gap between the frame and the duration when the
  // verb segment is hidden (e.g. `unicode` spinner style).  When the verb
  // IS shown, its trailing padding already provides the gap, so the extra
  // space is harmless.
  const durationSegment = startedAt ? `${dotSeparator}${fmtDuration(now - startedAt)}` : ''

  return (
    <Text color={color}>
      {frame}
      {verbSegment}
      {durationSegment}
    </Text>
  )
}

function ctxBarColor(pct: number | undefined, t: Theme) {
  if (pct == null) {
    return t.color.muted
  }

  if (pct >= 95) {
    return t.color.statusCritical
  }

  if (pct > 80) {
    return t.color.statusBad
  }

  if (pct >= 50) {
    return t.color.statusWarn
  }

  return t.color.statusGood
}

// Colour the battery read-out by its (Python-computed) category. Inverted vs
// the context bar — a full battery is "good", an empty one "critical".
function batteryColor(info: BatteryInfo, t: Theme): string {
  if (info.category === 'good') {
    return t.color.statusGood
  }

  if (info.category === 'warn') {
    return t.color.statusWarn
  }

  if (info.category === 'bad') {
    return t.color.statusBad
  }

  if (info.category === 'critical') {
    return t.color.statusCritical
  }

  return t.color.muted
}

// Compact battery label: a bolt while charging, else a battery glyph.
// Renders `--` for an unknown percent so a null can never surface as "null%".
function batteryLabel(info: BatteryInfo): string {
  return `${info.plugged ? '⚡' : '🔋'} ${info.percent ?? '--'}%`
}

// Colour a credits notice by its level. The notice TEXT already carries its
// own glyph (⚠ • ✕ ✓) from the Python policy — we only tint it here, never
// prepend another glyph. `success` maps to the theme's green status colour.
function noticeColor(level: Notice['level'], t: Theme): string {
  if (level === 'error') {
    return t.color.error
  }

  if (level === 'warn') {
    return t.color.warn
  }

  if (level === 'success') {
    return t.color.statusGood
  }

  // 'info' / undefined — keep it readable but understated.
  return t.color.accent
}

function ctxBar(pct: number | undefined, glyphs: DesignGlyphs, w = 10) {
  const p = Math.max(0, Math.min(100, pct ?? 0))
  const filled = Math.round((p / 100) * w)

  return glyphs.barFill.repeat(filled) + glyphs.barEmpty.repeat(w - filled)
}

// `minLeftContent` is the display width of the high-priority left segments
// (status indicator + model + context). Reserving it makes the cwd/branch
// segment on the right yield FIRST on narrow terminals, instead of squeezing
// the loading indicator and model down to nothing.
export function statusRuleWidths(cols: number, cwdLabel: string, minLeftContent = 0) {
  const width = Math.max(1, Math.floor(cols || 1))
  const desiredSeparatorWidth = width >= 24 ? 3 : 1
  const baseMinLeft = width >= 24 ? 8 : 1
  // Never reserve more than the terminal width; never less than the historical
  // floor. With the default `minLeftContent = 0` this is identical to the old
  // behaviour, so callers that don't pass content are unaffected.
  const minLeftWidth = Math.min(width, Math.max(baseMinLeft, Math.floor(minLeftContent)))
  const maxRightWidth = Math.max(0, width - desiredSeparatorWidth - minLeftWidth)

  if (!cwdLabel || maxRightWidth <= 0) {
    return { leftWidth: width, rightWidth: 0, separatorWidth: 0 }
  }

  const rightWidth = Math.max(0, Math.min(stringWidth(cwdLabel), maxRightWidth))
  const separatorWidth = rightWidth > 0 ? desiredSeparatorWidth : 0
  const leftWidth = Math.max(1, width - separatorWidth - rightWidth)

  return { leftWidth, rightWidth, separatorWidth }
}

// Progressive disclosure for the status rule's lower-priority tail segments.
// As the terminal narrows we shed the least important pieces first (cost →
// bg → voice → compressions → duration → context bar), and below the bar
// breakpoint the context read-out collapses to a bare token count. Status and
// model are never gated here — they're guaranteed room by `statusRuleWidths`.
export interface StatusBarSegments {
  bar: boolean
  bg: boolean
  cacheHit: boolean
  compactCtx: boolean
  compressions: boolean
  duration: boolean
  latency: boolean
  subagents: boolean
  tps: boolean
  voice: boolean
}

export function statusBarSegments(cols: number): StatusBarSegments {
  const w = Math.max(1, Math.floor(cols || 1))

  return {
    compactCtx: w < 72,
    bar: w >= 72,
    duration: w >= 76,
    compressions: w >= 80,
    voice: w >= 84,
    bg: w >= 88,
    subagents: w >= 92,
    cacheHit: w >= 96,
    latency: w >= 104,
    tps: w >= 110
  }
}

function SpawnHud({ t }: { t: Theme }) {
  // Tight HUD that only appears when the session is actually fanning out.
  // Colour escalates to warn/error as depth or concurrency approaches the cap.
  const delegation = useStore($delegationState)
  const subagents = useTurnSelector(state => state.subagents)

  const tree = useMemo(() => buildSubagentTree(subagents), [subagents])
  const totals = useMemo(() => treeTotals(tree), [tree])

  if (!totals.descendantCount && !delegation.paused) {
    return null
  }

  const maxDepth = delegation.maxSpawnDepth
  const maxConc = delegation.maxConcurrentChildren
  const depth = Math.max(0, totals.maxDepthFromHere)
  const active = totals.activeCount

  // `max_concurrent_children` is a per-parent cap, not a global one.
  // `activeCount` sums every running agent across the tree and would
  // over-warn for multi-orchestrator runs.  The widest level of the tree
  // is a closer proxy to "most concurrent spawns that could be hitting a
  // single parent's slot budget".
  const widestLevel = widthByDepth(tree).reduce((a, b) => Math.max(a, b), 0)
  const depthRatio = maxDepth ? depth / maxDepth : 0
  const concRatio = maxConc ? widestLevel / maxConc : 0
  const ratio = Math.max(depthRatio, concRatio)

  const color = delegation.paused || ratio >= 1 ? t.color.error : ratio >= 0.66 ? t.color.warn : t.color.muted

  const pieces: string[] = []

  if (delegation.paused) {
    pieces.push('⏸ paused')
  }

  if (totals.descendantCount > 0) {
    const depthLabel = maxDepth ? `${depth}/${maxDepth}` : `${depth}`
    pieces.push(`d${depthLabel}`)

    if (active > 0) {
      // Label pairs the widest-level count (drives concRatio above) with
      // the total active count for context.  `W/cap` triggers the warn,
      // `+N` is everything else currently running across the tree.
      const extra = Math.max(0, active - widestLevel)
      const widthLabel = maxConc ? `${widestLevel}/${maxConc}` : `${widestLevel}`
      const suffix = extra > 0 ? `+${extra}` : ''
      pieces.push(`⚡${widthLabel}${suffix}`)
    }
  }

  const atCap = depthRatio >= 1 || concRatio >= 1

  return (
    <Text color={color}>
      {atCap ? `${t.design.glyphs.separator}${t.design.glyphs.alert} ` : t.design.glyphs.separator}
      {pieces.join(' ')}
    </Text>
  )
}

const effortLabel = (effort?: string) => {
  const value = String(effort ?? '')
    .trim()
    .toLowerCase()

  return value && value !== 'medium' && value !== 'normal' && value !== 'default' ? value : ''
}

const shortModelLabel = (model: string) =>
  model
    .split('/')
    .pop()!
    .replace(/^claude[-_]/, '')
    .replace(/^anthropic[-_]/, '')
    .replace(/[-_]/g, ' ')
    .replace(/\b(\d+)\s+(\d+)\b/g, '$1.$2')
    .trim()

const modelLabel = (model: string, effort?: string, fast?: boolean) =>
  [shortModelLabel(model), effortLabel(effort), fast ? 'fast' : ''].filter(Boolean).join(' ')

export function GoodVibesHeart({ tick, t }: { tick: number; t: Theme }) {
  const [active, setActive] = useState(false)
  const [color, setColor] = useState(t.color.accent)

  useEffect(() => {
    if (tick <= 0) {
      return
    }

    const palette = [t.color.error, t.color.warn, t.color.accent]
    setColor(palette[Math.floor(Math.random() * palette.length)]!)
    setActive(true)

    const id = setTimeout(() => setActive(false), 650)

    return () => clearTimeout(id)
  }, [t.color.accent, t.color.error, t.color.warn, tick])

  if (!active) {
    return null
  }

  return <Text color={color}>♥</Text>
}

export function StatusRule({
  battery,
  focusView,
  cwdLabel,
  cols,
  busy,
  compacting = false,
  status,
  statusBarFields = null,
  statusColor,
  model,
  modelFast,
  modelReasoningEffort,
  indicatorStyle = 'kaomoji',
  notice,
  usage,
  bgCount,
  lastTurnEndedAt,
  liveSessionCount,
  sessionTitle,
  sessionStartedAt,
  turnStartedAt,
  voiceLabel,
  onSessionCountClick,
  t
}: StatusRuleProps) {
  const pct = usage.context_percent ?? undefined
  const contextMark = usage.context_estimated ? '~' : ''
  const barColor = ctxBarColor(pct, t)
  const segs = statusBarSegments(cols)

  // display.status_bar.fields visibility gate (same key + names as the
  // classic CLI bar). null = user hasn't customized → everything shows.
  const ok = (name: string) => statusBarFields === null || statusBarFields.has(name)

  // On narrow terminals the context read-out collapses to a bare token count
  // (`12k tok`) and the visual fill bar is dropped entirely.
  //
  // The value itself is the provider-quota read-out when one is cached
  // (classic-CLI parity: `5h 0% (1m) · w 17% (13h 33m)`, from
  // `shiina_cli.status_bar_limits.format_limits_compact`), else the context
  // window read-out. Only the value swaps — the bar and its % below keep
  // rendering the window's own numbers.
  const ctxSlotOn = ok('context_detail') || ok('context_pct')
  const limitsLabel =
    ctxSlotOn && !segs.compactCtx && typeof usage.limits_label === 'string' ? usage.limits_label.trim() : ''
  const windowLabel = usage.context_max
    ? segs.compactCtx
      ? `${contextMark}${compactNumber(usage.context_used ?? 0)} tok`
      : `${contextMark}${compactNumber(usage.context_used ?? 0)}/${compactNumber(usage.context_max ?? 0)}`
    : (usage.total ?? 0) > 0
      ? `${compactNumber(usage.total)} tok`
      : ''
  const ctxLabel = !ctxSlotOn ? '' : limitsLabel || windowLabel

  const bar = !segs.compactCtx && usage.context_max && ok('context_pct') ? ctxBar(pct, t.design.glyphs) : ''
  const modelText = modelLabel(model, modelReasoningEffort, modelFast)

  // Battery read-out — the first (pinned) status-bar element when enabled.
  const showBattery = !!battery && battery.available && battery.percent != null && ok('battery')
  const batteryText = showBattery ? batteryLabel(battery!) : ''
  const batteryColorVal = showBattery ? batteryColor(battery!, t) : ''
  const batteryWidth = showBattery ? stringWidth(`${batteryText}${t.design.glyphs.separator}`) : 0

  // A credits notice replaces the status/verb slot, but only when idle —
  // while busy the FaceTicker always wins (R1 render priority). The notice
  // text carries its own glyph; we only tint it (R1) and let it shrink (R3-M7).
  const showNotice = !busy && !!notice?.text
  // The notice slot is shrinkable (flexShrink={1}, truncate-end), so reserve
  // only a small bounded width for it in the essentials budget — enough that
  // a short notice never gets crushed, but a long one ellipsizes instead of
  // shoving `model │ ctx` off-screen (R3-M7). Cap at the notice's own width
  // so short notices reserve exactly what they need.
  const NOTICE_RESERVE_MAX = 24
  const noticeReserve = showNotice ? Math.min(stringWidth(notice!.text), NOTICE_RESERVE_MAX) : 0

  // Width of the must-keep left segments (indicator + model + context). They
  // are pinned (never shrink) and reserved so the cwd/branch on the right
  // yields first. The busy face width depends on the active /indicator style
  // (kaomoji is wide + verb; unicode is a bare 1-col spinner). When a notice
  // occupies the slot it reserves only `noticeReserve` (it shrinks/truncates).
  const slotWidth = busy
    ? busyIndicatorWidth(indicatorStyle, turnStartedAt != null, t.design.glyphs.dotSeparator)
    : showNotice
      ? noticeReserve
      : stringWidth(status)

  // Model is pinned left; the usage readout (ctx number + bar + %) is pinned
  // on the RIGHT ahead of the title/cwd label, so it is reserved out of the
  // right side (see usageRightText below) instead of the left essentials.
  const essentialWidth =
    stringWidth(t.design.glyphs.statusHead) +
    batteryWidth +
    slotWidth +
    stringWidth(t.design.glyphs.separator) +
    stringWidth(modelText)

  const rightLabel = sessionTitle && ok('title') ? ` ${sessionTitle} ` : cwdLabel
  // Usage readout pinned on the right, ahead of the title/cwd label:
  // `│ 73.2k/1M │ [bar] 7%`. Measured into the right reservation (not the
  // tail budget) so the label yields first on narrow terminals while usage
  // stays visible. Previously the bar consumed left tail budget via `fits`.
  const usageBarText = !!bar ? `[${bar}]${pct != null ? ` ${contextMark}${pct}%` : ''}` : ''
  const sep = t.design.glyphs.separator
  const usageRightText = `${ctxLabel ? `${sep}${ctxLabel}` : ''}${usageBarText ? `${sep}${usageBarText}` : ''}`
  const { leftWidth, rightWidth, separatorWidth } = statusRuleWidths(
    cols,
    `${usageRightText}${rightLabel}`,
    essentialWidth
  )

  // Whole-segment progressive disclosure for the tail: a segment renders only
  // if it fits in the space left after the pinned essentials, evaluated in
  // descending priority order — bar, duration, compressions, voice, session
  // count, bg, cost. Lower-priority segments drop first and nothing truncates
  // mid-segment, so status/model/context are never crushed.
  const SEP = stringWidth(sep)
  let tailBudget = Math.max(0, leftWidth - essentialWidth)

  const fits = (w: number) => {
    if (tailBudget >= w) {
      tailBudget -= w

      return true
    }

    return false
  }

  // The tail is data, not branches: `statusSegments.tsx` owns each segment
  // (text, colour, width charge, width-tier gate) and the skin's
  // `tui.status_bar.segments` owns the order. This loop is only the budget —
  // walk in order, charge each segment's columns, and drop whatever no longer
  // fits. Array order is therefore drop priority too: the last entries yield
  // first, so the pinned status/model/context read-outs are never crushed.
  const segmentCtx: StatusSegmentCtx = {
    bgCount,
    busy,
    focus: !!focusView,
    lastTurnEndedAt,
    liveSessionCount,
    onSessionCountClick,
    sessionStartedAt,
    subagentCount: typeof usage.active_subagents === 'number' ? usage.active_subagents : 0,
    t,
    usage,
    voiceLabel
  }

  const tailSegments: ReactNode[] = []

  for (const spec of resolveStatusSegments(t.design)) {
    // Width tier (progressive disclosure) and the classic CLI bar's field gate
    // are both declared by the segment, so a new segment cannot forget them.
    if (spec.segsKey && !segs[spec.segsKey]) {
      continue
    }

    if (spec.field && !ok(spec.field)) {
      continue
    }

    const view = spec.build(segmentCtx)

    if (!view) {
      continue
    }

    // Focus view is pinned on purpose: the user must never be in reduced-output
    // mode without seeing the badge, so it is not tail-budgeted.
    if (!spec.pinned && !fits(SEP + view.reserve)) {
      continue
    }

    tailSegments.push(<Fragment key={spec.id}>{view.node}</Fragment>)
  }

  return (
    <Box height={1}>
      <Box flexDirection="row" flexShrink={1} overflow="hidden" width={leftWidth}>
        {/* Leading pinned chrome: border + busy face / idle status. When a
            notice occupies the slot the status text is dropped — the notice
            renders as a separate shrinkable box below so a long notice
            ellipsizes instead of crushing model │ ctx (R3-M7). */}
        <Box flexDirection="row" flexShrink={0}>
          <Text color={t.color.border}>{t.design.glyphs.statusHead}</Text>
          {showBattery ? (
            <Text color={batteryColorVal}>
              {batteryText}
              <Text color={t.color.muted}>{sep}</Text>
            </Text>
          ) : null}
          {busy ? (
            <FaceTicker
              color={statusColor}
              dotSeparator={t.design.glyphs.dotSeparator}
              startedAt={turnStartedAt}
              style={indicatorStyle}
              verbOverride={compacting ? 'compacting' : undefined}
            />
          ) : showNotice ? null : (
            <Text color={statusColor} wrap="truncate-end">
              {status}
            </Text>
          )}
        </Box>
        {/* Notice slot — the only shrinkable left element (R3-M7). Sits in a
            flexShrink={1} box with truncate-end so it yields/ellipsizes
            before the pinned model │ ctx box ever clips. */}
        {showNotice ? (
          <Box flexDirection="row" flexShrink={1} overflow="hidden">
            <Text color={noticeColor(notice!.level, t)} wrap="truncate-end">
              {notice!.text}
            </Text>
          </Box>
        ) : null}
        {/* Pinned essentials — model never shrinks, always visible. Usage
            moved to the right box (usageRightText). */}
        <Box flexDirection="row" flexShrink={0}>
          {DEV_CREDITS_MODE ? (
            <Text color={t.color.warn} wrap="truncate-end">
              {' (dev credits)'}
            </Text>
          ) : null}
          <Text color={t.color.muted} wrap="truncate-end">
            {sep}
            {modelText}
          </Text>
        </Box>
        {tailSegments}
        {/* SpawnHud isn't part of the tail budget (its width is dynamic), so it
            renders last — any overflow truncates the HUD itself rather than the
            budgeted segments before it. It self-hides when no delegation runs. */}
        <SpawnHud t={t} />
      </Box>

      {rightWidth > 0 ? (
        <>
          {sessionTitle && separatorWidth >= stringWidth(` ${sessionTitle} `) + 2 ? (
            (() => {
              const titleW = stringWidth(` ${sessionTitle} `)
              const remainingSep = Math.max(0, separatorWidth - titleW)
              const leftDash = Math.floor(remainingSep / 2)
              const rightDash = remainingSep - leftDash
              const fill = (n: number) => flankFill(t.design.flank, t.design.borders.rule, n)
              return (
                <>
                  <Text color={t.color.border}>{fill(leftDash)}</Text>
                  <Text bold color={t.color.accent}>{` ${sessionTitle} `}</Text>
                  <Text color={t.color.border}>{fill(rightDash)}</Text>
                </>
              )
            })()
          ) : (
            <Text color={t.color.border}>{separatorWidth >= 3 ? ` ${t.design.borders.rule} ` : ' '}</Text>
          )}
          <Box flexDirection="row" flexShrink={0} width={rightWidth} overflow="hidden">
            {ctxLabel ? (
              <Box flexShrink={0}>
                <Text color={t.color.muted} wrap="truncate-end">
                  {sep}
                  {ctxLabel}
                </Text>
              </Box>
            ) : null}
            {usageBarText ? (
              <Box flexShrink={0}>
                <Text color={t.color.muted} wrap="truncate-end">
                  {sep}
                  <Text color={barColor}>[{bar}]</Text>
                  {pct != null ? <Text color={barColor}>{` ${contextMark}${pct}%`}</Text> : null}
                </Text>
              </Box>
            ) : null}
            <Box flexShrink={1} overflow="hidden">
              <Text bold={!!sessionTitle} color={sessionTitle ? t.color.accent : t.color.label} wrap="truncate-end">
                {rightLabel}
              </Text>
            </Box>
          </Box>
        </>
      ) : null}
    </Box>
  )
}

export function FloatBox({ children, color }: { children: ReactNode; color: string }) {
  // The border language comes from the active design. Read from the store rather
  // than threading a prop: FloatBox is mounted from a dozen overlay sites, and a
  // purely presentational wrapper should not force every caller to carry `t`.
  const theme = useStore($uiState).theme

  return (
    <Box
      alignSelf="flex-start"
      borderColor={color}
      borderStyle={theme.design.borders.alert}
      flexDirection="column"
      marginTop={1}
      opaque
      paddingX={theme.design.spacing.insetPadX}
    >
      {children}
    </Box>
  )
}

export function StickyPromptTracker({ messages, offsets, scrollRef, onChange }: StickyPromptTrackerProps) {
  const { atBottom, bottom, top } = useViewportSnapshot(scrollRef)
  const text = stickyPromptFromViewport(messages, offsets, top, bottom, atBottom)

  useEffect(() => onChange(text), [onChange, text])

  return null
}

export function TranscriptScrollbar({ scrollRef, t }: TranscriptScrollbarProps) {
  const [hover, setHover] = useState(false)
  const [grab, setGrab] = useState<number | null>(null)
  const grabRef = useRef<number | null>(null)
  const { scrollHeight: total, top: pos, viewportHeight: vp } = useScrollbarSnapshot(scrollRef)

  if (!vp) {
    return <Box width={1} />
  }

  const s = scrollRef.current
  const scrollable = total > vp
  const thumb = scrollable ? Math.max(1, Math.round((vp * vp) / total)) : vp
  const travel = Math.max(1, vp - thumb)
  const thumbTop = scrollable ? Math.round((pos / Math.max(1, total - vp)) * travel) : 0
  const { thumb: thumbColor, track: trackColor } = scrollbarColors(t, hover, grab !== null)
  const track = t.design.glyphs.railVertical
  const bar = t.design.glyphs.scrollThumb

  const jump = (row: number, offset: number) => {
    if (!s || !scrollable) {
      return
    }

    s.scrollTo(Math.round((Math.max(0, Math.min(travel, row - offset)) / travel) * Math.max(0, total - vp)))
  }

  return (
    <Box
      flexDirection="column"
      onMouseDown={(e: { localRow?: number }) => {
        const row = Math.max(0, Math.min(vp - 1, e.localRow ?? 0))
        const off = row >= thumbTop && row < thumbTop + thumb ? row - thumbTop : Math.floor(thumb / 2)

        grabRef.current = off
        setGrab(off)
        jump(row, off)
      }}
      onMouseDrag={(e: { localRow?: number }) =>
        jump(Math.max(0, Math.min(vp - 1, e.localRow ?? 0)), grabRef.current ?? Math.floor(thumb / 2))
      }
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onMouseUp={() => {
        grabRef.current = null
        setGrab(null)
      }}
      width={1}
    >
      {/* Nothing to scroll → draw nothing (the width={1} Box still reserves
          the column). Drawn-blank cells composite to a black bar on
          transparent terminals — same class as the removed opaque fills. */}
      {!scrollable ? null : (
        <>
          {thumbTop > 0 ? (
            <Text color={trackColor}>{`${`${track}\n`.repeat(Math.max(0, thumbTop - 1))}${track}`}</Text>
          ) : null}
          {thumb > 0 ? (
            <Text color={thumbColor}>{`${`${bar}\n`.repeat(Math.max(0, thumb - 1))}${bar}`}</Text>
          ) : null}
          {vp - thumbTop - thumb > 0 ? (
            <Text color={trackColor}>{`${`${track}\n`.repeat(Math.max(0, vp - thumbTop - thumb - 1))}${track}`}</Text>
          ) : null}
        </>
      )}
    </Box>
  )
}

interface StatusRuleProps {
  battery?: BatteryInfo | null
  // Focus view (/focus) badge — display-only reduced-output indicator.
  focusView?: boolean
  bgCount: number
  lastTurnEndedAt?: null | number
  liveSessionCount: number
  busy: boolean
  // Context compaction in progress — FaceTicker freezes on "compacting".
  compacting?: boolean
  cols: number
  cwdLabel: string
  model: string
  modelFast?: boolean
  modelReasoningEffort?: string
  indicatorStyle?: IndicatorStyle
  notice?: Notice | null
  sessionStartedAt?: null | number
  sessionTitle?: string
  status: string
  // display.status_bar.fields — segment visibility filter shared with the
  // classic CLI bar. null = defaults (everything shows).
  statusBarFields?: null | ReadonlySet<string>
  statusColor: string
  t: Theme
  turnStartedAt?: null | number
  usage: Usage
  voiceLabel?: string
  /** Drives the voice readout's marker glyph + colour; the glyph is rendered by
   *  statusSegments from the design's vocabulary, not baked into the label. */
  voiceTone?: 'idle' | 'rec' | 'stt'
  onSessionCountClick?: () => void
}

interface StickyPromptTrackerProps {
  messages: readonly Msg[]
  offsets: ArrayLike<number>
  onChange: (text: string) => void
  scrollRef: RefObject<ScrollBoxHandle | null>
}

interface TranscriptScrollbarProps {
  scrollRef: RefObject<ScrollBoxHandle | null>
  t: Theme
}
