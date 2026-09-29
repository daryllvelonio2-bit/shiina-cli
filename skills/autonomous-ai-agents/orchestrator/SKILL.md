---
name: orchestrator
description: "Orchestrate and delegate multi-agent tasks concurrently."
version: 1.0.0
author: Janelle, Shiina Agent
license: MIT
platforms: [linux, macos]
metadata:
  shiina:
    tags: [Orchestration, Multi-Agent, Delegation, Parallel, AGY, Qoder, TokenHarbor, OpenCode-Zen, Token-Efficiency]
    related_skills: [antigravity-cli, opencode, kiro-cli, shiina-agent]
---

# Multi-Agent Orchestrator (`orchestrator`)

The **Orchestrator** skill enables Shiina Agent to coordinate, delegate, and supervise complex multi-agent workflows simultaneously across your connected model providers: **Google Antigravity (`agy`)**, **Qoder**, **TokenHarbor**, **OpenCode Zen**, and **Kiro CLI**.

It enforces **high-concurrency execution** paired with **strict token conservation** so agents work collaboratively without inflating API costs or creating runaway context loops.

---

## 1. Connected Provider Matrix & Specialization

Route work to the right model tier to balance cognitive depth with execution speed and token expenditure:

| Provider | Model Tier | Resolved Alias | Best Suited Tasks | Token Budget & Speed |
|---|---|---|---|---|
| **AGY (Flash)** | Tiered Fast | `agy-flash` (`gemini-3.8-flash-tiered`) | Fast codebase scouting, AST scanning, unit test runs, documentation triage | Ultra-fast (~2.2s TTFT), massive 1M context, lowest token consumption |
| **AGY (Pro)** | Deep Reasoning | `agy-sonnet`, `agy-opus`, `agy-pro`, `gpt-oss` | Architecture design, multi-file refactoring, deep algorithmic reasoning | High cognitive budget; pass distilled snippets, not raw transcripts |
| **Qoder** | Fast Reactive (Free Tier) | `qoder-flash` (`qfmodel` / Qwen 3.8 Flash) | Rapid code edits, linting, baseline test checks, scaffolding | **FREE TIER ONLY** — Subagent Qoder tasks are strictly locked to `qoder-flash` |
| **TokenHarbor** | Free Tier (`:free`) | `tokenharbor-flash`, `th-free` (`deepseek-v4.1-flash:free`) | **UI Making** (Generative UI, components, styling), **Deep Auditing of Codebase** (security, logic edge cases), and **Optimizations** (performance, memory, algorithms) | **FREE TIER ONLY** — Subagent TokenHarbor tasks are strictly locked to `deepseek-v4.1-flash:free` |
| **OpenCode Zen** | Curated Coding Gateway | `opencode-zen` (`https://opencode.ai/zen/v1`) & `opencode run` CLI | Autonomous terminal builds, Git PR workflows, isolated worktrees | Headless execution, zero-retention privacy |
| **Kiro CLI** | Autonomous CLI Agent | `kiro-cli chat --no-interactive -a` | Full-repo autonomous feature implementation & debugging | Auto-approved CLI runs (`claude-sonnet-4.5`, `deepseek-3.2`) |

> [!IMPORTANT]
> **Free-Tier Subagent Policies**:
> - **Qoder**: For all subagent tasks delegated to Qoder, **strictly use `qoder-flash` (Qwen 3.8 Flash)** because it is free.
> - **TokenHarbor**: For all subagent tasks delegated to TokenHarbor, **strictly use `deepseek-v4.1-flash:free`** for UI making, deep auditing of the codebase, and optimizations. Do not route background subagents to paid models.

---

## 2. Token-Conservation Hardlines (Zero Waste)

Multi-agent execution can quickly multiply token consumption if uncontrolled. Always apply these five principles:

1. **Strict Context Pruning**:
   - Never pass full conversation transcripts to subagents.
   - Pass **only** self-contained problem statements, target file paths, relevant function signatures, and exact error stack traces.
2. **Tiered Dispatch (Scout Before Specialist)**:
   - Always run a fast scout (`agy-flash` or `qoder-flash`) first to locate lines and verify repro steps in seconds.
   - Only engage heavy reasoning models (`agy-sonnet`, `agy-opus`, `kiro-cli` Claude Sonnet 4.5) once the search space is narrowed to specific files.
3. **Structured Summary Contracts**:
   - Instruct subagents to return bounded Markdown summaries (under 400 words) answering:
     - Files modified or created.
     - Tests executed and pass/fail status.
     - Key architectural decisions made.
   - Forbid echoing back full unchanged file bodies.
4. **Iteration Ceilings**:
   - Enforce bounded `max_iterations` (10–25 turns) per delegated task. Subagents must terminate rather than spinning in open-ended tool loops.
5. **Prompt Prefix Stability**:
   - Keep system instructions uniform across subtasks to benefit from prompt caching on providers that support prefix caching.

---

## 3. Simultaneous Execution Patterns

### Pattern A: In-Process Concurrent Batch (`delegate_task`)

When tasks can be performed in parallel inside Shiina Agent, dispatch a batch with `delegate_task`. All subagents run simultaneously on background worker threads in isolated sessions:

```json
{
  "tasks": [
    {
      "goal": "Write backend API route for user profile update with validation.",
      "context": "File: server/routes/profile.py. Use Pydantic schema in server/schemas.py.",
      "output_schema": {
        "type": "object",
        "properties": {
          "status": {"type": "string"},
          "modified_files": {"type": "array", "items": {"type": "string"}},
          "summary": {"type": "string"}
        },
        "required": ["status", "summary"]
      }
    },
    {
      "goal": "Implement frontend profile edit form with react-hook-form.",
      "context": "File: client/src/components/ProfileForm.tsx. Matches API schema in server/schemas.py.",
      "output_schema": {
        "type": "object",
        "properties": {
          "status": {"type": "string"},
          "summary": {"type": "string"}
        },
        "required": ["status", "summary"]
      }
    },
    {
      "goal": "Write pytest unit tests for profile update endpoint.",
      "context": "File: tests/test_profile.py. Test valid updates and validation rejections.",
      "output_schema": {
        "type": "object",
        "properties": {
          "tests_passed": {"type": "boolean"},
          "summary": {"type": "string"}
        },
        "required": ["tests_passed", "summary"]
      }
    }
  ]
}
```

### Pattern B: Scout → Specialist → UI Maker → Deep Auditor & Optimizer Pipeline

1. **Scout** (`agy-flash` or `qoder-flash`):
   - Locate relevant symbols and files across the repo in 2–3 seconds (free or low token cost).
2. **Specialist** (`agy-sonnet`, `kiro-cli` Claude Sonnet 4.5, or `qoder-flash`):
   - Implement the core business logic, algorithmic changes, or backend APIs.
3. **UI Maker** (`tokenharbor` / `deepseek-v4.1-flash:free`):
   - Design and build interactive frontend components, generative UI artifacts, responsive layouts, and Tailwind/CSS styling.
4. **Deep Auditor & Optimizer** (`tokenharbor` / `deepseek-v4.1-flash:free`):
   - Rigorously audit the codebase for security flaws, memory leaks, and edge-case regressions, and execute latency/performance optimizations.

### Pattern C: Parallel External CLI Workers

Run independent external agents simultaneously using the `terminal` tool with `background=true`:

```python
# Worker 1: Antigravity CLI for high-level refactoring
terminal(
    command="agy -p 'Refactor database models in db/models.py to use asyncpg' --dangerously-skip-permissions",
    workdir="/path/to/project",
    background=True,
    notify_on_complete=True
)

# Worker 2: Kiro CLI for test generation
terminal(
    command="kiro-cli chat --no-interactive -a 'Generate unit tests for auth endpoints in tests/test_auth.py'",
    workdir="/path/to/project",
    background=True,
    notify_on_complete=True
)

# Worker 3: TokenHarbor for UI Making or Deep Codebase Auditing / Optimizations
terminal(
    command="shiina chat -q 'Audit src/engine for memory leaks and apply async optimizations' --oneshot --provider tokenharbor --model deepseek-v4.1-flash:free",
    workdir="/path/to/project",
    background=True,
    notify_on_complete=True
)

# Worker 4: OpenCode CLI for linting and build checks
terminal(
    command="opencode run 'Run npm run build and fix any TypeScript compiler errors'",
    workdir="/path/to/project",
    background=True,
    notify_on_complete=True
)
```

---

## 4. Helper Script & Status Dashboard

The orchestrator skill includes an executable CLI script located at:
`${SHIINA_SKILL_DIR}/scripts/orchestrator.py`

### Check Provider Readiness & Token Budgets
```bash
python3 ${SHIINA_SKILL_DIR}/scripts/orchestrator.py status
```
Inspects live connectivity, OAuth tokens, and credential status for AGY, Qoder, TokenHarbor, OpenCode Zen, and Kiro CLI.

### Generate a Multi-Agent Execution Plan
```bash
python3 ${SHIINA_SKILL_DIR}/scripts/orchestrator.py plan --task "Add 2FA authentication and unit tests"
```
Automatically outputs a parallelized task breakdown with recommended provider/model pairings and token bounds.

### Dispatch CLI Workers Simultaneously
```bash
python3 ${SHIINA_SKILL_DIR}/scripts/orchestrator.py dispatch --workers "kiro:auth_tests" "th:audit_optimizations" "opencode:typecheck"
```
Spawns background processes in parallel, monitors completion status, and streams aggregated results back.
