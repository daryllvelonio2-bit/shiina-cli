export const STREAM_BATCH_MS = 8
export const STREAM_IDLE_BATCH_MS = 8
export const STREAM_SCROLL_BATCH_MS = 48
export const STREAM_TYPING_BATCH_MS = 32
/** Slack over the requested delay before a stream cycle counts as "the main
 *  thread is behind" — the streaming governor backs off above it. Tight enough
 *  that a commit costing more than its own delay is caught in the first cycle
 *  (queue buildup is what reads as stutter), loose enough to ignore timer
 *  granularity and a GC pause. */
export const STREAM_LATE_MS = 8
/** Ceiling the streaming governor backs off to (fewer, larger commits). */
export const STREAM_MAX_BATCH_MS = 80
export const TYPING_IDLE_MS = 150
export const REASONING_PULSE_MS = 500

// A drag-resize fires a burst of SIGWINCH events (one per pixel step in some
// hosts). Each distinct terminal width remounts the visible transcript rows so
// yoga re-measures off live geometry, so reflowing on every tick stutters the
// drag. Coalesce the burst to at most one reflow per this window (~60fps):
// responsive enough to track the drag, cheap enough to stay smooth, and the
// trailing edge always lands the final width so the settled layout is exact.
export const RESIZE_COALESCE_MS = 16

// Two Esc presses within this window discard the draft (Claude Code /
// Gemini CLI parity). Long enough for a deliberate double-tap, short
// enough that two unrelated Escs — dismissing a completion, then a
// selection — don't silently clear the composer.
export const DOUBLE_ESC_MS = 500
