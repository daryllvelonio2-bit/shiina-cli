import { stripAnsi } from '@shiina/shared/ansi'
import { compactNumber } from '@shiina/shared/format'

import {
  LIVE_RENDER_MAX_CHARS,
  LIVE_RENDER_MAX_LINES,
  THINKING_COT_MAX,
  VERBOSE_TRAIL_MAX_CHARS,
  VERBOSE_TRAIL_MAX_LINES
} from '../config/limits.js'
import { VERBS } from '../content/verbs.js'
import { DEFAULT_BORDERS, DEFAULT_GLYPHS } from '../design.js'
import type { ThinkingMode } from '../types.js'

const WS_RE = /\s+/g

// The tool-trail LINE PROTOCOL. A trail line is built once, persisted with the
// transcript, and parsed back out of it (`isToolTrailResultLine`,
// `parseToolTrailResultLine`, `sameToolTrailGroup`), so these marks are pinned
// to the BUILT-IN glyphs rather than the live design: a design that restyles
// `check`/`cross` must not break parsing of lines written before the switch.
// Chrome that renders a trail line reads `t.design.glyphs` for its own marks.
// (`MARK_DOT` / `MARK_RAIL` are preview text, same reasoning.)
export const TOOL_TRAIL_OK = '✓'
export const TOOL_TRAIL_ERR = '✗'
const MARK_PENDING = DEFAULT_GLYPHS.pending
const MARK_DOT = DEFAULT_GLYPHS.dot
const MARK_RAIL = DEFAULT_GLYPHS.railVertical
/** The code-fence label's rule (`rows` math mirrors what `markdown.tsx` paints). */
const FENCE_RULE = DEFAULT_BORDERS.rule

const renderEstimateLine = (line: string) => {
  const trimmed = line.trim()

  if (trimmed.startsWith('|')) {
    return trimmed
      .split('|')
      .filter(Boolean)
      .map(cell => cell.trim())
      .join('  ')
  }

  return line
    .replace(/!\[(.*?)\]\(([^)\s]+)\)/g, '[image: $1]')
    .replace(/\[(.+?)\]\((https?:\/\/[^\s)]+)\)/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/(?<!\w)__(.+?)__(?!\w)/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/(?<!\w)_(.+?)_(?!\w)/g, '$1')
    .replace(/~~(.+?)~~/g, '$1')
    .replace(/==(.+?)==/g, '$1')
    .replace(/\[\^([^\]]+)\]/g, '[$1]')
    .replace(/^#{1,6}\s+/, '')
    .replace(/^\s*[-*+]\s+\[( |x|X)\]\s+/, (_m, checked: string) => `${MARK_DOT} [${checked.toLowerCase() === 'x' ? 'x' : ' '}] `)
    .replace(/^\s*[-*+]\s+/, `${MARK_DOT} `)
    .replace(/^\s*(\d+)\.\s+/, '$1. ')
    .replace(/^\s*(?:>\s*)+/, `${MARK_RAIL} `)
}

export const compactPreview = (s: string, max: number) => {
  const one = s.replace(WS_RE, ' ').trim()

  return !one ? '' : one.length > max ? one.slice(0, max - 1) + '…' : one
}

export const estimateTokensRough = (text: string) => (!text ? 0 : (text.length + 3) >> 2)

export const edgePreview = (s: string, head = 16, tail = 28) => {
  const one = s.replace(WS_RE, ' ').trim().replace(/\]\]/g, '] ]')

  return !one
    ? ''
    : one.length <= head + tail + 4
      ? one
      : `${one.slice(0, head).trimEnd()}.. ${one.slice(-tail).trimStart()}`
}

export const pasteTokenLabel = (text: string, lineCount: number) => {
  const preview = edgePreview(text)

  if (!preview) {
    return `[[ [${compactNumber(lineCount)} lines] ]]`
  }

  const [head = preview, tail = ''] = preview.split('.. ', 2)

  return tail
    ? `[[ ${head.trimEnd()}.. [${compactNumber(lineCount)} lines] .. ${tail.trimStart()} ]]`
    : `[[ ${preview} [${compactNumber(lineCount)} lines] ]]`
}

const SITUATIONAL_VERBS =
  'reviewing|inspecting|verifying|examining|checking|cooking|admiring|fine-tuning|polishing|double-checking|reading|studying|analyzing|searching|gathering|digging|scouting|scanning|connecting|exploring|digesting|browsing|researching|looking|thinking|overthinking|planning|debugging|diagnosing|troubleshooting|drafting|architecting|brainstorming|formulating|plotting|refining|figuring|hunting|untangling|pinpointing|mapping|testing|validating|confirming|ensuring|evaluating|synthesizing|considering|deliberating|piecing|in the zone|locked in|working magic|brewing|letting|firing|putting|simmering|whipping|channeling|crunching'

const STATUS_LINE_RE = new RegExp(
  `^\\s*(?:\\([^\\n)]*\\)\\S*\\s*)?(?:[A-Za-z0-9_.-]+[:\\s]+\\s*){0,3}(?:is\\s+[a-z-]+|(?:${SITUATIONAL_VERBS}))\\b.*(?:\\.{2,3}|…)\\s*$`,
  'i'
)

const STATUS_JOINED_RE = new RegExp(
  `((?:\\([^\\n)]*\\)\\S*\\s*)?(?:[A-Za-z0-9_.-]+[:\\s]+\\s*){0,3}(?:is\\s+[a-z-]+|(?:${SITUATIONAL_VERBS}))\\b.*?(?:\\.{2,3}|…))\\s*([A-Za-z0-9])`,
  'gi'
)

export const isThinkingStatusLine = (line: string): boolean => STATUS_LINE_RE.test(line.trim())

const THINKING_STATUS_RE = new RegExp(`^(?:${VERBS.join('|')})\\.{0,3}$`, 'i')
const THINKING_STATUS_CHUNK_RE = new RegExp(`[^A-Za-z\n]+\\s*(?:${VERBS.join('|')})\\.{0,3}\\s*`, 'giu')

const DSML_RE = /<[｜|]\s*DSML\s*[｜|][^>]*>/gi

export const cleanThinkingText = (reasoning: string) =>
  reasoning
    .replace(DSML_RE, '')
    .replace(STATUS_JOINED_RE, '$1\n\n$2')
    .split('\n')
    .map(line => line.replace(THINKING_STATUS_CHUNK_RE, '').trim())
    .filter(line => line && !THINKING_STATUS_RE.test(line.replace(/\.\.\.$/, '').trim()) && !isThinkingStatusLine(line))
    .join('\n')
    .replace(/([^\n])(?=\*\*[^*\n][^\n]*?\*\*)/g, '$1\n\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()

// cleanThinkingText runs several full-string regex passes (split/map/filter/join/replace).
// reasoning grows on every streamed token, so without a pre-bound this re-cleans the whole
// accumulated string on every chunk — O(n) work per token, O(n^2) over a stream. Only the
// tail is ever displayed (boundedLiveRenderText caps it further downstream), so bound the
// input here first. Headroom over LIVE_RENDER_MAX_CHARS keeps line-boundary trimming inside
// cleanThinkingText accurate even after slicing mid-line.
const THINKING_CLEAN_TAIL_BOUND = LIVE_RENDER_MAX_CHARS * 1.5

export const thinkingPreview = (reasoning: string, mode: ThinkingMode, max: number = THINKING_COT_MAX) => {
  const bounded = reasoning.length > THINKING_CLEAN_TAIL_BOUND ? reasoning.slice(-THINKING_CLEAN_TAIL_BOUND) : reasoning
  const raw = cleanThinkingText(bounded)

  return !raw || mode === 'collapsed' ? '' : mode === 'full' ? raw : compactPreview(raw.replace(WS_RE, ' '), max)
}

/** The rendered tail window of a live reply, plus where it starts. */
export interface LiveTail {
  /** Absolute offset of `text` within the source — everything before it was
   *  dropped from the render window (but the scanner still covers it). */
  dropped: number
  omittedChars: number
  omittedLines: number
  text: string
}

/**
 * Bound a live reply to a render window (a tail), reporting the absolute offset
 * of that window. The offset is what lets the incremental renderer keep scanning
 * the untrimmed stream (see `StreamingMd`): a sliding window used to look like a
 * brand-new document every delta and forced a full re-parse — ~130 ms per delta
 * at the 16 KB cap, which is the long-reply stutter.
 */
export const liveTailWindow = (
  text: string,
  { maxChars = LIVE_RENDER_MAX_CHARS, maxLines = LIVE_RENDER_MAX_LINES } = {}
): LiveTail => {
  if (text.length <= maxChars && text.split('\n', maxLines + 1).length <= maxLines) {
    return { dropped: 0, omittedChars: 0, omittedLines: 0, text }
  }

  let start = 0
  let idx = text.length

  for (let seen = 0; seen < maxLines && idx > 0; seen++) {
    idx = text.lastIndexOf('\n', idx - 1)
    start = idx < 0 ? 0 : idx + 1

    if (idx < 0) {
      break
    }
  }

  const lineStart = start

  start = Math.max(lineStart, text.length - maxChars)

  if (start > lineStart) {
    const nextBreak = text.indexOf('\n', start)

    if (nextBreak >= 0 && nextBreak < text.length - 1) {
      start = nextBreak + 1
    }
  }

  const tail = text.slice(start).trimStart()
  // `text.length - tail.length` is exactly where the rendered tail begins: the
  // line walk plus whatever `trimStart` removed.
  const dropped = text.length - tail.length

  return {
    dropped,
    omittedChars: dropped,
    omittedLines: countNewlines(text, start),
    text: tail
  }
}

/** The "[showing live tail; omitted …]" marker, or '' when nothing was dropped. */
export const liveTailLabel = (
  { omittedChars, omittedLines }: Pick<LiveTail, 'omittedChars' | 'omittedLines'>,
  labelPrefix = 'showing live tail'
) =>
  omittedChars <= 0
    ? ''
    : omittedLines > 0
      ? `[${labelPrefix}; omitted ${compactNumber(omittedLines)} lines / ${compactNumber(omittedChars)} chars]`
      : `[${labelPrefix}; omitted ${compactNumber(omittedChars)} chars]`

export const boundedLiveRenderText = (
  text: string,
  opts: { maxChars?: number; maxLines?: number } = {}
) => {
  const window = liveTailWindow(text, opts)
  const label = liveTailLabel(window)

  return label ? `${label}\n${window.text}` : window.text
}

const boundedRenderText = (
  text: string,
  labelPrefix: string,
  { maxChars, maxLines }: { maxChars: number; maxLines: number }
) => {
  if (text.length <= maxChars && text.split('\n', maxLines + 1).length <= maxLines) {
    return text
  }

  let start = 0
  let idx = text.length

  for (let seen = 0; seen < maxLines && idx > 0; seen++) {
    idx = text.lastIndexOf('\n', idx - 1)
    start = idx < 0 ? 0 : idx + 1

    if (idx < 0) {
      break
    }
  }

  const lineStart = start
  start = Math.max(lineStart, text.length - maxChars)

  if (start > lineStart) {
    const nextBreak = text.indexOf('\n', start)

    if (nextBreak >= 0 && nextBreak < text.length - 1) {
      start = nextBreak + 1
    }
  }

  const tail = text.slice(start).trimStart()
  const omittedLines = countNewlines(text, start)
  const omittedChars = Math.max(0, text.length - tail.length)

  const label =
    omittedLines > 0
      ? `[${labelPrefix}; omitted ${compactNumber(omittedLines)} lines / ${compactNumber(omittedChars)} chars]\n`
      : `[${labelPrefix}; omitted ${compactNumber(omittedChars)} chars]\n`

  return `${label}${tail}`
}

const countNewlines = (text: string, end: number) => {
  let count = 0

  for (let i = 0; i < end; i++) {
    if (text.charCodeAt(i) === 10) {
      count++
    }
  }

  return count
}

export const stripTrailingPasteNewlines = (text: string) => (/[^\n]/.test(text) ? text.replace(/\n+$/, '') : text)

export const toolTrailLabel = (name: string) => {
  if (name.toLowerCase() === 'patch') return 'Patched'
  return (
    name
      .split('_')
      .filter(Boolean)
      .map(p => p[0]!.toUpperCase() + p.slice(1))
      .join(' ') || name
  )
}

export const formatToolCall = (name: string, context = '') => {
  const label = toolTrailLabel(name)
  const preview = compactPreview(context, 64)

  return preview ? `${label}("${preview}")` : label
}

export const buildToolTrailLine = (
  name: string,
  context: string,
  error?: boolean,
  note?: string,
  duration?: number
) => {
  const detail = compactPreview(note ?? '', 72)
  const took = duration !== undefined ? ` (${duration.toFixed(1)}s)` : ''

  return `${formatToolCall(name, context)}${took}${detail ? ` :: ${detail}` : ''} ${error ? TOOL_TRAIL_ERR : TOOL_TRAIL_OK}`
}

const verboseToolBlock = (label: string, text?: string) => {
  const body = (text ?? '').trim()

  // Persisted trail blocks are kept all session and rendered expanded by
  // default — cap to a small readable preview (NOT the 16KB live-render
  // budget) so a large tool output can't balloon the Ink render tree and
  // silently OOM-kill the TUI. See VERBOSE_TRAIL_MAX_CHARS (#34095).
  return body
    ? `${label}:\n${boundedLiveRenderText(body, {
        maxChars: VERBOSE_TRAIL_MAX_CHARS,
        maxLines: VERBOSE_TRAIL_MAX_LINES
      })}`
    : ''
}

export const buildVerboseToolTrailLine = (
  name: string,
  context: string,
  error?: boolean,
  duration?: number,
  argsText?: string,
  resultText?: string
) => {
  const detail = [verboseToolBlock('Args', argsText), verboseToolBlock(error ? 'Error' : 'Result', resultText)]
    .filter(Boolean)
    .join('\n')

  const took = duration !== undefined ? ` (${duration.toFixed(1)}s)` : ''

  return `${formatToolCall(name, context)}${took}${detail ? ` :: ${detail}` : ''} ${error ? TOOL_TRAIL_ERR : TOOL_TRAIL_OK}`
}

export const isToolTrailResultLine = (line: string) =>
  line.endsWith(` ${TOOL_TRAIL_OK}`) || line.endsWith(` ${TOOL_TRAIL_ERR}`)

export const parseToolTrailResultLine = (line: string) => {
  // Verbose trail: the mark closes the LAST line and the detail (Args/Result
  // blocks) spans the lines between the call and the mark.
  if (isToolTrailResultLine(line)) {
    const mark = line.endsWith(` ${TOOL_TRAIL_ERR}`) ? TOOL_TRAIL_ERR : TOOL_TRAIL_OK
    const body = line.slice(0, -2)
    const sep = body.indexOf(' :: ')

    if (sep >= 0) {
      return { call: body.slice(0, sep), detail: body.slice(sep + 4), mark }
    }

    const legacy = body.indexOf(': ')

    if (legacy > 0) {
      return { call: body.slice(0, legacy), detail: body.slice(legacy + 2), mark }
    }

    return { call: body, detail: '', mark }
  }

  // Combined tool + inline-diff trail: the mark closes the FIRST line and a
  // ```diff block follows the call (patch comparison under the patch entry).
  const firstLine = line.split('\n')[0] ?? line

  if (!isToolTrailResultLine(firstLine)) {
    return null
  }

  const diffPart = line.slice(firstLine.length + 1)
  const mark = firstLine.endsWith(` ${TOOL_TRAIL_ERR}`) ? TOOL_TRAIL_ERR : TOOL_TRAIL_OK
  const body = firstLine.slice(0, -2)
  const sep = body.indexOf(' :: ')
  const detail = sep >= 0 ? [body.slice(sep + 4), diffPart].filter(Boolean).join('\n') : diffPart

  return { call: sep >= 0 ? body.slice(0, sep) : body, detail, mark }
}

export const splitToolDuration = (call: string) => {
  const match = call.match(/^(.*?)( \(\d+(?:\.\d)?s\))$/)

  return match ? { label: match[1]!, duration: match[2]! } : { label: call, duration: '' }
}

export const isTransientTrailLine = (line: string) => line.startsWith('drafting ') || line === 'analyzing tool output…'

export const sameToolTrailGroup = (label: string, entry: string) =>
  entry === `${label} ${TOOL_TRAIL_OK}` ||
  entry === `${label} ${TOOL_TRAIL_ERR}` ||
  entry.startsWith(`${label}(`) ||
  entry.startsWith(`${label} ::`) ||
  entry.startsWith(`${label}:`)

export const lastCotTrailIndex = (trail: readonly string[]) => {
  for (let i = trail.length - 1; i >= 0; i--) {
    if (!isToolTrailResultLine(trail[i]!)) {
      return i
    }
  }

  return -1
}

export const estimateRows = (text: string, w: number, compact = false) => {
  let fence: { char: '`' | '~'; len: number } | null = null
  let rows = 0

  for (const raw of text.split('\n')) {
    const line = stripAnsi(raw)
    const maybeFence = line.match(/^\s*(`{3,}|~{3,})(.*)$/)

    if (maybeFence) {
      const marker = maybeFence[1]!
      const lang = maybeFence[2]!.trim()

      if (!fence) {
        fence = { char: marker[0] as '`' | '~', len: marker.length }

        if (lang) {
          rows += Math.ceil((`${FENCE_RULE} ${lang}`.length || 1) / w)
        }
      } else if (marker[0] === fence.char && marker.length >= fence.len) {
        fence = null
      }

      continue
    }

    const inCode = Boolean(fence)
    const trimmed = line.trim()

    if (!inCode && trimmed.startsWith('|') && /^[|\s:-]+$/.test(trimmed)) {
      continue
    }

    const rendered = inCode ? line : renderEstimateLine(line)

    if (compact && !rendered.trim()) {
      continue
    }

    rows += Math.ceil((rendered.length || 1) / w)
  }

  return Math.max(1, rows)
}

/**
 * Render an unanswered clarify prompt (timed out, or cancelled with Esc/Ctrl+C)
 * as a persistent transcript block.  The live `ClarifyPrompt` overlay is torn
 * down the moment the turn settles, so without this the question + options
 * vanish from the screen while the agent's follow-up still refers to "the
 * options above".  Mirrors the option formatting in ClarifyPrompt (the same
 * 1-based numbered list) so the persisted record reads identically to what was
 * on screen.  `reason` states why the prompt ended ("timed out", "cancelled").
 */
export const formatAbandonedClarify = (question: string, choices: string[] | null, reason: string) => {
  const head = `ask ${question.trim()}`
  const opts = (choices ?? []).map((c, i) => `  ${i + 1}. ${c}`)

  return [head, ...opts, `  (${reason} — no selection)`].join('\n')
}

/**
 * Batch counterpart of `formatAbandonedClarify`: every question on its own
 * line, answered ones keeping their locked answer (partials survive a
 * timeout server-side, so the record must show what was actually sent).
 */
export const formatAbandonedClarifyBatch = (
  questions: { qid: string; question: string }[],
  answers: Record<string, string>,
  reason: string
) => {
  const lines = questions.map(q => {
    const answer = answers[q.qid]

    return answer ? `  ${TOOL_TRAIL_OK} ${q.question} → ${answer}` : `  ${MARK_PENDING} ${q.question} (no answer)`
  })

  return [`ask (${questions.length} questions)`, ...lines, `  (${reason})`].join('\n')
}

/**
 * Cursor/draft restore for re-visiting an answered batch clarify question
 * (Tab/Shift-Tab): a choice answer puts the cursor back on its row; an
 * answer that matches no choice was typed via Other, so the cursor lands on
 * the Other row (index = choices.length) with the text staged for editing.
 * Unanswered questions restore to a clean cursor.
 */
export const clarifyBatchRevisitState = (
  choices: readonly string[],
  answer: string | undefined
): { custom: string; sel: number } => {
  if (answer === undefined || answer === '') {
    return { custom: '', sel: 0 }
  }

  const choiceIndex = choices.indexOf(answer)

  if (choiceIndex >= 0) {
    return { custom: '', sel: choiceIndex }
  }

  return { custom: answer, sel: choices.length > 0 ? choices.length : 0 }
}

export const flat = (r: Record<string, string[]>) => Object.values(r).flat()

export const pick = <T>(a: readonly T[]) => a[Math.floor(Math.random() * a.length)]!

export const isPasteBackedText = (text: string) =>
  /\[\[paste:\d+(?:[^\n]*?)\]\]|\[paste #\d+ (?:attached|excerpt)(?:[^\n]*?)\]/.test(text)
