import { STREAM_LATE_MS, STREAM_MAX_BATCH_MS } from '../config/timing.js'

/**
 * Self-clocking delay for the streaming commit loop.
 *
 * A streaming commit is not free: it re-lays-out the mounted window plus the
 * growing reply, and on a long session that work can exceed the frame budget.
 * With a flat 16 ms delay the timer then fires faster than the main thread can
 * paint — callbacks queue, frames drop, and the UI stutters in bursts. Measuring
 * how long a full cycle actually took (delay + the work it triggered) is the
 * cheapest honest signal: over budget → back off, comfortable → tighten. The
 * loop ends up paced just under what the machine can render, which is what
 * "smooth" means here — no queue, no bursts.
 *
 * `cycleMs` is the wall time between two consecutive fires (so it includes the
 * previous commit's work). `floor` is the interaction floor: while the user is
 * typing or scrolling, commits must not be stretched past it.
 */
export const adaptStreamDelay = (delay: number, cycleMs: number, floor: number): number => {
  const boundedDelay = Math.min(STREAM_MAX_BATCH_MS, delay)
  return cycleMs > boundedDelay + STREAM_LATE_MS
    ? Math.min(STREAM_MAX_BATCH_MS, Math.max(boundedDelay + 1, Math.round(boundedDelay * 1.6)))
    : Math.max(floor, Math.round(boundedDelay * 0.85))
}
