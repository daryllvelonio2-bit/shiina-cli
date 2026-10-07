import type { DetailsMode, SectionName, SectionVisibility } from '../types.js'

const MODES = ['hidden', 'collapsed', 'live', 'expanded'] as const

export const SECTION_NAMES = ['thinking', 'tools', 'subagents', 'activity'] as const

// Out-of-the-box per-section defaults — applied when the user hasn't pinned
// an explicit override and layered ABOVE the global details_mode:
//
//   - thinking / tools: live — open while the turn is running (reasoning and
//     tool calls read as a live transcript), then fold to a single header row
//     the moment the turn settles. `expanded` stays open for good; `collapsed`
//     never auto-opens.
//   - activity: hidden — ambient meta (gateway hints, terminal-parity
//     nudges, background notifications) is noise for typical use.  Tool
//     failures still render inline on the failing tool row, and ambient
//     errors/warnings surface via the floating-alert backstop when every
//     panel resolves to hidden.
//   - subagents: not set — falls through to the global details_mode so
//     spawn trees stay under a chevron until a delegation actually happens.
//
// Every one of these is design-driven: a design's `layout.sections` block
// (e.g. designs/codex.yaml) overrides them, and `display.sections.<name>` in
// config.yaml or `/details <name> live|collapsed|hidden|expanded` pins one at
// runtime.
const SECTION_DEFAULTS: SectionVisibility = {
  thinking: 'live',
  tools: 'live',
  activity: 'hidden'
}

const THINKING_FALLBACK: Record<string, DetailsMode> = {
  collapsed: 'collapsed',
  full: 'expanded',
  truncated: 'collapsed'
}

const norm = (v: unknown) =>
  String(v ?? '')
    .trim()
    .toLowerCase()

export const parseDetailsMode = (v: unknown): DetailsMode | null => MODES.find(m => m === norm(v)) ?? null

export const isSectionName = (v: unknown): v is SectionName =>
  typeof v === 'string' && (SECTION_NAMES as readonly string[]).includes(v)

export const resolveDetailsMode = (d?: { details_mode?: unknown; thinking_mode?: unknown } | null): DetailsMode =>
  parseDetailsMode(d?.details_mode) ?? THINKING_FALLBACK[norm(d?.thinking_mode)] ?? 'collapsed'

// Build SectionVisibility from a free-form blob.  Unknown section names and
// invalid modes are dropped silently — partial overrides are intentional, so
// missing keys fall through to SECTION_DEFAULTS / global at lookup time.
export const resolveSections = (raw: unknown): SectionVisibility =>
  raw && typeof raw === 'object' && !Array.isArray(raw)
    ? (Object.fromEntries(
        Object.entries(raw as Record<string, unknown>)
          .map(([k, v]) => [k, parseDetailsMode(v)] as const)
          .filter(([k, m]) => !!m && isSectionName(k))
      ) as SectionVisibility)
    : {}

// Effective mode for one section: explicit override → global command mode →
// the layout's own progress defaults → built-in live-stream defaults → global
// config mode.
//
// The `commandOverride` flag is set for in-session `/details <mode>` changes.
// That command should immediately apply to every section, including sections
// with built-in defaults like thinking/tools=expanded and activity=hidden. On
// startup/config sync we keep those defaults layered above the persisted global
// config so the TUI still opens live reasoning/tools by default unless the user
// pins explicit per-section overrides.
//
// `layoutDefaults` is the layer a TUI layout contributes (`display.layout`):
// minimal folds progress to compact rows, timeline keeps tool calls and
// subagent trees open. It sits BELOW the explicit `sections` override and
// below `/details`, so a user pin always wins, and it never enters
// `detailsRequested()` — a layout must not make settled turns paint their trail.
export const sectionMode = (
  name: SectionName,
  global: DetailsMode,
  sections?: SectionVisibility,
  commandOverride = false,
  layoutDefaults?: SectionVisibility
): DetailsMode =>
  sections?.[name] ?? (commandOverride ? global : (layoutDefaults?.[name] ?? SECTION_DEFAULTS[name] ?? global))

/** Whether the user asked for details explicitly — `display.sections.*` in
 *  config or an in-session `/details <mode>` — rather than leaving the built-in
 *  defaults in charge. A finished turn paints its trail only when this is true:
 *  otherwise the answer stands alone and the work behind it is invisible until
 *  someone asks for it. */
export const detailsRequested = (sections?: SectionVisibility, commandOverride = false): boolean =>
  !!commandOverride || Object.keys(sections ?? {}).length > 0

export const nextDetailsMode = (m: DetailsMode): DetailsMode => MODES[(MODES.indexOf(m) + 1) % MODES.length]!

/** Does a section render open on mount?
 *
 *  - `expanded` — yes, always (an explicit "keep this in my face").
 *  - `live`     — only for the in-progress turn's block; a settled row folds
 *                 to its single header line (`isLive`).
 *  - `collapsed` / `hidden` — no.
 *
 *  `isLive` is the renderer's own signal that this row belongs to the running
 *  turn (`preferExpandedThinking`), not a user preference. */
export const opensByDefault = (mode: DetailsMode, isLive: boolean): boolean =>
  mode === 'expanded' || (mode === 'live' && isLive)
