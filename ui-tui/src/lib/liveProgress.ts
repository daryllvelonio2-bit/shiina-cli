import { VISIBLE_STEP_ROWS } from '../config/limits.js'
import type { Msg, TodoItem } from '../types.js'

export const countPendingTodos = (todos: readonly TodoItem[]) =>
  todos.filter(todo => todo.status === 'in_progress' || todo.status === 'pending').length

export const isTodoDone = (todos: readonly TodoItem[]) =>
  todos.length > 0 && todos.every(todo => todo.status === 'completed' || todo.status === 'cancelled')

export const isToolShelfMessage = (msg: Msg | undefined) =>
  Boolean(msg?.kind === 'trail' && !msg.text && !msg.thinking?.trim() && msg.tools?.length)

export const canHoldToolShelf = (msg: Msg | undefined) =>
  Boolean(msg?.kind === 'trail' && !msg.text && (msg.thinking?.trim() || msg.tools?.length))

export const mergeToolShelfInto = (target: Msg, source: Msg): Msg => ({
  ...target,
  tools: [...(target.tools ?? []), ...(source.tools ?? [])]
})

const isToolCarryingTrail = (msg: Msg | undefined) => Boolean(msg?.kind === 'trail' && !msg.text && msg.tools?.length)

export const appendToolShelfMessage = (prev: readonly Msg[], msg: Msg): Msg[] => {
  if (!isToolShelfMessage(msg)) {
    return [...prev, msg]
  }

  // Merge only into the block directly above: a tool result belongs to the step
  // it follows. Walking further back (past intervening thoughts) pulled a later
  // tool call into an OLDER `Steps` block, so the trail stopped reading as a
  // chronological hierarchy — the call appeared above the thoughts that came
  // between it and its group.
  const last = prev[prev.length - 1]

  if (!isToolCarryingTrail(last) && !canHoldToolShelf(last)) {
    return [...prev, msg]
  }

  const next = [...prev]

  next[next.length - 1] = mergeToolShelfInto(last!, msg)

  return next
}

const isStepRow = (msg: Msg) => msg.kind === 'trail' && Boolean(msg.thinking?.trim() || msg.tools?.length)

/** Keep the newest `max` step rows, dropping the oldest. Non-step rows (text,
 *  diffs, panels) are never dropped — only the trail rolls. */
export const keepRecentStepRows = (msgs: readonly Msg[], max: number = VISIBLE_STEP_ROWS): Msg[] => {
  let drop = msgs.filter(isStepRow).length - max

  if (drop <= 0) {
    return [...msgs]
  }

  return msgs.filter(msg => {
    if (drop === 0 || !isStepRow(msg)) {
      return true
    }

    drop -= 1

    return false
  })
}
