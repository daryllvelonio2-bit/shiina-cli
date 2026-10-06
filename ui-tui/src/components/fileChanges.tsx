import { Box, Text } from '@shiina/ink'
import { useStore } from '@nanostores/react'
import { memo, useEffect } from 'react'

import {
  $fileChanges,
  $fileChangesExpanded,
  $fileChangesTotals,
  collapseFileChanges,
  fetchFileChanges,
  toggleFileChanges
} from '../app/fileChangesStore.js'
import { useGateway } from '../app/gatewayContext.js'
import type { Theme } from '../theme.js'

const MAX_ROWS = 6

/** Path, shortened to its last two segments so the row stays readable in a narrow column. */
const shortPath = (path: string) => {
  const parts = path.split('/').filter(Boolean)

  return parts.length <= 2 ? path : parts.slice(-2).join('/')
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

/**
 * Collapsed change list above the status rule: one compact line
 * (`✎ 3 files · +42 −7`) that expands to the per-file rows on click.
 *
 * Refreshed when the loop finishes (`busy` falls) and when the session changes —
 * the backend scan is a git call, so it is never polled per frame.
 */
export const FileChangesStrip = memo(function FileChangesStrip({
  busy,
  sessionId,
  t
}: {
  busy: boolean
  sessionId: string | null
  t: Theme
}) {
  const { gw } = useGateway()
  const files = useStore($fileChanges)
  const totals = useStore($fileChangesTotals)
  const expanded = useStore($fileChangesExpanded)

  useEffect(() => {
    void fetchFileChanges(gw, sessionId)
  }, [gw, sessionId])

  useEffect(() => {
    if (busy) {
      collapseFileChanges()

      return
    }

    // Loop finished: this is the moment the edited-file list is complete.
    void fetchFileChanges(gw, sessionId)
  }, [busy, gw, sessionId])

  if (!totals.changed) {
    return null
  }

  const summary = `${plural(totals.changed, 'file')} · +${totals.added} −${totals.removed}`
  const rows = files.length > MAX_ROWS ? files.slice(0, MAX_ROWS) : files
  const hidden = files.length - rows.length

  return (
    <Box flexDirection="column" flexShrink={0} paddingX={t.design.spacing.insetPadX}>
      <Box onClick={toggleFileChanges}>
        <Text color={t.color.muted}>{expanded ? `${t.design.glyphs.chevronOpen} ` : `${t.design.glyphs.chevronClosed} `}</Text>
        <Text color={t.color.label}>✎ {summary}</Text>
        {!expanded && <Text color={t.color.muted}> (click for files)</Text>}
      </Box>
      {expanded &&
        rows.map(file => (
          <Box key={file.path}>
            <Text color={t.color.muted}> </Text>
            <Text color={file.status === '?' ? t.color.ok : t.color.text}>{shortPath(file.path)}</Text>
            <Text color={t.color.diffAdded}> +{file.added}</Text>
            <Text color={t.color.diffRemoved}> −{file.removed}</Text>
          </Box>
        ))}
      {expanded && hidden > 0 && <Text color={t.color.muted}> … {plural(hidden, 'more file')}</Text>}
    </Box>
  )
})
