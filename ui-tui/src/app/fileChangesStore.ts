import { atom } from 'nanostores'

import type { ChangedFile } from '@shiina/shared/gateway-events'

import type { GatewayClient } from '../gatewayClient.js'
import { asRpcResult } from '../lib/rpc.js'

/** One line of the session's change list — the wire type from the generated contract. */
export type { ChangedFile }

/**
 * Working-tree changes in the session cwd. The backend answers with a short
 * TTL cache, so the client re-asks at each loop end instead of polling —
 * `fetchFileChanges` is called from that transition.
 */
export const $fileChanges = atom<ChangedFile[]>([])

/** Totals across `$fileChanges`, shown collapsed above the status rule. */
export const $fileChangesTotals = atom<{ changed: number; added: number; removed: number }>({
  changed: 0,
  added: 0,
  removed: 0
})

/** The strip is compact by default; the user expands it for the file list. */
export const $fileChangesExpanded = atom(false)

export const toggleFileChanges = () => $fileChangesExpanded.set(!$fileChangesExpanded.get())

/** Collapse back to the one-line summary (a new turn starts clean). */
export const collapseFileChanges = () => $fileChangesExpanded.set(false)

const clear = () => {
  $fileChanges.set([])
  $fileChangesTotals.set({ changed: 0, added: 0, removed: 0 })
}

/**
 * Pull the session's change list. A non-repo cwd, a dead session or a version skew leaves the
 * strip empty: it is optional chrome above the status bar, so it never prints an error there.
 */
export const fetchFileChanges = async (gw: GatewayClient, sessionId: string | null) => {
  if (!sessionId) {
    clear()

    return
  }

  try {
    const raw = await gw.request('session.changes', { session_id: sessionId })
    const result = asRpcResult<{
      repo?: boolean
      changed?: number
      added?: number
      removed?: number
      files?: ChangedFile[]
    }>(raw)

    if (!result?.repo) {
      clear()

      return
    }

    const files = result.files ?? []

    $fileChanges.set(files)
    $fileChangesTotals.set({
      changed: result.changed ?? files.length,
      added: result.added ?? 0,
      removed: result.removed ?? 0
    })
  } catch {
    clear()
  }
}
