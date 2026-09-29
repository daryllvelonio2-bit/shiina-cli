import type { HapticIntent } from '@/lib/haptics'

// Minimum gap between keystroke haptics. Printable typing stays silent by
// design (the global 5/sec rate-limit would turn fast typing into a buzz);
// Enter/Ctrl-C/Esc are human-paced confirmations, and this window also covers
// a held-down Enter repeat.
export const KEY_HAPTIC_THROTTLE_MS = 120

/** Map an xterm onData chunk to its key haptic, if it carries a control key.
 *  Pure (no timing) so it's unit-testable; callers own the throttle. */
export function hapticIntentForInput(data: string): HapticIntent | null {
  if (!data) {
    return null
  }

  // Enter (CR in most shells, LF for bracketed multi-line paste).
  if (data.includes('\r') || data.includes('\n')) {
    return 'submit'
  }

  // Ctrl-C interrupt.
  if (data.includes('\x03')) {
    return 'cancel'
  }

  // A lone Escape (mode cancel / dismiss). Longer ESC-prefixed sequences are
  // arrow/function keys, not a deliberate Esc press.
  if (data === '\x1b') {
    return 'tap'
  }

  return null
}
