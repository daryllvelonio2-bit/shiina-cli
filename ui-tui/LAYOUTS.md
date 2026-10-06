# Structural TUI layouts

`display.layout` picks one of three structural arrangements for the TUI. A layout
is **presentational only**: the same stores, the same transcript rows, the same
composer — only *where the chrome sits* changes. Nothing about what the model
sees, streams, or stores is affected.

```yaml
# ~/.shiina/config.yaml
display:
  layout: workbench   # minimal | workbench | studio
```

Switch live with `/layout [minimal|workbench|studio|cycle]`. The slash command
patches `$uiState` immediately and persists through `config.set` (`display.layout`),
so the running frame changes instantly and the next session boots into it. An
external edit to `config.yaml` is picked up by the existing `useConfigSync` mtime
poll (no new RPC, no second config path).

## The three arrangements

| region | minimal | workbench | studio |
|---|---|---|---|
| ambient widget rails (reserved columns) | – | ✓ | ✓ |
| ambient widget dock rows | – | ✓ | ✓ |
| floating pet | – | ✓ | ✓ |
| status rule (spinner/model/cwd) | ✓ | ✓ | ✓ |
| file-changes strip | – | ✓ | ✓ |
| sticky-prompt echo | – | ✓ | ✓ |
| transcript scrollbar gutter | – | ✓ | ✓ |
| live agents board | – | above composer | **side column** |
| live todo list | – | under the prompt | **side column** |
| reserved side column | – | – | ✓ (32–48 cols, ≥100 cols terminal) |

- **minimal** — transcript, prompt, composer and one status line. No widget
  chrome, no strips, no gutters. Reading and typing, nothing else.
- **workbench** — the long-standing single-column arrangement; every instrument
  wraps the composer. This is the default and the shape existing users see.
- **studio** — panes: a reserved right-hand instrument column holds the live
  agents board and the todo list for the whole session, beside the transcript.

The single source of truth is `src/domain/layout.ts` (`LAYOUT_SPECS` +
`layoutRegions`). `appLayout.tsx` never branches on a layout id — it asks the
resolved region table whether a region mounts.

### Degradation (never fight the host)

- **Too narrow**: below `STUDIO_MIN_COLS` (100) the side column cannot be
  afforded, so studio's instruments fall back to the workbench placement instead
  of vanishing or squeezing the transcript to a sliver.
- **Phone PTYs** (`TERMUX_TUI_MODE`): reserved panes and rails fight a phone
  terminal's width, so `layoutRegions` is called with `singleColumn: true` —
  single column, no reserved rails. Inline mode (`SHIINA_TUI_INLINE=1`, the
  Termux default) only changes the shell (primary buffer instead of the
  alternate screen); it does not strip the arrangement a wide terminal can
  afford.
- **Floating pet**: it owns the frame's bottom-right corner. In studio that
  corner is the side column, so the transcript keeps its full wrap width and
  reserves no pet gutter there; in workbench it still clears the pet.
- **Unknown / absent / malformed value**: `normalizeLayout` resolves to
  `workbench`. A typo never blanks the frame, and a transient `config.get`
  failure (null payload) preserves the last known layout instead of reverting a
  live `/layout` switch.

## Rendering overhead (opt-perf evidence)

Harness: `ui-tui/scripts/layout-perf.tsx`

```bash
cd ui-tui
PATH=../node_modules/.bin:$PATH NODE_ENV=development SHIINA_DEV_PERF=1 \
  SHIINA_DEV_PERF_MS=0 SHIINA_DEV_PERF_LOG=/tmp/layout-perf.log \
  tsx scripts/layout-perf.tsx
```

Dev-mode React, 140 cols, a 40-row transcript with **no virtual-history
windowing** (the harness stubs `offsets`/`measureRef`, so every commit renders
all 40 rows). Treat these as a pessimistic ceiling and compare shapes, not
absolute values. Per-phase commits are attributed from the `PerfPane`
(`SHIINA_DEV_PERF=1`) rows.

| layout | mount p50 | delta mean | delta p50 | delta p95 | live switch p50 |
|---|---|---|---|---|---|
| minimal | 378 ms | 104 ms | 92 ms | 151 ms | 103 ms (minimal ↔ workbench) |
| workbench | 385 ms | 131 ms | 121 ms | 178 ms | 273 ms (workbench ↔ studio) |
| studio | 347 ms | 123 ms | 117 ms | 157 ms | 269 ms (studio ↔ minimal) |

React commit cost by pane (mean / p95, ms):

| phase | pane | commits | mean | p95 | max |
|---|---|---|---|---|---|
| deltas | transcript | 75 | 46.6 | 56.5 | 81.6 |
| deltas | composer | 76 | 18.5 | 22.1 | 27.1 |
| deltas | prompt | 75 | 0.07 | 0.14 | 0.16 |
| deltas | studio-side | 25 | 0.01 | 0.03 | 0.04 |
| switch | transcript | 18 | 102.5 | 218.0 | 218.0 |
| switch | composer | 22 | 14.7 | 20.7 | 20.8 |
| switch | studio-side | 6 | 3.9 | 5.8 | 5.8 |

### Bottlenecks worth the opt-perf pass

1. **Transcript commits dominate everything** (46.6 ms mean per streaming delta,
   ~102 ms per layout switch, 216 ms on first mount). The layout code adds no
   per-frame work here, but it is the number every other cost is measured
   against — virtual-history windowing is what keeps it survivable in a real
   session.
2. **A layout switch costs one transcript commit, not a rebuild.** Commit counts
   per switch phase are 1 per pane (18 switches → 18 transcript commits, no
   mount cascade): the frame re-renders in place, `virtualHistory.offsets` and
   the scroll box state are untouched. Switching *widths* (into/out of studio's
   36-col column) is the expensive direction — the transcript must re-wrap,
   ~270 ms vs ~103 ms for a same-width switch (minimal ↔ workbench).
3. **`ComposerPane` is the second cost** (~18.5 ms mean per keystroke/delta,
   more than the whole status + prompt + side panes combined). Pre-existing, but
   it is what a layout switch pays on top of the transcript commit.
4. **The studio side column is nearly free while idle** — 0.01 ms mean per delta
   (the `LiveAgentsPanel`/`LiveTodoPanel` children return null with no live
   agents/todos); it only costs ~3.9 ms on the switch/mount paint. The 32–48 col
   reservation shrinks the transcript's wrap width, which is the real price of
   studio, not the panels.
5. **`memo()` boundaries hold.** `AppLayout`, `TranscriptPane`, `ComposerPane` and
   `StatusRulePane` keep their shallow compares: the region table is memoized on
   `[layout, cols]`, and `TranscriptPane` takes primitives (no object prop that
   would fail every compare) — a keystroke still repaints the composer without
   re-rendering the transcript (contract test:
   `src/__tests__/appLayoutComposerMemo.test.tsx`).

## Tests

- `src/__tests__/layout.test.ts` — region/spec contract, fail-safe normalisation,
  side-column math and degradation.
- `src/__tests__/layoutFrame.test.tsx` — which regions actually mount per layout,
  a live store-driven switch, and message-content parity across layouts.
- `tests/tui_gateway/test_config_layout.py` — `display.layout` is read/written
  through the loader the TUI uses (`config.get`/`config.set`), with an absent key
  resolving to the default.
