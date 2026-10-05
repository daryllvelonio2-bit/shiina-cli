// StreamingMd — incremental markdown renderer for in-flight assistant text.
//
// Rendering <Md text={full}/> per delta re-tokenizes the whole message every
// time (O(total) × deltas). The prior stable-prefix split fixed the per-delta
// cost but not the per-block cliff: each advanced boundary re-tokenized the
// entire prefix from scratch — O(blocks²) — plus an O(total) fence rescan.
//
// This is fully incremental. A forward scanner keeps fence/math state + scan
// position in a ref across deltas, so each delta touches only newly-arrived
// complete lines. Settled top-level blocks (split on "\n\n" outside a fence)
// are frozen into an append-only array, each its own <Md> memoized on text
// that never changes — every block tokenizes exactly once. Only the in-flight
// tail re-parses per delta (O(tail)).
//
// The scanner reads the UNTRIMMED reply and the render window is applied at
// render time (`firstVisibleBlock` + a clipped tail). Scanning the trimmed
// window instead looked like a brand-new document on every delta — the window
// slides once the reply passes LIVE_RENDER_MAX_CHARS — which reset the scanner
// and re-parsed the whole window (~130 ms at the 16 KB cap) per delta: the
// long-reply stutter. A front-trim now costs nothing because the dropped head
// was already scanned; only a genuine restart (new turn, reasoning→answer)
// resets, and then no more often than the OLD guard did.
//
// Invariants that keep it correct:
//   · Only newline-terminated lines are scanned; a partial trailing line may
//     yet become a fence opener, so it stays in the tail.
//   · Blank-line boundaries can't be retroactively merged (a setext underline
//     only binds the contiguous line above it, never across a committed "\n\n").
//   · An unmatched `$$` / `\[` opener is treated as open forever — more
//     conservative than markdown.tsx's full-text fallback, because a committed
//     block is frozen and can't be un-decided once the closer streams in.
//   · State only advances (idempotent under StrictMode).
//   · Pruning only ever drops settled blocks the window has passed, so block
//     ordinals (React keys) stay stable for everything still rendered.
//
// Layout: the <Md> subtrees MUST stack in a column — the messageLine.tsx
// parent is a default row Box, so bare siblings render side-by-side.

import { Box, Text } from '@shiina/ink'
import { memo, useRef, type ReactNode } from 'react'

import { useTurnSelector } from '../app/turnStore.js'
import type { Theme } from '../theme.js'

import { Md } from './markdown.js'

/** How many settled blocks stay resident after the window has passed them. */
const SETTLED_BLOCK_KEEP = 256

/** Longest provisional line parsed as markdown; longer lines render as text so a
 *  single huge line cannot dominate the per-delta cost. */
const PROVISIONAL_MD_MAX = 400

const EMPTY_LINES: string[] = []

export interface StreamScanState {
  /** Settled top-level block strings, in order. Append-only. */
  blocks: string[]
  /** Absolute end offset of each committed block (aligned with `blocks`). */
  blockEnds: number[]
  /** Leading blocks pruned out of the render window (blocks.length + this = total). */
  droppedBlocks: number
  /** Inside an unclosed ``` / ~~~ fence at the scan position. */
  codeOpen: boolean
  /** Non-null inside an unclosed display-math block at the scan position. */
  mathOpener: '$$' | '\\[' | null
  /** Prefix whose complete lines have been scanned (kept as text so the reset
   *  guard can confirm the scanned region — and thus fence state — still holds). */
  scanned: string
  /** Length of the committed prefix (blocks.join('').length). */
  settledLen: number
}

export const createScanState = (): StreamScanState => ({
  blocks: [],
  blockEnds: [],
  codeOpen: false,
  droppedBlocks: 0,
  mathOpener: null,
  scanned: '',
  settledLen: 0
})

// Fold one complete line into the fence/math state: ``` / ~~~ toggle the code
// fence; `$$` / `\[` open display math unless the line also closes it; closers
// count only against a pending opener; math inside an open code fence is inert.
const applyLine = (state: StreamScanState, line: string) => {
  if (/^(?:`{3,}|~{3,})/.test(line)) {
    state.codeOpen = !state.codeOpen

    return
  }

  if (state.codeOpen) {
    return
  }

  if (!state.mathOpener) {
    if (/^\$\$/.test(line) && !(line.length >= 4 && /\$\$$/.test(line))) {
      state.mathOpener = '$$'
    } else if (/^\\\[/.test(line) && !/\\\]$/.test(line)) {
      state.mathOpener = '\\['
    }
  } else if (state.mathOpener === '$$' && /\$\$$/.test(line)) {
    state.mathOpener = null
  } else if (state.mathOpener === '\\[' && /\\\]$/.test(line)) {
    state.mathOpener = null
  }
}

// Consume newly-arrived complete lines, committing a settled block at every
// "\n\n" outside a fence. Whitespace-only runs stay with the next block, never
// committed as empty <Md>s. Mutates `state`; re-calling with the same text is
// a no-op (idempotent).
export const advanceScan = (text: string, state: StreamScanState) => {
  const start = state.scanned.length

  let i = start

  while (i < text.length) {
    const nl = text.indexOf('\n', i)

    if (nl < 0) {
      break // partial trailing line — could still open a fence; keep in tail
    }

    if (nl === i) {
      // Second half of a "\n\n" outside any fence → prior text is a block.
      if (i > 0 && !state.codeOpen && !state.mathOpener) {
        const block = text.slice(state.settledLen, nl + 1)

        if (/\S/.test(block)) {
          state.blocks.push(block)
          state.blockEnds.push(nl + 1)
          state.settledLen = nl + 1
        }
      }
    } else {
      applyLine(state, text.slice(i, nl).trim())
    }

    i = nl + 1
  }

  if (i > start) {
    state.scanned += text.slice(start, i)
  }
}

// Index just past the last committed boundary, or -1 if nothing has settled.
// Thin wrapper over the scanner for boundary-semantics tests.
export const findStableBoundary = (text: string) => {
  const state = createScanState()

  advanceScan(text, state)

  return state.settledLen > 0 ? state.settledLen : -1
}

// The frozen settled prefix behind a memo boundary. `blocks` is append-only
// and mutated in place, so its reference is stable across appends; `count` is
// the ONLY prop that changes, and only when a new block commits. An append
// that settles nothing therefore leaves this whole subtree untouched, and one
// that settles a single block renders ONLY the block that just arrived — the
// already-settled <Md> elements are reused by identity, so React never even
// re-creates (let alone re-renders) the frozen prefix.
const SettledBlocks = memo(function SettledBlocks({
  blocks,
  cols,
  compact,
  count,
  firstOrdinal,
  from,
  t
}: SettledBlocksProps) {
  const cacheRef = useRef<{
    cols?: boolean | number
    compact?: boolean
    count: number
    from: number
    nodes: ReactNode[]
    t: Theme
  }>({ cols, compact, count: 0, from, nodes: [], t })

  const cache = cacheRef.current

  // Render options, a prune (count/firstOrdinal moved back) or a window slide
  // (from moved forward) invalidates the element list. Blocks themselves stay
  // cached: each <Md> is keyed by its own text in markdown.tsx's LRU, so a
  // rebuild after a slide re-uses the parsed nodes.
  if (cache.t !== t || cache.cols !== cols || cache.compact !== compact || cache.count > count || cache.from > from) {
    cache.nodes = []
    cache.from = from
    cache.count = from
    cache.t = t
    cache.cols = cols
    cache.compact = compact
  }

  if (from > cache.from) {
    // The window slid: drop the leading elements (ordinals before `from`).
    cache.nodes = cache.nodes.slice(from - cache.from)
    cache.from = from
  }

  if (count > cache.count) {
    for (let ord = cache.count; ord < count; ord++) {
      cache.nodes.push(<Md cols={cols} compact={compact} key={ord} t={t} text={blocks[ord - firstOrdinal]!} />)
    }

    // New array identity so React reconciles the added child; the reused
    // element objects let the frozen prefix skip re-render entirely.
    cache.nodes = [...cache.nodes]
    cache.count = count
  }

  return <>{cache.nodes}</>
})

/**
 * Drop settled blocks that fell out of the render window.
 *
 * Blocks are only ever appended, so the only reclaimable memory is the head —
 * and only the head that the window has already passed. Keeps `blockEnds`
 * aligned and records how many ordinals went, so keys stay stable.
 */
export const pruneStreamBlocks = (state: StreamScanState, windowStart: number, keep = SETTLED_BLOCK_KEEP): void => {
  let drop = 0

  while (state.blocks.length - drop > keep && (state.blockEnds[drop] ?? Number.POSITIVE_INFINITY) <= windowStart) {
    drop++
  }

  if (drop === 0) {
    return
  }

  state.blocks.splice(0, drop)
  state.blockEnds.splice(0, drop)
  state.droppedBlocks += drop
}

/** Ordinal of the first settled block intersecting the render window. */
export const firstVisibleBlock = (state: StreamScanState, windowStart: number): number => {
  let i = 0

  while (i < state.blockEnds.length && state.blockEnds[i]! <= windowStart) {
    i++
  }

  return state.droppedBlocks + i
}

/**
 * The in-flight (uncommitted) tail, rendered provisional-line-by-line.
 *
 * A tail cannot be committed as a block until a blank line closes it, so a reply
 * with a long unbroken paragraph, list or fence would otherwise re-parse the whole
 * uncommitted region on every delta — up to the full 16 KB window, ~130 ms, which
 * is the long-reply stutter. Instead each settled *line* is rendered once and then
 * left alone: a short line goes through `<Md>` (whose cross-instance LRU keys on
 * the line text, so it parses exactly once and still gets headings, bullets and
 * inline style); a very long line renders as plain text so a single 5 KB line
 * cannot become the new cliff. Both are provisional — the moment the block settles
 * the scanner commits it and the frozen `<Md>` block replaces the lines, so any
 * construct that spans lines (a fence, a table) snaps into its real form at the
 * next blank line.
 */
const ProvisionalTail = memo(function ProvisionalTail({
  cols,
  compact,
  lines,
  t
}: {
  cols?: number
  compact?: boolean
  lines: string[]
  t: Theme
}) {
  return (
    <>
      {lines.map((line, i) =>
        line.length <= PROVISIONAL_MD_MAX ? (
          <Md cols={cols} compact={compact} key={i} t={t} text={line} />
        ) : (
          <Text color={t.color.text} key={i} wrap="wrap">
            {line}
          </Text>
        )
      )}
    </>
  )
})

export const StreamingMd = memo(function StreamingMd({ cols, compact, t, text }: StreamingMdProps) {
  const scanRef = useRef<StreamScanState>(createScanState())
  // Scan the untrimmed reply and clip only at render. Scanning the tail window
  // instead is what made a long reply stutter: every delta presented a sliding
  // window, which is not an extension of the previous text, so the scanner reset
  // and re-parsed the whole 16 KB window (~130 ms) on every delta.
  const raw = useTurnSelector(state => state.streamingRaw)
  const dropped = useTurnSelector(state => state.streamingDropped)
  const label = useTurnSelector(state => state.streamingLabel)
  const source = raw || text
  const windowStart = raw ? dropped : 0

  let state = scanRef.current

  // Genuine reset only: turn reuse, or the reasoning→answer switch, where the
  // stream no longer extends what was scanned (a front-trim does extend it —
  // the dropped head was already scanned).
  if (!source.startsWith(state.scanned)) {
    state = scanRef.current = createScanState()
  }

  advanceScan(source, state)
  pruneStreamBlocks(state, windowStart)

  const from = firstVisibleBlock(state, windowStart)
  const tail = source.slice(Math.max(state.settledLen, windowStart))
  const tailLines = tail ? tail.split('\n') : EMPTY_LINES

  return (
    <Box flexDirection="column">
      {label ? <Text color={t.color.muted}>{label}</Text> : null}

      <SettledBlocks
        blocks={state.blocks}
        cols={cols}
        compact={compact}
        count={state.droppedBlocks + state.blocks.length}
        firstOrdinal={state.droppedBlocks}
        from={from}
        t={t}
      />

      {tailLines.length ? <ProvisionalTail cols={cols} compact={compact} lines={tailLines} t={t} /> : null}
    </Box>
  )
})

interface SettledBlocksProps {
  blocks: string[]
  cols?: number
  compact?: boolean
  count: number
  /** Ordinal of `blocks[0]` (≥ 0 once the head has been pruned). */
  firstOrdinal: number
  /** First ordinal still intersecting the render window. */
  from: number
  t: Theme
}

interface StreamingMdProps {
  cols?: number
  compact?: boolean
  t: Theme
  text: string
}
