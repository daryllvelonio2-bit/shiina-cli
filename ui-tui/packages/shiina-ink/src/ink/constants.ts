// Shared frame interval for render throttling and animations.
// Default to 8ms (~120fps max cap), or configurable via SHIINA_TUI_FPS / SHIINA_TUI_FRAME_MS.
const envFps = process.env.SHIINA_TUI_FPS ? parseInt(process.env.SHIINA_TUI_FPS, 10) : 0
const envFrameMs = process.env.SHIINA_TUI_FRAME_MS ? parseInt(process.env.SHIINA_TUI_FRAME_MS, 10) : 0

export const FRAME_INTERVAL_MS = envFrameMs > 0
  ? envFrameMs
  : envFps > 0
    ? Math.max(1, Math.round(1000 / envFps))
    : 8

// Keep clock-driven animations at full speed when terminal focus changes.
// We still pause entirely when there are no keepAlive subscribers.
export const BLURRED_FRAME_INTERVAL_MS = FRAME_INTERVAL_MS

// Issue #31486 (stdout-backpressure strand): when the previous frame's
// stdout.write has NOT drained yet (terminal parser overwhelmed by a wide
// CR+LF burst — CJK + ANSI tool output on a high-context session), piling
// another write on the backed-up pipe both wastes the frame and keeps the
// macrotask queue churning, starving the stdin 'readable' callback. We
// instead COALESCE: skip the frame and retry on the drain tick. This ceiling
// caps how many consecutive frames we'll coalesce before forcing a write
// through, so a terminal whose drain callback never fires (e.g. EIO on
// flush) can't wedge the renderer permanently — it self-heals once the pipe
// recovers. ~10 frames at the drain-tick cadence is a few hundred ms of
// breathing room, well under any human-perceptible render stall.
export const MAX_COALESCED_BACKPRESSURE_FRAMES = 10
