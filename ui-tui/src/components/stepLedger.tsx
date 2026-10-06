import { Box, stringWidth, Text } from '@shiina/ink'
import { useStore } from '@nanostores/react'
import { useEffect, useState } from 'react'

import { $uiState } from '../app/uiStore.js'
import { useTurnSelector } from '../app/turnStore.js'
import { fmtDuration } from '../lib/subagentTree.js'
import { compactPreview } from '../lib/text.js'
import type { Theme } from '../theme.js'

/**
 * The live step ledger — the running turn's steps as a persistent, ordered
 * list above the composer.
 *
 * This is what makes `display.layout: timeline` a different surface rather than
 * a rearrangement: workbench folds the same information into per-turn
 * accordions that a settled turn hides, while the ledger keeps the *current*
 * turn's shape on screen for as long as it is running — completed steps behind
 * a check, the tool being called right now at the bottom, counting up.
 *
 * Sources, both already maintained by the turn controller:
 *   - `turnTrail`  the chronological step lines for this turn (bounded)
 *   - `tools`      the calls in flight, with `startedAt` for the elapsed clock
 *
 * Renders nothing without a live turn, so an idle TUI pays no rows.
 */

const LEDGER_STEP_LIMIT = 6

export const StepLedger = ({ cols, t }: { cols: number; t: Theme }) => {
  const ui = useStore($uiState)
  const trail = useTurnSelector(state => state.turnTrail)
  const tools = useTurnSelector(state => state.tools)

  const running = tools.length > 0

  // Elapsed time only matters while something is in flight; ticking otherwise
  // would repaint the ledger (and its parent) for a frozen number.
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!running || !ui.busy) {
      return
    }

    const id = setInterval(() => setNow(Date.now()), 500)

    return () => clearInterval(id)
  }, [running, ui.busy])

  const steps = trail.slice(-LEDGER_STEP_LIMIT)

  if (!steps.length && !running) {
    return null
  }

  const glyphs = t.design.glyphs
  const indent = t.design.indent.unit
  // '  ' (the built-in unit) + '✓ ' accounts for the two columns this used to
  // hardcode as `cols - 6`; a wider design indent shrinks the preview by as much.
  const lead = stringWidth(indent) + 4
  const done = steps.length
  const header = `${glyphs.active} Steps${done ? ` ${glyphs.separator.trim()} ${done}` : ''}`
  const hint = running ? `${glyphs.bullet} ${tools.length} running` : `${glyphs.idle} idle`

  return (
    <Box flexDirection="column" flexShrink={0} width={cols}>
      <Text bold color={t.color.accent} wrap="truncate-end">
        {header}
        <Text color={t.color.muted}>{` ${glyphs.separator} ${hint}`}</Text>
      </Text>
      {steps.map((line, index) => (
        <Text color={t.color.muted} dim key={`${index}:${line}`} wrap="truncate-end">
          {`${indent}${glyphs.check} ${compactPreview(line, Math.max(8, cols - lead))}`}
        </Text>
      ))}
      {tools.map(tool => {
        const elapsed = tool.startedAt ? fmtDuration(now - tool.startedAt) : ''
        const label = tool.context ? `${tool.name} ${glyphs.separator}${tool.context}` : tool.name
        const room = Math.max(8, cols - lead - stringWidth(elapsed))

        return (
          <Text color={t.color.tool} key={tool.id} wrap="truncate-end">
            {`${indent}${glyphs.bullet} ${compactPreview(label, room)}`}
            {elapsed ? <Text color={t.color.muted}>{` ${elapsed}`}</Text> : null}
          </Text>
        )
      })}
    </Box>
  )
}
