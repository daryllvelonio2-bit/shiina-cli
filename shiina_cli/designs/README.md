# TUI designs

A **design** is the complete look of the terminal UI: its colours, its glyph
vocabulary, its borders, its prompt symbol, its animations, which status fields
it shows, and how it arranges the frame. Designs are **pure data** — adding one
never requires a code change.

```
~/.shiina/designs/          ← your editable designs (this is the folder)
~/.shiina/designs/README.md ← this file
```

Shipped built-ins live in the install tree at `shiina_cli/designs/`. A file in
your folder with the same name WINS, so you can override a built-in without
losing it. `shiina design init` copies the built-ins into your folder to edit.

## Turning one on

```yaml
# ~/.shiina/config.yaml
display:
  design: codex
```

Or live, from inside the TUI: `/design codex` (bare `/design` cycles,
`/design status` reports). Independent of `display.layout` — a design may also
carry a region/progress profile, but you can pair any design with any layout.

## Inheriting

Every design is merged onto `default`, so declare **only what you change**:

```yaml
name: my-design
extends: default
prompt: "λ"
colors:
  accent: "#7c3aed"
```

Anything omitted keeps `default`'s value. A malformed value is ignored and the
built-in default is used — a typo never blanks the UI.

---

# Schema

## Top level

| key | type | notes |
|---|---|---|
| `name` | string | Should match the filename stem. Identifies the design. |
| `description` | string | Shown by `shiina design list`. |
| `extends` | string | Base design to inherit from. Default `default`. |
| `dynamic` | bool | `true` = take the palette live from the desktop scheme (see **Colour**). |
| `prompt` | string | Composer prompt symbol, e.g. `"❯"`, `">"`, `"▌"`. |

## Colour

Two modes.

**1. Explicit palette** — any subset of these keys. Unset keys inherit.

```yaml
colors:
  primary: "#3b82f6"          # headline / brand tone
  accent: "#38bdf8"           # the main highlight: headers, active markers
  border: "#334155"
  text: "#e2e8f0"             # default body text
  muted: "#64748b"            # dim asides, hints, metadata
  label: "#94a3b8"
  ok: "#4ade80"               # success / completed steps
  warn: "#fbbf24"
  error: "#f87171"

  tool: "#38bdf8"             # tool-call bullets, tool spinner
  thinking: "#64748b"         # reasoning body text
  prompt: "#38bdf8"           # composer prompt
  shellDollar: "#a78bfa"      # ! shell-mode prompt

  diffAdded: "#4ade80"
  diffRemoved: "#f87171"
  diffAddedWord: "#16a34a"
  diffRemovedWord: "#dc2626"

  syntaxString: "#4ade80"
  syntaxNumber: "#fbbf24"
  syntaxKeyword: "#c084fc"
  syntaxComment: "#64748b"

  sessionLabel: "#94a3b8"
  sessionBorder: "#334155"

  statusBg: "#1e293b"
  statusFg: "#e2e8f0"
  statusGood: "#4ade80"
  statusWarn: "#fbbf24"
  statusBad: "#f87171"
  statusCritical: "#ef4444"
  selectionBg: "#334155"

  completionBg: "#1e293b"
  completionCurrentBg: "#334155"
  completionMetaBg: "#1e293b"
  completionMetaCurrentBg: "#334155"
```

**2. Dynamic** — `dynamic: true` takes the palette from the live desktop scheme
(the same source the `caelestia` skin uses). Use this when the terminal sits on
changing wallpaper and a fixed accent would fight the background. Individual
`colors` keys still win over the live ones, so a dynamic design can pin one tone
and inherit the rest.

## Chrome identity

```yaml
design:
  density: compact        # compact | normal | roomy  — vertical rhythm
  panel: round            # single | round | double | bold | none — box border language
  alert: double           # border for attention panels (approvals, warnings).
                          # Independent of `panel`; defaults to the built-in "double".
                          # `none` draws no box at all and reclaims the border cells,
                          # so a borderless design is a real layout, not a recoloured one.
  rule: "─"               # horizontal rule character

  # What flanks a title/header — the lines beside it.
  flank: rule             # rule | space | none
                          #   rule  = draw the rule character either side
                          #   space = blank air, keeps the title centred
                          #   none  = nothing either side

  # Header treatment: label transform, weight, and what precedes the label.
  header:
    case: none            # upper | lower | none
    emphasis: bold        # bold | dim | none
    marker: chevron       # chevron | rule | none
                          #   chevron = the expand marker (default)
                          #   rule    = a rule dash, same as the status line's lead
                          #   none    = a bare label (the row stays clickable)

  # Nesting unit for tool output, subagents and ledger steps. Every field is a
  # string, so `''` goes flat and a wider `unit` steps deeper.
  indent:
    unit: "  "            # one nesting level, repeated per depth; '' = flat
    stem: "│ "            # rail inside a level whose branch continues
    branch: "├─ "         # lead before a non-final child
    last: "└─ "           # lead before the final child

  # Container chrome spacing. Omit any key to take it from `density`.
  spacing:
    overlayPadX: 1        # left/right padding inside an overlay
    overlayPadY: 1        # top/bottom padding inside an overlay
    panelPadX: 2          # left/right padding inside a bordered panel
    panelPadY: 1          # top/bottom padding inside a bordered panel
    insetPadX: 1          # left/right padding inside a compact box / side pane
    insetPadY: 0          # top/bottom padding inside a compact box / side pane
    rowGap: 0             # gap between rows inside a group
    sectionGap: 1          # gap between sections

  glyphs:
    chevronClosed: "▸"    # a collapsed section
    chevronOpen: "▾"      # an expanded section
    bullet: "●"           # tool-call / list marker
    check: "✓"            # a completed step / enabled entry
    cross: "✗"            # a failed / disabled entry
    pending: "·"          # a not-yet-started step
    active: "▸"           # the active row marker
    progress: "▶"         # a running / working row
    ellipsis: "…"         # a starting / loading row
    waiting: "?"          # a row waiting on input
    warn: "!"             # a warning marker
    off: "○"              # unavailable / not-authenticated
    selected: "*"         # the currently-selected entry
    separator: " │ "      # status-rule segment separator (include spacing)
    dotSeparator: " · "   # inline separator: compact meta lines and list joins (include spacing)
    barFill: "█"          # a filled meter cell (usage / context bars)
    barEmpty: "░"         # the unfilled remainder of a meter
    statusHead: "─ "      # leading status-rule dash (include trailing space)
    chain: "⛓"            # subagent / delegation count
    cache: "◎"            # cache-hit readout
    latency: "◷"          # average-latency readout
    tps: "↑"              # tokens-per-second readout
    focus: "◉"            # focus-view badge
    idle: "✓"             # idle clock / turn finished
    resume: "↩"           # "resumes when the subagent finishes" hint
    alert: "⚠"            # attention: an approval, a destructive confirm
    blocked: "⊘"          # a refused / rejected request
    busy: "⏳"             # work in progress: the busy tab, a scheduled change
    checkboxOn: "☑"       # a checked checklist item
    checkboxOff: "☐"      # an unchecked checklist item
    disclosure: "▶"       # opens a collapsible block (`<summary>`)
    dot: "•"              # a markdown list item / masked input
    halt: "■"             # interrupted / cancelled
    partial: "◐"          # partially complete (a subagent finalizing)
    timeout: "⌛"          # timed out
    railVertical: "│"     # a vertical line: tree rails, blockquote rail, scroll track
    railTee: "├"          # a tree rail that continues below the row
    railElbow: "└"        # a tree rail that ends at the row
    scrollThumb: "┃"      # the scrollbar thumb (a heavier vertical than the track)
    rulerTick: "┼"        # a major tick on a timeline ruler

  status_bar:
    # Order AND allowlist. Omit the key (or set null) for the built-in set.
    # Unknown ids are dropped.
    segments: [model, cwd, tokens, cost, duration]
```

Available `status_bar.segments` ids are the ones the status rule knows; run
`shiina design keys` for the full key list, and `/status` in the TUI to see the
live segment ids.

## Motion

Animations are frame sets, chosen by name. Both keys are lists — one is picked
per session, so a design has a signature *vocabulary* rather than a single loop.

```yaml
spinner:
  think: [helix, breathe, orbit]     # while reasoning
  tool: [cascade, scan, diagswipe]   # while a tool runs
```

Available names: `braille`, `braillewave`, `dna`, `scan`, `rain`, `scanline`,
`pulse`, `snake`, `sparkle`, `cascade`, `columns`, `orbit`, `breathe`,
`waverows`, `checkerboard`, `helix`, `fillsweep`, `diagswipe`.

The classic CLI's spinner faces are separate — see the skin's `spinner.*`.

## Structure

Optional. A design can also decide *where* chrome sits and *how much* progress
shows; unset keys inherit the layout's own profile, so most designs leave this
out.

```yaml
layout:
  regions:                # true/false per region
    rails: false          # ambient corner-widget columns
    dock: true            # ambient dock rows
    pet: false            # floating pet
    statusRule: true
    fileChanges: true
    agentsDock: false     # live subagent board above the composer
    todoUnderPrompt: false
    stickyPrompt: false
    scrollbar: true
    sideColumn: false     # reserved right-hand instrument column
    ledger: true          # the persistent step list

  sections:               # hidden | collapsed | live | expanded, per progress section
                          # live = open during the turn, folds to one row when it settles
    thinking: collapsed
    tools: expanded
    subagents: expanded
    activity: collapsed
```

---

# For agents

Everything you need is data; there is nothing to import to *author* a design.

**Discover**: `shiina design list` (names + source + description),
`shiina design path` (the folder), `shiina design show <name>` (the resolved
design, after inheritance), `shiina design segments` (valid status-bar ids).

**Author**: write `~/.shiina/designs/<name>.yaml` with `name: <name>` and
`extends: default`, then set `display.design: <name>`. Adding a design needs no
code change, no rebuild, and no restart of anything but the TUI.

**Widgets / internals** (only if you are writing code against this):

| what | where |
|---|---|
| schema types | `ui-tui/src/design.ts` — `Design`, `DesignBorders`, `DesignGlyphs`, `DesignHeader`, `DesignIndent`; `ui-tui/src/domain/designSpec.ts` — the design-file `DesignSpec` |
| applying it | `ui-tui/src/domain/applyDesign.ts` — `applyDesign(theme, spec)` |
| the loader | `shiina_cli/design_engine.py` — `load_design`, `list_designs`, `get_active_design` |
| config key | `display.design` (`shiina_cli/config_defaults.py`) |
| CLI | `shiina design` (`shiina_cli/design_cmd.py`) |
| existing precedent | `shiina_cli/skin_engine.py` — same user→builtin→default rule |

A design is applied in exactly one place — where the theme is resolved — so any
component reading `t.design.*`, `t.brand.prompt` or `t.color.*` honours it
without knowing designs exist.
