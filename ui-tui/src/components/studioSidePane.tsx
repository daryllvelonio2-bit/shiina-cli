// Studio's reserved instrument column: the live agents board and the todo list
// sit BESIDE the transcript for the whole session instead of wrapping the
// composer (workbench) — panes, not flow. Rendered only while the studio
// layout affords the column (see domain/layout.ts `layoutRegions`).

import { Box, NoSelect, Text } from '@shiina/ink'
import { useStore } from '@nanostores/react'
import { memo } from 'react'

import { $uiState } from '../app/uiStore.js'

import { LiveAgentsPanel } from './agentsPanel.js'
import { LiveTodoPanel } from './streamingAssistant.js'

export const StudioSidePane = memo(function StudioSidePane({ width }: { width: number }) {
  const ui = useStore($uiState)

  return (
    <NoSelect flexDirection="column" flexShrink={0} paddingX={ui.theme.design.spacing.insetPadX} width={width}>
      <Text bold color={ui.theme.color.label}>
        instruments
      </Text>

      <Box flexDirection="column" marginTop={1}>
        <LiveAgentsPanel cols={Math.max(1, width - 2)} />
      </Box>

      <Box flexDirection="column" marginTop={1}>
        <LiveTodoPanel />
      </Box>
    </NoSelect>
  )
})
