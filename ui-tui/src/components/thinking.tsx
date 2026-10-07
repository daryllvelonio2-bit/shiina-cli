import { Box, NoSelect, Text } from '@shiina/ink'
import { compactNumber } from '@shiina/shared/format'
import { useStore } from '@nanostores/react'
import { memo, type ReactNode, useEffect, useMemo, useRef, useState } from 'react'
import spinners, { type BrailleSpinnerName } from 'unicode-animations'

import { $uiState } from '../app/uiStore.js'
import { THINKING_COT_MAX, THINKING_TRAIL_MAX_CHARS, THINKING_TRAIL_MAX_LINES } from '../config/limits.js'
import { type DesignIndent, headerEmphasis, headerLabel, headerLead } from '../design.js'
import { opensByDefault, sectionMode } from '../domain/details.js'
import {
  buildSubagentTree,
  fmtTokens,
  formatSummary as formatSpawnSummary,
  hotnessBucket,
  peakHotness,
  sparkline,
  treeTotals,
  widthByDepth
} from '../lib/subagentTree.js'
import {
  TOOL_TRAIL_ERR,
  boundedLiveRenderText,
  compactPreview,
  estimateTokensRough,
  formatToolCall,
  isThinkingStatusLine,
  parseToolTrailResultLine,
  pick,
  splitToolDuration,
  thinkingPreview,
  toolTrailLabel
} from '../lib/text.js'
import type { Theme } from '../theme.js'
import { Md } from './markdown.js'
import type {
  ActiveTool,
  ActivityItem,
  DetailsMode,
  SectionVisibility,
  SubagentNode,
  SubagentProgress,
  ThinkingMode
} from '../types.js'

const THINK: BrailleSpinnerName[] = ['helix', 'breathe', 'orbit', 'dna', 'waverows', 'snake', 'pulse']
const TOOL: BrailleSpinnerName[] = ['cascade', 'scan', 'diagswipe', 'fillsweep', 'rain', 'columns', 'sparkle']

const fmtElapsed = (ms: number) => {
  const sec = Math.max(0, ms) / 1000

  return sec < 10 ? `${sec.toFixed(1)}s` : `${Math.round(sec)}s`
}

type TreeBranch = 'mid' | 'last'
type TreeRails = readonly boolean[]

const nextTreeRails = (rails: TreeRails, branch: TreeBranch) => [...rails, branch === 'mid']

const treeLead = (rails: TreeRails, branch: TreeBranch, indent: DesignIndent) =>
  `${rails.map(on => (on ? indent.stem : indent.unit)).join('')}${branch === 'mid' ? indent.branch : indent.last}`

// ── Primitives ───────────────────────────────────────────────────────

function TreeRow({
  branch,
  children,
  rails = [],
  stemColor,
  stemDim = true,
  t
}: {
  branch: TreeBranch
  children: ReactNode
  rails?: TreeRails
  stemColor?: string
  stemDim?: boolean
  t: Theme
}) {
  const lead = treeLead(rails, branch, t.design.indent)

  return (
    <Box>
      <NoSelect flexShrink={0} fromLeftEdge width={lead.length}>
        <Text color={stemColor ?? t.color.muted} dim={stemDim}>
          {lead}
        </Text>
      </NoSelect>
      <Box flexDirection="column" flexGrow={1}>
        {children}
      </Box>
    </Box>
  )
}

function TreeTextRow({
  branch,
  color,
  content,
  dimColor,
  rails = [],
  t,
  wrap = 'wrap-trim'
}: {
  branch: TreeBranch
  color: string
  content: ReactNode
  dimColor?: boolean
  rails?: TreeRails
  t: Theme
  wrap?: 'truncate-end' | 'wrap' | 'wrap-trim'
}) {
  const text = dimColor ? (
    <Text color={color} dim wrap={wrap}>
      {content}
    </Text>
  ) : (
    <Text color={color} wrap={wrap}>
      {content}
    </Text>
  )

  return (
    <TreeRow branch={branch} rails={rails} t={t}>
      {text}
    </TreeRow>
  )
}

function TreeNode({
  branch,
  children,
  header,
  open,
  rails = [],
  stemColor,
  stemDim,
  t
}: {
  branch: TreeBranch
  children?: (rails: boolean[]) => ReactNode
  header: ReactNode
  open: boolean
  rails?: TreeRails
  stemColor?: string
  stemDim?: boolean
  t: Theme
}) {
  return (
    <Box flexDirection="column">
      <TreeRow branch={branch} rails={rails} stemColor={stemColor} stemDim={stemDim} t={t}>
        {header}
      </TreeRow>
      {open ? children?.(nextTreeRails(rails, branch)) : null}
    </Box>
  )
}

export function Spinner({ color, variant = 'think' }: { color: string; variant?: 'think' | 'tool' }) {
  // The active design picks the animation set. Motion is a large part of why
  // two TUIs read as different apps — the same frame with a different spinner
  // vocabulary reads as a different product.
  const frames = useStore($uiState).design?.spinner?.[variant === 'tool' ? 'tool' : 'think']

  const spin = useMemo(() => {
    const chosen = frames?.length ? (frames as BrailleSpinnerName[]) : variant === 'tool' ? TOOL : THINK
    // A design naming an unknown animation must not crash the frame: fall back
    // to the built-in pick rather than dereferencing undefined.frames.
    const raw = spinners[pick(chosen)] ?? spinners[pick(variant === 'tool' ? TOOL : THINK)]

    return { ...raw, frames: raw.frames.map(f => [...f][0] ?? '⠀') }
  }, [frames, variant])

  const [frame, setFrame] = useState(0)

  useEffect(() => {
    setFrame(0)
  }, [spin])

  useEffect(() => {
    const id = setInterval(() => setFrame(f => (f + 1) % spin.frames.length), spin.interval)

    return () => clearInterval(id)
  }, [spin])

  return <Text color={color}>{spin.frames[frame]}</Text>
}

interface DetailRow {
  color: string
  content: ReactNode
  dimColor?: boolean
  key: string
}

function Detail({
  branch = 'last',
  color,
  content,
  dimColor,
  rails = [],
  t
}: DetailRow & { branch?: TreeBranch; rails?: TreeRails; t: Theme }) {
  if (typeof content === 'string' && content.includes('```diff')) {
    return (
      <TreeRow branch={branch} rails={rails} t={t}>
        <Box flexDirection="column">
          <Md cols={80} t={t} text={content} />
        </Box>
      </TreeRow>
    )
  }
  return <TreeTextRow branch={branch} color={color} content={content} dimColor={dimColor} rails={rails} t={t} />
}

function StreamCursor({
  color,
  dimColor,
  streaming = false,
  visible = false
}: {
  color: string
  dimColor?: boolean
  streaming?: boolean
  visible?: boolean
}) {
  const [on, setOn] = useState(true)

  useEffect(() => {
    if (!visible || !streaming) {
      setOn(true)

      return
    }

    const id = setInterval(() => setOn(v => !v), 420)

    return () => clearInterval(id)
  }, [streaming, visible])

  if (!visible) {
    return null
  }

  return dimColor ? (
    <Text color={color} dim>
      {streaming && on ? '▍' : ' '}
    </Text>
  ) : (
    <Text color={color}>{streaming && on ? '▍' : ' '}</Text>
  )
}

/** Section-title color: the identity color at full strength, with error/warn
 *  overriding it when the row is reporting a problem. Extracted so the
 *  hierarchy (header loud, body quiet) is pinned by a test rather than by the
 *  rendered escapes, which the test harness cannot force. */
export const chevronColor = (t: Theme, tone: 'dim' | 'error' | 'warn' = 'dim'): string =>
  tone === 'error' ? t.color.error : tone === 'warn' ? t.color.warn : t.color.accent

function Chevron({
  count,
  onClick,
  open,
  suffix,
  t,
  title,
  tone = 'dim'
}: {
  count?: number
  onClick: (deep?: boolean) => void
  open: boolean
  suffix?: string
  t: Theme
  title: string
  tone?: 'dim' | 'error' | 'warn'
}) {
  // Section titles are the navigation, so they carry the identity color at full
  // strength; the chevron keeps it too. They used to render muted+dim, which put
  // the body text (reasoning) visually above its own header.
  const color = chevronColor(t, tone)
  const header = t.design.header

  return (
    <Box onClick={(e: any) => onClick(!!e?.shiftKey || !!e?.ctrlKey)}>
      <Text color={color} {...headerEmphasis(header)}>
        {headerLead(header, open, t.design.glyphs)}
        {headerLabel(header, title)}
        {typeof count === 'number' ? <Text color={t.color.muted}> ({count})</Text> : ''}
        {suffix ? (
          <Text color={t.color.statusFg} dim>
            {'  '}
            {suffix}
          </Text>
        ) : null}
      </Text>
    </Box>
  )
}

function heatColor(node: SubagentNode, peak: number, theme: Theme): string | undefined {
  const palette = [theme.color.border, theme.color.accent, theme.color.primary, theme.color.warn, theme.color.error]
  const idx = hotnessBucket(node.aggregate.hotness, peak, palette.length)

  // Below the median bucket we keep the default dim stem so cool branches
  // fade into the chrome — only "hot" branches draw the eye.
  if (idx < 2) {
    return undefined
  }

  return palette[idx]
}

function SubagentAccordion({
  branch,
  expanded,
  node,
  peak,
  rails = [],
  t
}: {
  branch: TreeBranch
  expanded: boolean
  node: SubagentNode
  peak: number
  rails?: TreeRails
  t: Theme
}) {
  const [open, setOpen] = useState(expanded)
  const [deep, setDeep] = useState(expanded)
  const [openThinking, setOpenThinking] = useState(expanded)
  const [openTools, setOpenTools] = useState(expanded)
  const [openNotes, setOpenNotes] = useState(expanded)
  const [openKids, setOpenKids] = useState(expanded)

  useEffect(() => {
    if (!expanded) {
      return
    }

    setOpen(true)
    setDeep(true)
    setOpenThinking(true)
    setOpenTools(true)
    setOpenNotes(true)
    setOpenKids(true)
  }, [expanded])

  const expandAll = () => {
    setOpen(true)
    setDeep(true)
    setOpenThinking(true)
    setOpenTools(true)
    setOpenNotes(true)
    setOpenKids(true)
  }

  const item = node.item
  const children = node.children
  const aggregate = node.aggregate

  const statusTone: 'dim' | 'error' | 'warn' =
    item.status === 'error' || item.status === 'failed'
      ? 'error'
      : item.status === 'interrupted' || item.status === 'timeout'
        ? 'warn'
        : 'dim'

  // `[6a66 3/9]` when the gateway tags the batch; `[3/9]` on older gateways.
  const batchTag = item.delegationId?.split('_').at(-1)?.slice(0, 4)

  const prefix =
    item.taskCount > 1
      ? `[${batchTag ? `${batchTag} ` : ''}${item.index + 1}/${item.taskCount}] `
      : batchTag
        ? `[${batchTag}] `
        : ''

  const goalLabel = item.goal || `Subagent ${item.index + 1}`
  const title = `${prefix}${open ? goalLabel : compactPreview(goalLabel, 60)}`
  const summary = compactPreview((item.summary || '').replace(/\s+/g, ' ').trim(), 72)

  // Suffix packs branch rollup: status · elapsed · per-branch tool/agent/token/cost.
  // Emphasises the numbers the user can't easily eyeball from a flat list.
  const statusLabel = item.status === 'queued' ? 'queued' : item.status === 'running' ? 'running' : String(item.status)

  const rollupBits: string[] = [statusLabel]

  if (item.durationSeconds) {
    rollupBits.push(fmtElapsed(item.durationSeconds * 1000))
  }

  const localTools = item.toolCount ?? 0
  const subtreeTools = aggregate.totalTools - localTools

  if (localTools > 0) {
    rollupBits.push(`${localTools} tool${localTools === 1 ? '' : 's'}`)
  }

  const localTokens = (item.inputTokens ?? 0) + (item.outputTokens ?? 0)

  if (localTokens > 0) {
    rollupBits.push(`${fmtTokens(localTokens)} tok`)
  }

  const filesLocal = (item.filesWritten?.length ?? 0) + (item.filesRead?.length ?? 0)

  if (filesLocal > 0) {
    rollupBits.push(`⎘${filesLocal}`)
  }

  if (children.length > 0) {
    rollupBits.push(`${aggregate.descendantCount}↓`)

    if (subtreeTools > 0) {
      rollupBits.push(`+${subtreeTools}t sub`)
    }

    if (aggregate.activeCount > 0 && item.status !== 'running') {
      rollupBits.push(`⚡${aggregate.activeCount}`)
    }
  }

  const suffix = rollupBits.join(t.design.glyphs.dotSeparator)

  const thinkingText = item.thinking.join('\n')
  const hasThinking = Boolean(thinkingText)
  const hasTools = item.tools.length > 0
  const noteRows = [...(summary ? [summary] : []), ...item.notes]
  const hasNotes = noteRows.length > 0
  const noteColor = statusTone === 'error' ? t.color.error : statusTone === 'warn' ? t.color.warn : t.color.muted

  const sections: {
    header: ReactNode
    key: string
    open: boolean
    render: (rails: boolean[]) => ReactNode
  }[] = []

  if (hasThinking) {
    sections.push({
      header: (
        <Chevron
          count={item.thinking.length}
          onClick={shift => {
            if (shift) {
              expandAll()
            } else {
              setOpenThinking(v => !v)
            }
          }}
          open={openThinking}
          t={t}
          title="Thinking"
        />
      ),
      key: 'thinking',
      open: openThinking,
      render: childRails => (
        <Thinking
          active={item.status === 'running'}
          branch="last"
          mode="full"
          rails={childRails}
          reasoning={thinkingText}
          streaming={item.status === 'running'}
          t={t}
        />
      )
    })
  }

  if (hasTools) {
    sections.push({
      header: (
        <Chevron
          count={item.tools.length}
          onClick={shift => {
            if (shift) {
              expandAll()
            } else {
              setOpenTools(v => !v)
            }
          }}
          open={openTools}
          t={t}
          title="Tool calls"
        />
      ),
      key: 'tools',
      open: openTools,
      render: childRails => (
        <Box flexDirection="column">
          {item.tools.map((line, index) => (
            <TreeTextRow
              branch={index === item.tools.length - 1 ? 'last' : 'mid'}
              color={t.color.text}
              content={
                <>
                  <Text color={t.color.tool}>{`${t.design.glyphs.bullet} `}</Text>
                  {line}
                </>
              }
              key={`${item.id}-tool-${index}`}
              rails={childRails}
              t={t}
            />
          ))}
        </Box>
      )
    })
  }

  if (hasNotes) {
    sections.push({
      header: (
        <Chevron
          count={noteRows.length}
          onClick={shift => {
            if (shift) {
              expandAll()
            } else {
              setOpenNotes(v => !v)
            }
          }}
          open={openNotes}
          t={t}
          title="Progress"
          tone={statusTone}
        />
      ),
      key: 'notes',
      open: openNotes,
      render: childRails => (
        <Box flexDirection="column">
          {noteRows.map((line, index) => (
            <TreeTextRow
              branch={index === noteRows.length - 1 ? 'last' : 'mid'}
              color={noteColor}
              content={line}
              dimColor={statusTone === 'dim'}
              key={`${item.id}-note-${index}`}
              rails={childRails}
              t={t}
            />
          ))}
        </Box>
      )
    })
  }

  if (children.length > 0) {
    // Nested grandchildren — rendered recursively via SubagentAccordion,
    // sharing the same keybindings / expand semantics as top-level nodes.
    sections.push({
      header: (
        <Chevron
          count={children.length}
          onClick={shift => {
            if (shift) {
              expandAll()
            } else {
              setOpenKids(v => !v)
            }
          }}
          open={openKids}
          suffix={`d${item.depth + 1} · ${aggregate.descendantCount} total`}
          t={t}
          title="Spawned"
        />
      ),
      key: 'subagents',
      open: openKids,
      render: childRails => (
        <Box flexDirection="column">
          {children.map((child, i) => (
            <SubagentAccordion
              branch={i === children.length - 1 ? 'last' : 'mid'}
              expanded={expanded || deep}
              key={child.item.id}
              node={child}
              peak={peak}
              rails={childRails}
              t={t}
            />
          ))}
        </Box>
      )
    })
  }

  // Heatmap: amber→error gradient on the stem when this branch is "hot"
  // (high tools/sec) relative to the whole tree's peak.
  const stem = heatColor(node, peak, t)

  return (
    <TreeNode
      branch={branch}
      header={
        <Chevron
          onClick={shift => {
            if (shift) {
              expandAll()

              return
            }

            setOpen(v => {
              if (!v) {
                setDeep(false)
              }

              return !v
            })
          }}
          open={open}
          suffix={suffix}
          t={t}
          title={title}
          tone={statusTone}
        />
      }
      open={open}
      rails={rails}
      stemColor={stem}
      stemDim={stem == null}
      t={t}
    >
      {childRails => (
        <Box flexDirection="column">
          {sections.map((section, index) => (
            <TreeNode
              branch={index === sections.length - 1 ? 'last' : 'mid'}
              header={section.header}
              key={`${item.id}-${section.key}`}
              open={section.open}
              rails={childRails}
              t={t}
            >
              {section.render}
            </TreeNode>
          ))}
        </Box>
      )}
    </TreeNode>
  )
}

// ── Thinking ─────────────────────────────────────────────────────────

/** Window a chain of thought for display: at most `maxLines` rows and at most
 *  `THINKING_TRAIL_MAX_CHARS` characters, always ending at the newest text — the
 *  window slides, old lines unrender as new ones arrive, like `tail -f` for
 *  reasoning. Lines alone do not bound height (one logical line can wrap into a
 *  wall) and characters alone do not bound rows, so both are applied. Pure so
 *  the window is testable without a renderer. */
export const capThinkingLines = (allLines: string[], maxLines?: number): { hidden: number; lines: string[] } => {
  const filtered = allLines.filter(line => !isThinkingStatusLine(line))

  if (!maxLines) {
    return { hidden: 0, lines: filtered }
  }

  const windowed = filtered.slice(-maxLines)
  const hidden = Math.max(0, filtered.length - windowed.length)

  let budget = THINKING_TRAIL_MAX_CHARS

  const lines = windowed
    .map(line => {
      if (budget <= 0) {
        return null
      }

      const room = Math.min(line.length, budget)

      budget -= room

      // A line too long for the budget keeps its END — the newest text is what
      // the window is for — with a leading marker for the clipped head.
      return room < line.length ? `…${line.slice(line.length - Math.max(0, room - 1))}` : line
    })
    .filter((line): line is string => line !== null)

  return { hidden, lines }
}

export const Thinking = memo(function Thinking({
  active = false,
  branch = 'last',
  maxLines,
  mode = 'truncated',
  rails = [],
  reasoning,
  streaming = false,
  t
}: {
  active?: boolean
  branch?: TreeBranch
  /** Cap on rendered lines; the window always ends at the newest line. */
  maxLines?: number
  mode?: ThinkingMode
  rails?: TreeRails
  reasoning: string
  streaming?: boolean
  t: Theme
}) {
  const preview = useMemo(() => {
    const raw = thinkingPreview(reasoning, mode, THINKING_COT_MAX)

    return mode === 'full' ? boundedLiveRenderText(raw) : raw
  }, [mode, reasoning])

  const allLines = useMemo(() => preview.split('\n').map(line => line.replace(/\t/g, '  ')), [preview])

  const { hidden, lines } = useMemo(() => capThinkingLines(allLines, maxLines), [allLines, maxLines])

  if (!preview && !active) {
    return null
  }

  const greenColor = t.color.ok || '#4ade80'

  return (
    <TreeRow branch={branch} rails={rails} t={t}>
      <Box flexDirection="column" flexGrow={1}>
        {preview ? (
          mode === 'full' ? (
            <>
              {hidden > 0 ? (
                <Text color={t.color.muted} dim wrap="truncate-end">
                  {`… +${hidden} earlier line${hidden === 1 ? '' : 's'}`}
                </Text>
              ) : null}
              {lines.map((line, index) => (
                <Text color={t.color.thinking} dim key={index} wrap="wrap-trim">
                  {line || ' '}
                  {index === lines.length - 1 ? (
                    <StreamCursor color={t.color.thinking} streaming={streaming} visible={active} />
                  ) : null}
                </Text>
              ))}
            </>
          ) : (
            <Text color={t.color.thinking} dim wrap="truncate-end">
              {preview}
              <StreamCursor
                color={t.color.thinking}
                streaming={streaming}
                visible={active}
              />
            </Text>
          )
        ) : (
          <Text color={t.color.thinking} dim>
            <StreamCursor color={t.color.thinking} streaming={streaming} visible={active} />
          </Text>
        )}
      </Box>
    </TreeRow>
  )
})

// ── ToolTrail ────────────────────────────────────────────────────────

interface Group {
  color: string
  content: ReactNode
  details: DetailRow[]
  key: string
  label: string
}

export const ToolTrail = memo(function ToolTrail({
  busy = false,
  commandOverride = false,
  detailsMode = 'collapsed',
  layoutSections,
  outcome = '',
  preferExpandedThinking = false,
  reasoningActive = false,
  reasoning = '',
  reasoningAlwaysVisible = false,
  reasoningDuration = 0,
  reasoningTokens,
  reasoningStreaming = false,
  sections,
  subagents = [],
  t,
  tools = [],
  toolTokens,
  trail = [],
  activity = []
}: {
  busy?: boolean
  commandOverride?: boolean
  detailsMode?: DetailsMode
  /** Default progress visibility contributed by the active TUI layout — the
   *  layer between the user's explicit `sections` and the built-in defaults. */
  layoutSections?: SectionVisibility
  outcome?: string
  preferExpandedThinking?: boolean
  reasoningActive?: boolean
  reasoning?: string
  // MoA reference blocks (see Msg.isMoaReference) stay visible even when
  // `visible.thinking === 'hidden'` — they're the mixture-of-agents process
  // the user opted into, not private model reasoning (#64657).
  reasoningAlwaysVisible?: boolean
  reasoningDuration?: number
  reasoningTokens?: number
  reasoningStreaming?: boolean
  sections?: SectionVisibility
  subagents?: SubagentProgress[]
  t: Theme
  tools?: ActiveTool[]
  toolTokens?: number
  trail?: string[]
  activity?: ActivityItem[]
}) {
  const visible = useMemo(
    () => ({
      thinking: sectionMode('thinking', detailsMode, sections, commandOverride, layoutSections),
      tools: sectionMode('tools', detailsMode, sections, commandOverride, layoutSections),
      subagents: sectionMode('subagents', detailsMode, sections, commandOverride, layoutSections),
      activity: sectionMode('activity', detailsMode, sections, commandOverride, layoutSections)
    }),
    [commandOverride, detailsMode, layoutSections, sections]
  )

  // Open defaults come from the section MODE (design/layout/YAML-driven):
  // `live` opens the running turn's block and folds it once settled,
  // `expanded` keeps it open for good. No mode is hardcoded here — see
  // `layout.sections` in the design YAML (designs/codex.yaml).
  const thinkingDefaultExpanded = opensByDefault(visible.thinking, preferExpandedThinking)
  const toolsDefaultExpanded = opensByDefault(visible.tools, preferExpandedThinking)
  const subagentsDefaultExpanded = opensByDefault(visible.subagents, preferExpandedThinking)

  // An explicit `/details` expand or design maxLines=null/0 shows the whole chain of thought;
  // otherwise respect the design's maxLines (defaults to undefined = full/unlimited).
  const designMaxLines = t.design.thinking?.maxLines
  const thinkingMaxLines =
    commandOverride || sections?.thinking === 'expanded'
      ? undefined
      : designMaxLines === 0 || designMaxLines === null
        ? undefined
        : designMaxLines ?? undefined

  const [now, setNow] = useState(() => Date.now())
  // Local toggles own the open state once mounted.  Init from the resolved
  // section visibility so default-expanded sections (thinking/tools) render
  // open on first paint; the useEffect below re-syncs when the user mutates
  // visibility at runtime via /details.  NEVER OR these against
  // `visible.X === 'expanded'` at render time — that locks the panel open
  // and silently breaks manual chevron clicks for default-expanded
  // sections (regression caught after #14968).
  // A MoA reference panel (reasoningAlwaysVisible) opens by default on
  // mount even under `thinking: hidden` — the user opted into MoA and
  // should see the reference immediately, not a collapsed "Thinking"
  // label. This only affects the initial mount value; the re-sync effect
  // below deliberately does NOT re-apply it, so a manual collapse still
  // sticks (see the no-OR-at-effect-time warning above, #14968).
  const [openThinking, setOpenThinking] = useState(thinkingDefaultExpanded || reasoningAlwaysVisible)
  const [openTools, setOpenTools] = useState(toolsDefaultExpanded)
  const [openSubagents, setOpenSubagents] = useState(subagentsDefaultExpanded)
  const [deepSubagents, setDeepSubagents] = useState(subagentsDefaultExpanded)
  const activityDefaultExpanded = opensByDefault(visible.activity, preferExpandedThinking)
  const [openMeta, setOpenMeta] = useState(activityDefaultExpanded)

  useEffect(() => {
    if (!tools.length || (visible.tools !== 'expanded' && !openTools)) {
      return
    }

    const id = setInterval(() => setNow(Date.now()), 500)

    return () => clearInterval(id)
  }, [openTools, tools.length, visible.tools])

  // Effects run after the FIRST render too, not just on later updates — so
  // this re-sync was clobbering the reasoningAlwaysVisible mount value above
  // right after mount, collapsing a just-opened MoA reference panel under
  // `thinking: hidden` before the user ever saw it (#64701). Skip only the
  // very first run; every subsequent mode change (the case this effect exists
  // for) still re-syncs without the override, so a manual collapse still
  // sticks per the no-OR-at-effect-time rule above.
  //
  // Deps are the RESOLVED MODES, never the `visible` object: `layoutSections()`
  // returns a fresh object every render (appLayout computes it inline), so an
  // object dep made this fire on every repaint and reset the panel to its
  // default — a panel the user opened folded itself again a few hundred ms
  // later, mid-turn and while idle.
  const skippedInitialSync = useRef(false)
  useEffect(() => {
    if (!skippedInitialSync.current) {
      skippedInitialSync.current = true

      return
    }

    setOpenThinking(thinkingDefaultExpanded)
    setOpenTools(toolsDefaultExpanded)
    setOpenSubagents(subagentsDefaultExpanded)
    setOpenMeta(activityDefaultExpanded)
  }, [activityDefaultExpanded, subagentsDefaultExpanded, thinkingDefaultExpanded, toolsDefaultExpanded])

  // `collapsed` is an auto preference: keep the panel open while reasoning
  // is live (stream pulses keep `reasoningActive` true) and collapse it the
  // moment the reasoning phase ends (`endReasoningPhase` flips it false).
  // `expanded` stays fully manual, `hidden` never renders content, and MoA
  // reference panels (reasoningAlwaysVisible) are left alone.
  const thinkingAuto = visible.thinking === 'collapsed' && !reasoningAlwaysVisible
  useEffect(() => {
    if (!thinkingAuto) {
      return
    }

    setOpenThinking(reasoningActive)
  }, [thinkingAuto, reasoningActive])

  // The loop finished: collapse every section (thinking, tools, subagents, activity) so the
  // whole process reads as one compact summary and only the final message is left in the
  // open. A section the user pinned open via /details stays open; an MoA reference panel is
  // never touched. The next set opens itself (it is the live one).
  const wasBusy = useRef(busy)
  useEffect(() => {
    const finished = wasBusy.current && !busy
    wasBusy.current = busy

    if (!finished) {
      return
    }

    if (thinkingAuto || !thinkingDefaultExpanded) {
      setOpenThinking(false)
    }

    if (!toolsDefaultExpanded) {
      setOpenTools(false)
    }

    if (!subagentsDefaultExpanded) {
      setOpenSubagents(false)
      setDeepSubagents(false)
    }

    if (!opensByDefault(visible.activity, false)) {
      setOpenMeta(false)
    }
  }, [busy, subagentsDefaultExpanded, thinkingAuto, visible])

  const cot = useMemo(() => thinkingPreview(reasoning, 'full', THINKING_COT_MAX), [reasoning])

  // Spawn-tree derivations must live above any early return so React's
  // rules-of-hooks sees a stable call order.  Cheap O(N) builds memoised
  // by subagent-list identity.
  const spawnTree = useMemo(() => buildSubagentTree(subagents), [subagents])
  const spawnPeak = useMemo(() => peakHotness(spawnTree), [spawnTree])
  const spawnTotals = useMemo(() => treeTotals(spawnTree), [spawnTree])
  const spawnWidths = useMemo(() => widthByDepth(spawnTree), [spawnTree])
  const spawnSpark = useMemo(() => sparkline(spawnWidths), [spawnWidths])
  const spawnSummaryLabel = useMemo(
    () => formatSpawnSummary(spawnTotals, t.design.glyphs.dotSeparator),
    [spawnTotals, t.design.glyphs.dotSeparator]
  )

  if (
    !busy &&
    !trail.length &&
    !tools.length &&
    !subagents.length &&
    !activity.length &&
    !cot &&
    !reasoningActive &&
    !outcome
  ) {
    return null
  }

  // ── Build groups + meta ────────────────────────────────────────

  const groups: Group[] = []
  const meta: DetailRow[] = []
  const pushDetail = (row: DetailRow) => (groups.at(-1)?.details ?? meta).push(row)

  for (const [i, line] of trail.entries()) {
    const parsed = parseToolTrailResultLine(line)

    if (parsed) {
      groups.push({
        color: parsed.mark === TOOL_TRAIL_ERR ? t.color.error : t.color.text,
        content: parsed.call,
        details: [],
        key: `tr-${i}`,
        label: parsed.call
      })

      if (parsed.detail) {
        pushDetail({
          color: parsed.mark === TOOL_TRAIL_ERR ? t.color.error : t.color.muted,
          content: parsed.detail,
          dimColor: parsed.mark !== TOOL_TRAIL_ERR,
          key: `tr-${i}-d`
        })
      }

      continue
    }

    if (line.startsWith('drafting ')) {
      const label = toolTrailLabel(line.slice(9).replace(/…$/, '').trim())

      groups.push({
        color: t.color.text,
        content: label,
        details: [{ color: t.color.muted, content: 'drafting...', dimColor: true, key: `tr-${i}-d` }],
        key: `tr-${i}`,
        label
      })

      continue
    }

    if (line === 'analyzing tool output…') {
      pushDetail({
        color: t.color.muted,
        dimColor: true,
        key: `tr-${i}`,
        content: groups.length ? (
          <>
            <Spinner color={t.color.accent} variant="think" /> {line}
          </>
        ) : (
          line
        )
      })

      continue
    }

    meta.push({ color: t.color.muted, content: line, dimColor: true, key: `tr-${i}` })
  }

  for (const tool of tools) {
    const label = formatToolCall(tool.name, tool.context || '')

    groups.push({
      color: t.color.text,
      key: tool.id,
      label,
      details: tool.verboseArgs
        ? [
            {
              color: t.color.muted,
              content: `Args:\n${boundedLiveRenderText(tool.verboseArgs)}`,
              dimColor: true,
              key: `${tool.id}-args`
            }
          ]
        : [],
      content: (
        <>
          <Spinner color={t.color.tool} variant="tool" /> {label}
          {tool.startedAt ? ` (${fmtElapsed(now - tool.startedAt)})` : ''}
        </>
      )
    })
  }

  for (const item of activity.slice(-4)) {
    const glyph =
      item.tone === 'error'
        ? t.design.glyphs.cross
        : item.tone === 'warn'
          ? t.design.glyphs.warn
          : t.design.glyphs.pending
    const color = item.tone === 'error' ? t.color.error : item.tone === 'warn' ? t.color.warn : t.color.muted
    meta.push({ color, content: `${glyph} ${item.text}`, dimColor: item.tone === 'info', key: `a-${item.id}` })
  }

  // ── Derived ────────────────────────────────────────────────────

  const hasTools = groups.length > 0
  const hasSubagents = subagents.length > 0
  const hasMeta = meta.length > 0
  const hasThinking = !!cot || reasoningActive || reasoningStreaming
  const thinkingLive = reasoningActive || reasoningStreaming

  const tokenCount =
    reasoningTokens && reasoningTokens > 0 ? reasoningTokens : reasoning ? estimateTokensRough(reasoning) : 0

  const toolTokenCount = toolTokens ?? 0
  const totalTokenCount = tokenCount + toolTokenCount
  const thinkingTokensLabel = tokenCount > 0 ? `~${compactNumber(tokenCount)} tokens` : null

  const toolTokensLabel =
    toolTokens !== undefined && toolTokens > 0 ? `~${compactNumber(toolTokens)} tokens` : undefined

  const delegateGroups = groups.filter(g => g.label.startsWith('Delegate Task'))
  const inlineDelegateKey = hasSubagents && delegateGroups.length === 1 ? delegateGroups[0]!.key : null

  const toolLabel = (group: Group) => {
    const { duration, label } = splitToolDuration(String(group.content))

    return duration ? (
      <>
        {label}
        <Text color={t.color.statusFg} dim>
          {duration}
        </Text>
      </>
    ) : (
      group.content
    )
  }

  // ── Backstop: floating alerts when every panel is hidden ─────────
  //
  // Per-section overrides win over the global details_mode (they're computed
  // by sectionMode), so we only collapse to nothing when EVERY section is
  // resolved to hidden — that way `details_mode: hidden` + `sections.tools:
  // expanded` still renders the tools panel.  When all panels are hidden
  // AND ambient errors/warnings exist, surface them as a compact inline
  // backstop so quiet-mode users aren't blind to failures.

  const allHidden =
    visible.thinking === 'hidden' &&
    !reasoningAlwaysVisible &&
    visible.tools === 'hidden' &&
    visible.subagents === 'hidden' &&
    visible.activity === 'hidden'

  if (allHidden) {
    const alerts = activity.filter(i => i.tone !== 'info').slice(-2)

    return alerts.length ? (
      <Box flexDirection="column">
        {alerts.map(i => (
          <Text color={i.tone === 'error' ? t.color.error : t.color.warn} key={`ha-${i.id}`}>
            {i.tone === 'error' ? t.design.glyphs.cross : t.design.glyphs.warn} {i.text}
          </Text>
        ))}
      </Box>
    ) : null
  }

  // ── Tree render fragments ──────────────────────────────────────
  //
  // Shift+click on any chevron expands every NON-hidden section at once —
  // hidden sections stay hidden so the override is honoured.

  const expandAll = () => {
    if (visible.thinking !== 'hidden' || reasoningAlwaysVisible) {
      setOpenThinking(true)
    }

    if (visible.tools !== 'hidden') {
      setOpenTools(true)
    }

    if (visible.subagents !== 'hidden') {
      setOpenSubagents(true)
      setDeepSubagents(true)
    }

    if (visible.activity !== 'hidden') {
      setOpenMeta(true)
    }
  }

  const metaTone: 'dim' | 'error' | 'warn' = activity.some(i => i.tone === 'error')
    ? 'error'
    : activity.some(i => i.tone === 'warn')
      ? 'warn'
      : 'dim'

  const renderSubagentList = (rails: boolean[]) => (
    <Box flexDirection="column">
      {spawnTree.map((node, index) => (
        <SubagentAccordion
          branch={index === spawnTree.length - 1 ? 'last' : 'mid'}
          expanded={visible.subagents === 'expanded' || deepSubagents}
          key={node.item.id}
          node={node}
          peak={spawnPeak}
          rails={rails}
          t={t}
        />
      ))}
    </Box>
  )

  const panels: {
    header: ReactNode
    key: string
    open: boolean
    render: (rails: boolean[]) => ReactNode
  }[] = []

  if (hasThinking && (visible.thinking !== 'hidden' || reasoningAlwaysVisible)) {
    panels.push({
      header: (
        <Box
          onClick={(e: any) => {
            if (e?.shiftKey || e?.ctrlKey) {
              expandAll()
            } else {
              setOpenThinking(v => !v)
            }
          }}
        >
          <Text color={t.color.muted} dim={!thinkingLive}>
            <Text color={t.color.accent}>
              {headerLead(t.design.header, openThinking, t.design.glyphs)}
            </Text>
            <Text {...headerEmphasis(t.design.header)} color={t.color.accent}>
              {headerLabel(
                t.design.header,
                thinkingLive
                  ? 'Thinking'
                  : reasoningDuration > 0
                    ? `thought for ${reasoningDuration.toFixed(1)}s`
                    : 'Thought'
              )}
            </Text>
            {thinkingTokensLabel ? (
              <Text color={t.color.statusFg} dim>
                {'  '}
                {thinkingTokensLabel}
              </Text>
            ) : null}
          </Text>
        </Box>
      ),
      key: 'thinking',
      open: openThinking,
      render: rails => (
        <Thinking
          active={reasoningActive}
          branch="last"
          maxLines={thinkingMaxLines}
          mode="full"
          rails={rails}
          reasoning={busy ? reasoning : cot}
          streaming={busy && reasoningStreaming}
          t={t}
        />
      )
    })
  }

  if (hasTools && visible.tools !== 'hidden') {
    panels.push({
      header: (
        <Chevron
          count={groups.length}
          onClick={shift => {
            if (shift) {
              expandAll()
            } else {
              setOpenTools(v => !v)
            }
          }}
          open={openTools}
          suffix={toolTokensLabel}
          t={t}
          title="Tool calls"
        />
      ),
      key: 'tools',
      open: openTools,
      render: rails => (
        <Box flexDirection="column">
          {groups.map((group, index) => {
            const branch: TreeBranch = index === groups.length - 1 ? 'last' : 'mid'
            const childRails = nextTreeRails(rails, branch)
            const hasInlineSubagents = inlineDelegateKey === group.key
            // Surface the /agents hint the moment a delegate group appears —
            // while it's still in-flight and before any subagent has
            // registered — so users can open the live monitor immediately.
            const isDelegateGroup = group.label.startsWith('Delegate Task')

            return (
              <Box flexDirection="column" key={group.key}>
                <TreeTextRow
                  branch={branch}
                  color={group.color}
                  content={
                    <>
                      <Text color={t.color.tool}>{`${t.design.glyphs.bullet} `}</Text>
                      {toolLabel(group)}
                      {isDelegateGroup ? (
                        <Text color={t.color.statusFg} dim>
                          {'  (/agents to monitor)'}
                        </Text>
                      ) : null}
                    </>
                  }
                  rails={rails}
                  t={t}
                />
                {group.details.map((detail, detailIndex) => (
                  <Detail
                    {...detail}
                    branch={detailIndex === group.details.length - 1 && !hasInlineSubagents ? 'last' : 'mid'}
                    key={detail.key}
                    rails={childRails}
                    t={t}
                  />
                ))}
                {hasInlineSubagents ? renderSubagentList(childRails) : null}
              </Box>
            )
          })}
        </Box>
      )
    })
  }

  if (hasSubagents && !inlineDelegateKey && visible.subagents !== 'hidden') {
    // Spark + summary give a one-line read on the branch shape before
    // opening the subtree.  `/agents` opens the full-screen audit overlay.
    const suffix = spawnSpark ? `${spawnSummaryLabel}  ${spawnSpark}  (/agents)` : `${spawnSummaryLabel}  (/agents)`

    panels.push({
      header: (
        <Chevron
          count={spawnTotals.descendantCount}
          onClick={shift => {
            if (shift) {
              expandAll()
              setDeepSubagents(true)
            } else {
              setOpenSubagents(v => !v)
              setDeepSubagents(false)
            }
          }}
          open={openSubagents}
          suffix={suffix}
          t={t}
          title="Spawn tree"
        />
      ),
      key: 'subagents',
      open: openSubagents,
      render: renderSubagentList
    })
  }

  if (hasMeta && visible.activity !== 'hidden') {
    panels.push({
      header: (
        <Chevron
          count={meta.length}
          onClick={shift => {
            if (shift) {
              expandAll()
            } else {
              setOpenMeta(v => !v)
            }
          }}
          open={openMeta}
          t={t}
          title="Activity"
          tone={metaTone}
        />
      ),
      key: 'meta',
      open: openMeta,
      render: rails => (
        <Box flexDirection="column">
          {meta.map((row, index) => (
            <TreeTextRow
              branch={index === meta.length - 1 ? 'last' : 'mid'}
              color={row.color}
              content={row.content}
              dimColor={row.dimColor}
              key={row.key}
              rails={rails}
              t={t}
            />
          ))}
        </Box>
      )
    })
  }

  if (panels.length === 0) {
    return outcome ? (
      <Box marginTop={1}>
        <Text color={t.color.muted} dim>
          {t.design.glyphs.dotSeparator.trim()} {outcome}
        </Text>
      </Box>
    ) : null
  }
  // Only a section that actually HAS content may hold the unified block open —
  // a stale/leftover flag on an absent section used to force every settled row
  // open (the design's `subagents: expanded` default did exactly that).
  const isSingleSetOpen =
    (hasThinking && openThinking) ||
    (hasTools && openTools) ||
    (hasSubagents && openSubagents) ||
    (activity.length > 0 && openMeta)

  const toggleUnified = () => {
    const next = !isSingleSetOpen
    if (hasThinking) setOpenThinking(next)
    if (hasTools) setOpenTools(next)
    if (hasSubagents) setOpenSubagents(next)
    if (activity.length > 0) setOpenMeta(next)
  }

    const unifiedSummary = [
      hasThinking ? (thinkingTokensLabel || 'Thinking') : null,
      hasTools ? `${groups.length} tool${groups.length === 1 ? '' : 's'}` : null,
      hasSubagents ? `${spawnTotals.descendantCount} agent${spawnTotals.descendantCount === 1 ? '' : 's'}` : null,
    ].filter(Boolean).join(`, `)

    const unifiedTitle = (() => {
      if (hasThinking && !hasTools && !hasSubagents) {
        return thinkingLive
          ? 'Thinking'
          : reasoningDuration > 0
            ? `thought for ${reasoningDuration.toFixed(1)}s`
            : 'Thought'
      }
      return busy ? 'In progress' : 'Steps'
    })()

  return (
    <Box flexDirection="column">
      <TreeNode
        branch="last"
        header={
          <Box onClick={toggleUnified}>
            <Text color={t.color.muted} dim={!busy}>
              <Text color={t.color.accent}>
                {headerLead(t.design.header, isSingleSetOpen, t.design.glyphs)}
              </Text>
              <Text {...headerEmphasis(t.design.header)} color={t.color.accent}>
                {headerLabel(t.design.header, unifiedTitle)}
              </Text>
              {unifiedSummary ? (
                <Text color={t.color.statusFg} dim>
                  {'  '}({unifiedSummary})
                </Text>
              ) : null}
            </Text>
          </Box>
        }
        key="unified-set"
        open={isSingleSetOpen}
        t={t}
      >
        {rails => (
          <Box flexDirection="column">
            {panels.map(panel => (
              <Box flexDirection="column" key={panel.key}>
                {panel.render(rails)}
              </Box>
            ))}
          </Box>
        )}
      </TreeNode>
      {outcome ? (
        <Box marginTop={1}>
          <Text color={t.color.muted} dim>
            {t.design.glyphs.dotSeparator.trim()} {outcome}
          </Text>
        </Box>
      ) : null}
    </Box>
  )
})
