# Shiina Agent - Development Guide

Instructions for AI coding assistants and developers working on the shiina-agent codebase.
This root file holds only what applies everywhere. Each area has its own `AGENTS.md` (aim for
~8k chars; `agent/subdirectory_hints.py` delivers up to 32k and truncates head/tail with a warning
past that); see the **routing table** at the end and read the area file before editing in that area.

**Never give up on the right solution.**

## What Shiina Is

Shiina is a personal AI agent that runs the same agent core across a CLI, a messaging
gateway (Telegram, Discord, Slack, ~20 platforms), a TUI, and an Electron desktop app. It
learns across sessions (memory + skills), delegates to subagents, runs scheduled jobs, and
drives a real terminal and browser. It is extended primarily through **plugins and skills**,
not by growing the core.

Two invariants shape almost every design decision and are the lens for reviewing any change:

- **Per-conversation prompt caching is sacred:** A long-lived conversation reuses a cached prefix every turn. Never mutate past context, swap toolsets, reload memories, or rebuild system prompts mid-conversation (invalidates cache and multiplies cost). Exception: context compression. Slash commands mutating prompt state default to deferred invalidation (next session) with opt-in `--now`.
- **The core is a narrow waist; capability lives at the edges:** Every model tool is sent on every API call. Keep the core schema minimal; add capability via CLI command + skill, service-gated tool (`check_fn`), or plugin.

## Development Principles & Quality Gates

- **Fix real bugs, well:** Reproduce on current `main`, point to exact line, fix the whole bug class including sibling call paths. Verify claim and design intent against codebase before patching.
- **Expand reach at the edges:** Adapters, channels, providers, models, UI features integrate via existing setup/config UX (`shiina tools`, `shiina setup`).
- **Refactor god-files into clean modules:** Extract into facade + siblings (`<stem>_<topic>.py`).
- **Extend, don't duplicate:** Check existing infra first. For 3+ variants in a category, design an ABC + orchestrator.
- **Behavior contracts over snapshots:** Tests assert relationships between data, never freeze current catalog values.
- **Real E2E validation:** Exercise real imports against temp `SHIINA_HOME` (two homes: A→B→A under multiplex).
- **Cache-, alternation-, and invariant-safe:** Preserve prompt caching, strict role alternation, byte-stable system prompt.
- **What we reject:** Speculative hooks without concrete consumers; new `SHIINA_*` env vars for non-secrets (use `config.yaml`); new core tools when terminal/file/skill suffice; `offset`/`limit` pagination on instructional tools; un-gated telemetry; third-party vendor connectors in core tree (ship as standalone plugins).

### The Footprint Ladder (new capability decision)

Choose the highest (least-footprint) rung that correctly solves the problem:

1. **Extend existing code** — a variation of something that exists. Zero new surface.
2. **CLI command + skill** — config/state/infra expressible as shell commands; the agent runs
   `shiina <subcommand>` guided by a skill. Default for subscriptions, scheduled tasks,
   service setup (`shiina webhook`, `shiina cron`, `shiina tools`).
3. **Service-gated tool (`check_fn`)** — needs structured params/returns AND only appears when
   a prerequisite is configured (Home Assistant tools, memory-provider tools). This rung gates
   reachability/opt-in process-wide; a capability that varies per SESSION (who is watching) is
   a named toolset folded in by the toolset resolver, not a `check_fn` — see "Surface capability
   is a property of the SESSION" below.
4. **Plugin** — third-party/niche/user-specific; lives in `~/.shiina/plugins/` or a pip
   package, discovered at runtime.
5. **MCP server (in the catalog)** — genuinely a tool but not core-fundamental. Zero permanent
   core-schema footprint, reusable by any MCP host, reached via the built-in MCP client.
6. **New core tool** — only when fundamental, broadly useful to nearly every user, and
   unreachable via terminal + file or an MCP server (terminal, read_file, web_search,
   browser_navigate).

### Surface capability is session-scoped, never process-scoped

Capabilities dependent on client UI (desktop panes, in-app browser, reactions) resolve availability from the **session's platform**, not backend env vars like `SHIINA_DESKTOP=1` (client and backend may run on separate hosts).
- **Toolsets as surface gates:** Place UI-dependent tools in named toolsets (`desktop_ui`), folded in via `_load_enabled_toolsets(platform)`.
- **`check_fn` handles reachability:** `check_fn` resolves process-wide prereqs/reachability, not per-session client surfaces.
- **Process identity vs UI session:** `SHIINA_DESKTOP=1` means the process was spawned by Electron (for cron/dist), NOT that a GUI session is attached.

## Development Environment

```bash
source .venv/bin/activate   # or: source venv/bin/activate
```
`scripts/run_tests.sh` probes `.venv`, then `venv`, then `$HOME/.shiina/shiina-agent/venv`
(worktrees sharing the main checkout's venv).

## Project Structure

Counts shift constantly; the filesystem is canonical. Load-bearing entry points:

```
shiina-agent/
├── run_agent.py          # AIAgent facade; the turn loop lives in agent/turn_*.py
├── model_tools.py        # Tool orchestration, discover_builtin_tools(), handle_function_call()
├── toolsets.py           # TOOLSETS dict, _SHIINA_CORE_TOOLS
├── cli.py                # ShiinaCLI (REPL, slash dispatch) + shiina_cli/cli_*_mixin.py
├── shiina_state.py       # SessionDB facade; shiina_state_*.py siblings
├── shiina_constants.py   # get_shiina_home(), display_shiina_home() — profile-aware paths
├── shiina_logging.py     # agent.log / errors.log / gateway.log (profile-aware)
├── batch_runner.py       # Parallel batch processing
├── agent/                # turn_*.py loop phases, providers, memory, compression, prompt builder
├── shiina_cli/           # CLI subcommands, setup, config, plugins loader, skins, updater
│   └── web_routers/      # Dashboard FastAPI routers (one per surface); web_server.py mounts them
├── tools/                # Tool implementations, auto-discovered via tools/registry.py
│   └── environments/     # Terminal backends (local, docker, ssh, modal, daytona, singularity)
├── gateway/              # run.py facade + run_*.py phases + session*.py + platforms/
│   ├── platforms/        # One adapter per platform; see platforms/ADDING_A_PLATFORM.md
│   └── builtin_hooks/    # Always-registered gateway hooks (extension point; none shipped)
├── plugins/              # memory/, context_engine/, model-providers/, kanban/, image_gen/, ...
├── skills/               # Built-in skills (by category)   optional-skills/: shipped, not active
├── ui-tui/               # Ink (React) terminal UI — `shiina --tui`
├── tui_gateway/          # Python JSON-RPC backend for TUI + Desktop — server.py + methods_*.py
├── apps/desktop/         # Electron desktop app (+ apps/shared JSON-RPC client)   web/: dashboard SPA
├── acp_adapter/          # ACP server (VS Code / Zed / JetBrains)
├── cron/                 # jobs.py + scheduler.py (+ scheduler_*.py)
├── evals/                # Offline benchmarks (codebase_navigability/, compaction/, ...)
├── scripts/              # run_tests.sh, release.py, check_compat_pointers.py, ci/
├── website/              # Docusaurus docs (developer-guide/ holds the long-form area docs)
└── tests/                # Pytest suite (~39k tests / ~3.7k files, Sep 2026)
```

**User state:** `~/.shiina/config.yaml` (settings), `~/.shiina/.env` (secrets only),
`~/.shiina/logs/` (`agent.log` INFO+, `errors.log` WARNING+, `gateway.log`); all
profile-aware via `get_shiina_home()`. Browse logs with `shiina logs [--follow] [--level] [--session]`.

**Dependency chain:** `tools/registry.py` (no deps) ← `tools/*.py` (register at import) ←
`model_tools.py` (discovery) ← `run_agent.py`, `cli.py`, `batch_runner.py`, `environments/`.

### Facade + siblings layout (Sep 2026 decomposition)

Every former god file is a **facade** (public entry points + the names other packages import)
plus **siblings** `<stem>_<topic>.py` in the same directory, each owning one topic. Largest
families: `shiina_state.py` (21), `gateway/run.py` (15), `tools/mcp_tool.py` (15),
`shiina_cli/kanban.py` (14), `shiina_cli/web_server.py` (13 + 24 routers), `shiina_cli/auth.py`
(12), `tools/browser_tool.py` (11), `cli.py` (12 `shiina_cli/cli_*_mixin.py`), `run_agent.py`
(`agent/turn_*.py`, `agent_init.py`, `conversation_loop.py`).

- **Find code by topic, not by facade:** `grep -rn "def name" <dir>/<stem>_*.py`. Reading the
  facade first is the expensive way (`evals/codebase_navigability/`).
- **Siblings may import each other and late-import the facade** inside functions. A facade
  never imports a sibling at module level *and* gets imported by that sibling at module level.
- **Patch where production reads.** Siblings often do `from <facade> import name` inside the
  function so `monkeypatch.setattr(facade, "name", ...)` is the seam; a patch on the defining
  module passes silently. Check the call site's binding before writing a patch target
  (blind repointing to defining modules broke 130+ tests).
- **Compat pointers are OFF LIMITS in-tree.** Old import paths kept alive for external plugins
  (`PLUGIN-COMPAT` blocks, `COMPAT_MANIFEST.md`, `compat_manifest.json`) must not be used by
  in-tree code or tests; `scripts/check_compat_pointers.py` runs in CI, and
  `-W error::shiina_cli.plugin_compat.ShiinaPluginCompatWarning` catches them in the suite.
  They are removed 2026-09-14 by reverting one commit. Import from the defining module.
- **Don't recreate god files.** A file passing ~2,000 lines or a function passing ~300 lines /
  cyclomatic complexity 30 is the signal to split along `<stem>_<topic>` FIRST, in its own
  commit. New behaviour goes in a new or topical sibling — never appended to a facade.
- **No `if/elif` ladders ≥ 4 branches keyed on a name/kind** — use a dict/table → handler
  (`_SLASH_DISPATCH` in `cli.py`, `_command_handler_table` in the gateway are the shape).
- **No re-export shims for internal moves** ("keep the old name importable"). Internal paths
  are not API; external compat is handled ONCE by the compat layer, not per PR.
- **Moving a symbol means fixing its docs in the same PR:** grep `website/docs`,
  `skills/`, and every `AGENTS.md` for the old `path.py` + symbol (23 doc files went stale
  after the refactor). `evals/codebase_navigability/static_metrics.py <tree> <label>` measures
  file/function/CC/elif distributions before/after a large PR in ~2 min.

## Code Shape Rules (all languages)

- No "defense-in-depth" wrappers, `try/except: pass` around code that cannot fail, or flags
  nobody sets. Docstrings/comments keep the WHY, cut the WHAT.
- **Never infer process identity from argv substrings** (`"serve" in cmdline`) — the bug class
  behind ~10 fleet-update issues (#90778, #87594, #78089, #76129, #91964). Use the canonical
  matchers `gateway.status.looks_like_gateway_command_line` and
  `shiina_cli.update_cmd._shiina_holder_subcommand`; flag sets are DERIVED from the parser
  (`_holder_value_flags()`), never hand-written; match FULL cmdlines and truncate only for
  display. Details: `shiina_cli/AGENTS.md`.
- **Never hardcode `~/.shiina`.** `get_shiina_home()` for code paths, `display_shiina_home()`
  for user-facing text (both from `shiina_constants`). Hardcoding breaks profiles (5 bugs in
  PR #3575). Profile operations themselves are HOME-anchored
  (`_get_profiles_root()` = `Path.home()/.shiina/profiles`) so `shiina -p x profile list`
  sees all profiles — intentional, not a bug.
- **Explicit profile scope binding outside turns:** A profile binds home, secrets, and terminal scope. Outside a turn, code must explicitly bind profile scope via `_profile_runtime_scope` (turn), `@_profile_scoped` / `_session_profile_runtime_scope` (RPC/teardown), `_profile_cron_scope` (cron ticker), or `served_profile_child_env` (child spawns; never raw `os.environ.copy()`). Module constants derived from `.env`/home are forbidden; key slots by `shiina_home_key()` or resolve at runtime. Fail-closed reads apply after `set_multiplex_active(True)`. Prove with two homes (A→B→A).
- **Argparse alias dispatch:** `add_parser("list", aliases=["ls"])` sets `dest` to the literal
  the user typed (`"ls"`). Dispatch must accept both (caught PTY-testing `shiina webhook ls`).
- **Don't wire in dead code without E2E validation.** Unshipped code was dead for a reason;
  E2E the real resolution chain with real imports against a temp `SHIINA_HOME` first.

### TypeScript style (desktop, TUI, website, future TS packages)

Small nanostores over component state when state is shared or read by distant UI; each
feature owns its atoms (chat near chat, shared in `src/store`); rendering components use
`useStore`, non-rendering actions read `$atom.get()`; never thread state through three
components when the leaf can subscribe; persistence sits beside the atom that owns it. Route
roots stay thin (compose routes + shell, never controllers). No monolithic hooks — one narrow
job each; colocated action modules over god hooks. Pure side-effect callbacks use the terse
void form `onState={st => void setGatewayState(st)}`; async handlers make intent explicit
`onClick={() => void save()}`. Interfaces for public props and shared object shapes (not
`type X = {...}`); extend React primitives (`React.ComponentProps<'button'>`, `Omit`, `Pick`).
Table-driven beats condition ladders for ids/routes/views. `src/app` owns routes/pages,
`src/store` shared atoms, `src/lib` pure helpers.

## Dependency Pinning Policy

All dependencies carry upper bounds (litellm compromise #2796/#2810; Mini Shai-Hulud worm,
May 2026). PyPI: `>=floor,<next_major` (`"httpx>=0.28.1,<1"`); pre-1.0: `<0.(minor+2)`
(`>=0.29,<0.32`). Git URLs: 40-char commit SHA. GitHub Actions: SHA + `# vN` comment. CI-only
pip: `==exact`. A bare `>=X.Y.Z` is rejected by CI and reviewers. Run `uv lock` after
changing `pyproject.toml`. Reference: #2810 (bounds), #9801 (SHA pinning + audit CI).

## Commits, Merges, PRs

- **Squash merges from stale branches silently revert recent fixes.** Before squash-merging,
  bring the branch to `main` (`git fetch origin main && git reset --hard origin/main`, re-apply
  the PR's commits). Verify with `git diff HEAD~1..HEAD` after merging — unexpected deletions
  are a red flag.
- Salvage by cherry-pick so contributor authorship survives (see rubric).
- Tests per fix: 1–2 INVARIANT tests (behaviour contract, proven red on base), never
  change-detectors; ≤ 2 tests is the salvage bar too. Reject/rewrite in salvaged diffs:
  appendages to facades, new god helpers, compat aliases, wrappers.

## Testing (applies everywhere)

**ALWAYS use `scripts/run_tests.sh`**, never bare `pytest`. It enforces CI parity: credential
vars unset, `TZ=UTC`, `LANG=C.UTF-8`, `SHIINA_HOME` → temp dir, and per-file subprocess
isolation via `scripts/run_tests_parallel.py` (no xdist; workers scale with CPU count) so
module-level dicts/ContextVars cannot leak between files. Direct `pytest` on a big machine
with API keys set has caused repeated "works locally, fails in CI" incidents (and the reverse).

```bash
scripts/run_tests.sh                                    # full suite
scripts/run_tests.sh tests/gateway/                     # one directory
scripts/run_tests.sh tests/agent/test_foo.py -k test_x  # runner is file-granular; -k narrows
scripts/run_tests.sh -v --tb=long                       # pytest flags pass through
```

- **Flake policy:** a failing FILE is retried once in a fresh subprocess (`--file-retries`;
  `SHIINA_TEST_FILE_RETRIES=0` disables). Pass-on-retry is green but printed under `⚠ FLAKY`
  with both outputs — a bug to fix, not noise. Timing tests must not assume a quiet runner:
  wall-clock bounds ≥ 2s, event-based sync, no `assert not _wait_until(...)` races.
- **Placement mirrors the source tree.** A test lives in `tests/<top-level source dir>/` (`tests/shiina_cli/`,
  `tests/agent/`, `tests/shiina_state/`, `tests/gateway/relay/`, ...); installer/updater script tests
  under `tests/scripts/{install,desktop_update}/`. Only tests of root-level modules (`batch_runner`,
  `utils`, `shiina_constants`, packaging) sit directly in `tests/`. No issue numbers in filenames —
  cite the issue in the module docstring (`test_89315_x.py` → `test_x.py`, "Regression for #89315").
- **Placement (CI lanes):** `scripts/ci/classify_changes.py` picks jobs by changed files. A Python test
  asserting about `package.json`, `package-lock.json`, `tsconfig.json`, or `.ts/.tsx/.js/
  .mjs/.cjs` sources will not run on a JS-only PR (green on PR, red on `main` where the
  classifier fails open). Such tests belong in the vitest suite, not `tests/*.py`.
- **Tests must not write to `~/.shiina/`.** The autouse `_isolate_shiina_home` fixture in
  `tests/conftest.py` redirects `SHIINA_HOME`; never hardcode `~/.shiina/` in tests. Profile
  tests also mock `Path.home()` so `_get_profiles_root()` / `_get_default_shiina_home()` stay
  in the temp dir (pattern: `tests/shiina_cli/test_profiles.py`):
  ```python
  @pytest.fixture
  def profile_env(tmp_path, monkeypatch):
      home = tmp_path / ".shiina"; home.mkdir()
      monkeypatch.setattr(Path, "home", lambda: tmp_path)
      monkeypatch.setenv("SHIINA_HOME", str(home))
      return home
  ```
  Tests that `patch.object(Path, "home", ...)` must ALSO set `SHIINA_HOME` — code reads the
  env var, not `Path.home()/.shiina`.

### Don't fake the host OS

Behaviour that genuinely differs per host must be tested ON that host with `@pytest.mark.linux_only`, `macos_only`, or `windows_only` markers — never by patching `sys.platform`. Use the marker directly (never bare `skipif` or local aliases, which deselect in CI).

### Don't write change-detector tests

Assert contracts and relationships between data (e.g. `assert "gemini" in _PROVIDER_MODELS and len(_PROVIDER_MODELS["gemini"]) >= 1`), never freeze catalogs, counts, or versions that are expected to evolve. If it reads like a snapshot, delete it; if it tests a contract, keep it.

### Never read source code in tests

A test reading `.py`/`.ts` source text tests the syntax shape rather than runtime behavior. Extract logic into pure/DI functions and test runtime inputs and outputs directly.

## Routing Table — working in X → read X/AGENTS.md

| Area | Read | Covers |
|---|---|---|
| `run_agent.py`, `agent/` | `agent/AGENTS.md` | AIAgent + mixins, turn phases, caching integrity, message-flow invariants, compression, model/aux resolution |
| `cli.py`, `shiina_cli/`, `main.py` | `shiina_cli/AGENTS.md` | CLI mixins, `_SLASH_DISPATCH`, slash registry, config system + loaders, skins, `shiina update` pipeline, profiles / multiplex |
| `gateway/` | `gateway/AGENTS.md` | Adapters, two message guards, streaming contract, background notifications, gateway vs desktop lifecycle, token locks, scoped secrets |
| `tools/`, `toolsets.py`, `model_tools.py` | `tools/AGENTS.md` | Adding tools, registry, toolsets, delegation, cross-tool references, backends |
| `plugins/`, `shiina_cli/plugins*.py` | `plugins/AGENTS.md` | Plugin kinds, native compat contract, in-tree policy, Sep-2026 compat window |
| `tui_gateway/`, `ui-tui/` | `tui_gateway/AGENTS.md` | Process model, JSON-RPC transport, key surfaces, slash flow, dev commands |
| `web/`, `shiina_cli/web_routers/` | `web/AGENTS.md` | Dashboard embeds the real TUI; what React may and may not rebuild |
| `apps/desktop/` | `apps/desktop/AGENTS.md`, `apps/desktop/src/AGENTS.md` | Desktop judgment guide; `serve` backend, slash palette curation, Bot Mode canonical chat |
| `skills/`, `optional-skills/`, `agent/curator*.py` | `skills/AGENTS.md` | Frontmatter, HARDLINE authoring standards, curator |
| `cron/`, kanban (`shiina_cli/kanban*.py`, `tools/kanban_tools.py`, `plugins/kanban/`) | `cron/AGENTS.md` | Scheduler invariants, job fields, kanban board/dispatcher |
| `gateway/platforms/` new adapter | `gateway/platforms/ADDING_A_PLATFORM.md` | Step-by-step adapter guide |
| profiles / multiplex / secret scope (any area) | `gateway/AGENTS.md` § Profile scope, `website/docs/user-guide/multi-profile-gateways.md` § What is isolated per profile | which execution points bind scope, what is isolated per profile |

Long-form background lives in `website/docs/developer-guide/` (agent-loop, prompt-assembly,
context-compression-and-caching, gateway-internals, tools-runtime, plugins/, cron-internals,
session-storage, ...). Workflow rules (PR/issue/review/salvage process) live in the
`shiina-agent-dev` skill, not here.
