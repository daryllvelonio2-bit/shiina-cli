#!/usr/bin/env python3
"""
Multi-Agent Orchestrator CLI helper for Shiina Agent.
Manages provider readiness, task decomposition, and concurrent execution.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Constants
SHIINA_HOME = Path(os.getenv("SHIINA_HOME", Path.home() / ".shiina"))
ENV_FILE = SHIINA_HOME / ".env"
QODER_CACHE = SHIINA_HOME / "cache" / "qoder_credentials.json"


def load_shiina_env() -> Dict[str, str]:
    """Parse environment variables from ~/.shiina/.env."""
    env = dict(os.environ)
    if ENV_FILE.exists():
        try:
            for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'").strip('"')
                    if k and k not in env:
                        env[k] = v
        except Exception:
            pass
    return env


def check_agy_status(env: Dict[str, str]) -> Dict[str, Any]:
    """Check Google Antigravity provider readiness."""
    try:
        from agent.google_oauth import get_active_token
        token = get_active_token()
        if token:
            return {
                "status": "ready",
                "auth_type": "Google OAuth (SecretService)",
                "models": ["gemini-3.8-flash-tiered", "gemini-pro-agent", "claude-sonnet-4-6", "claude-opus-4-6-thinking", "gpt-oss-120b-medium"],
                "speed": "Fast (~2.2s TTFT on Flash)",
            }
    except Exception:
        pass

    # Check CLI fallback
    agy_bin = shutil.which("agy")
    if agy_bin:
        return {
            "status": "ready (cli-only)",
            "auth_type": "agy binary",
            "path": agy_bin,
            "models": ["gemini-3.8-flash-tiered", "claude-sonnet-4-6"],
            "speed": "CLI Subprocess",
        }

    return {"status": "unconfigured", "error": "Antigravity OAuth token or agy binary not detected"}


def check_qoder_status(env: Dict[str, str]) -> Dict[str, Any]:
    """Check Qoder provider readiness."""
    pat = env.get("QODER_PAT")
    has_cache = QODER_CACHE.exists()

    user_info = {}
    if has_cache:
        try:
            cached = json.loads(QODER_CACHE.read_text(encoding="utf-8"))
            user_info = cached.get("user", {})
        except Exception:
            pass

    if pat or has_cache:
        return {
            "status": "ready",
            "auth_type": "PAT + COSY JobToken",
            "user": user_info.get("name") or user_info.get("email") or "Authenticated User",
            "subagent_policy": "Strictly locked to qoder-flash (Qwen 3.8 Flash) [FREE TIER]",
            "models": ["qoder-flash (FREE - subagents)", "qoder-deepseek", "qoder-qwen", "qoder-sonus", "qoder-cantus"],
            "speed": "Native Streaming (Reasoning delta enabled)",
        }
    return {"status": "unconfigured", "error": "QODER_PAT missing in ~/.shiina/.env"}


def check_opencode_status(env: Dict[str, str]) -> Dict[str, Any]:
    """Check OpenCode Zen / CLI readiness."""
    zen_key = env.get("OPENCODE_ZEN_API_KEY")
    opencode_bin = shutil.which("opencode") or (Path.home() / ".opencode" / "bin" / "opencode")
    has_bin = Path(opencode_bin).exists() if isinstance(opencode_bin, Path) else (opencode_bin is not None)

    if zen_key or has_bin:
        return {
            "status": "ready",
            "zen_api_key_configured": bool(zen_key),
            "cli_installed": bool(has_bin),
            "cli_path": str(opencode_bin) if has_bin else None,
            "models": ["opencode-zen", "opencode/gpt-5.6-sol", "opencode/claude-sonnet-4"],
            "speed": "Direct API / CLI Runner",
        }
    return {"status": "unconfigured", "error": "Neither OPENCODE_ZEN_API_KEY nor opencode binary found"}


def check_kiro_status(env: Dict[str, str]) -> Dict[str, Any]:
    """Check Kiro CLI readiness."""
    kiro_bin = shutil.which("kiro-cli") or (Path.home() / ".local" / "bin" / "kiro-cli")
    has_bin = Path(kiro_bin).exists() if isinstance(kiro_bin, Path) else (kiro_bin is not None)

    if has_bin:
        whoami = "configured"
        try:
            res = subprocess.run([str(kiro_bin), "whoami"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                whoami = res.stdout.strip()
        except Exception:
            pass

        return {
            "status": "ready",
            "cli_path": str(kiro_bin),
            "account": whoami,
            "models": ["claude-sonnet-4.5", "deepseek-3.2", "claude-haiku-4.5", "auto"],
            "speed": "Autonomous CLI Agent (-a --no-interactive)",
        }
    return {"status": "unconfigured", "error": "kiro-cli binary not found on PATH or ~/.local/bin"}


def check_tokenharbor_status(env: Dict[str, str]) -> Dict[str, Any]:
    """Check TokenHarbor provider readiness and free-tier model access."""
    api_key = env.get("TOKENHARBOR_API_KEY")
    if api_key:
        return {
            "status": "ready",
            "auth_type": "Bearer API Key",
            "subagent_policy": "Strictly locked to deepseek-v4.1-flash:free [FREE TIER]",
            "specialties": [
                "UI Making (Generative UI, component styling, HTML/CSS/React layouts)",
                "Deep Auditing (Codebase security scans, logic flaws, regressions)",
                "Optimizations (Performance tuning, memory leak checks, algorithmic efficiency)",
            ],
            "models": ["deepseek-v4.1-flash:free (FREE - UI, Auditing, Optimizations)", "deepseek-v4-flash:free", "qwen3.8-flash:free"],
            "endpoint": "https://tokenharbor.ai/v1",
            "speed": "Fast Streaming with Native Thinking",
        }
    return {"status": "unconfigured", "error": "TOKENHARBOR_API_KEY missing in ~/.shiina/.env"}


def cmd_status(args: argparse.Namespace) -> int:
    """Print status of all supported providers."""
    env = load_shiina_env()
    report = {
        "Google Antigravity (AGY)": check_agy_status(env),
        "Qoder": check_qoder_status(env),
        "TokenHarbor": check_tokenharbor_status(env),
        "OpenCode Zen": check_opencode_status(env),
        "Kiro CLI": check_kiro_status(env),
    }

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print("=" * 60)
    print(" SHIINA MULTI-AGENT ORCHESTRATOR — PROVIDER STATUS")
    print("=" * 60)
    for provider, data in report.items():
        status = data.get("status", "unknown")
        color_status = f"✓ {status.upper()}" if "ready" in status else f"✗ {status.upper()}"
        print(f"\n[{provider}] -> {color_status}")
        for k, v in data.items():
            if k != "status":
                if isinstance(v, list):
                    print(f"  • {k}: {', '.join(v)}")
                else:
                    print(f"  • {k}: {v}")
    print("\n" + "=" * 60)
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    """Decompose a high-level task into parallel, token-efficient subtasks."""
    task = args.task
    if not task:
        print("Error: --task is required.", file=sys.stderr)
        return 1

    # Intelligent template decomposition with free-tier Qoder constraint
    plan = {
        "task": task,
        "token_conservation_rules": [
            "Pass only file slices, AST signatures, or error traces (never full history).",
            "Cap each subagent at max_iterations: 15.",
            "Subagents return bounded Markdown summary (< 300 words).",
            "Qoder subagents MUST ONLY use qoder-flash (Qwen 3.8 Flash) because it is FREE.",
            "TokenHarbor subagents MUST ONLY use deepseek-v4.1-flash:free (FREE TIER) for UI making, deep auditing, and optimizations.",
        ],
        "stages": [
            {
                "stage": 1,
                "name": "Reconnaissance & File Indexing",
                "execution_mode": "Parallel Fast Scout",
                "subagents": [
                    {
                        "role": "Scout",
                        "provider": "agy-flash",
                        "model": "gemini-3.8-flash-tiered",
                        "goal": f"Find relevant source files, imports, and definitions for: {task}",
                        "context_needed": "Target repository paths or file tree overview.",
                        "estimated_token_cost": "~500 tokens (Flash tier)",
                    },
                    {
                        "role": "Linter / Test Baseline",
                        "provider": "qoder-flash",
                        "model": "qfmodel (Qwen 3.8 Flash - FREE TIER)",
                        "goal": "Verify current test suite and linters to establish baseline pass/fail.",
                        "context_needed": "Test execution command and root dir.",
                        "estimated_token_cost": "0 (Free Tier)",
                    }
                ]
            },
            {
                "stage": 2,
                "name": "Simultaneous Implementation & UI Making",
                "execution_mode": "Parallel Concurrent Specialists",
                "subagents": [
                    {
                        "role": "Fast Component Builder / Scaffolder",
                        "provider": "qoder-flash",
                        "model": "qfmodel (Qwen 3.8 Flash - FREE TIER)",
                        "goal": f"Implement file scaffolding, interfaces, and function skeletons for: {task}",
                        "context_needed": "Target file path and exact signatures identified in Stage 1.",
                        "estimated_token_cost": "0 (Free Tier)",
                    },
                    {
                        "role": "Deep Logic & Architecture Specialist",
                        "provider": "agy-sonnet or kiro-cli",
                        "model": "claude-sonnet-4-6 / claude-sonnet-4.5",
                        "goal": f"Implement complex business logic, algorithms, and comprehensive test suite for: {task}",
                        "context_needed": "File signatures and mock requirements.",
                        "estimated_token_cost": "~1,800 tokens",
                    },
                    {
                        "role": "UI & Frontend Designer / Component Maker",
                        "provider": "tokenharbor",
                        "model": "deepseek-v4.1-flash:free (FREE TIER)",
                        "goal": f"Build responsive UI layouts, components, generative UI widgets, and styling for: {task}",
                        "context_needed": "Component requirements, target frontend files, design/CSS specs.",
                        "estimated_token_cost": "0 (Free Tier)",
                    }
                ]
            },
            {
                "stage": 3,
                "name": "Deep Auditing, Optimizations & Integration Review",
                "execution_mode": "Deterministic Multi-Perspective Audit",
                "subagents": [
                    {
                        "role": "Deep Codebase Auditor",
                        "provider": "tokenharbor",
                        "model": "deepseek-v4.1-flash:free (FREE TIER)",
                        "goal": "Perform deep static code analysis, security vulnerability scanning, edge case detection, and logic verification.",
                        "context_needed": "Unified diff and modified source files from Stage 2.",
                        "estimated_token_cost": "0 (Free Tier)",
                    },
                    {
                        "role": "Codebase Performance & Optimization Specialist",
                        "provider": "tokenharbor",
                        "model": "deepseek-v4.1-flash:free (FREE TIER)",
                        "goal": "Identify and apply runtime optimizations, memory reductions, concurrency improvements, and algorithmic refinements.",
                        "context_needed": "Profiling hotpaths, heavy loops, or modified modules.",
                        "estimated_token_cost": "0 (Free Tier)",
                    },
                    {
                        "role": "Security & Architecture Reviewer",
                        "provider": "gpt-oss or opencode-zen",
                        "model": "gpt-oss-120b-medium",
                        "goal": "Audit generated diffs for regressions, race conditions, and boundary violations.",
                        "context_needed": "Unified diff produced in Stage 2.",
                        "estimated_token_cost": "~1,000 tokens",
                    }
                ]
            }
        ]
    }

    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        print("=" * 65)
        print(f" ORCHESTRATION PLAN: {task}")
        print("=" * 65)
        for stage in plan["stages"]:
            print(f"\n[Stage {stage['stage']}: {stage['name']} ({stage['execution_mode']})]")
            for sa in stage["subagents"]:
                print(f"  ▸ {sa['role']} ({sa['provider']})")
                print(f"    - Model: {sa['model']}")
                print(f"    - Goal:  {sa['goal']}")
                print(f"    - Cost:  {sa['estimated_token_cost']}")
        print("\n" + "=" * 65)
        print("Token Conservation: Strict context pruning & free-tier Qoder locking active.")
    return 0


def _run_worker(cmd: List[str], label: str, workdir: Optional[str] = None) -> Dict[str, Any]:
    """Execute a single external CLI worker and capture output."""
    try:
        proc = subprocess.run(
            cmd,
            cwd=workdir or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        return {
            "label": label,
            "success": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"label": label, "success": False, "returncode": -1, "error": "Execution timed out (180s)"}
    except Exception as exc:
        return {"label": label, "success": False, "returncode": -1, "error": str(exc)}


def cmd_dispatch(args: argparse.Namespace) -> int:
    """Run multiple external CLI workers simultaneously in parallel."""
    worker_specs = args.workers
    if not worker_specs:
        print("Error: Specify at least one worker with --workers, e.g. 'kiro:tests' 'opencode:lint'", file=sys.stderr)
        return 1

    tasks_to_run = []
    for spec in worker_specs:
        if ":" in spec:
            engine, goal = spec.split(":", 1)
        else:
            engine, goal = "auto", spec

        engine = engine.strip().lower()
        goal = goal.strip()

        if engine in ("kiro", "kiro-cli"):
            kiro_bin = shutil.which("kiro-cli") or (Path.home() / ".local" / "bin" / "kiro-cli")
            cmd = [str(kiro_bin), "chat", "--no-interactive", "-a", goal]
            tasks_to_run.append((cmd, f"Kiro ({goal[:20]}...)"))
        elif engine in ("opencode", "zen"):
            oc_bin = shutil.which("opencode") or (Path.home() / ".opencode" / "bin" / "opencode")
            cmd = [str(oc_bin), "run", goal]
            tasks_to_run.append((cmd, f"OpenCode ({goal[:20]}...)"))
        elif engine in ("agy", "antigravity"):
            cmd = ["agy", "-p", goal]
            tasks_to_run.append((cmd, f"Antigravity ({goal[:20]}...)"))
        elif engine in ("tokenharbor", "th"):
            shiina_bin = shutil.which("shiina") or (Path.home() / ".local" / "bin" / "shiina")
            cmd = [str(shiina_bin), "chat", "-q", goal, "--oneshot", "--provider", "tokenharbor", "--model", "deepseek-v4.1-flash:free"]
            tasks_to_run.append((cmd, f"TokenHarbor ({goal[:20]}...)"))
        elif engine in ("qoder", "qoder-flash"):
            shiina_bin = shutil.which("shiina") or (Path.home() / ".local" / "bin" / "shiina")
            cmd = [str(shiina_bin), "chat", "-q", goal, "--oneshot", "--provider", "qoder", "--model", "Qwen3.8-Flash"]
            tasks_to_run.append((cmd, f"Qoder ({goal[:20]}...)"))
        else:
            print(f"Warning: Unknown engine '{engine}'. Skipping.", file=sys.stderr)

    if not tasks_to_run:
        print("No valid worker tasks configured.", file=sys.stderr)
        return 1

    print(f"Dispatching {len(tasks_to_run)} workers simultaneously in parallel...")
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(tasks_to_run), 8)) as executor:
        futures = {executor.submit(_run_worker, cmd, label, args.workdir): label for cmd, label in tasks_to_run}
        for future in concurrent.futures.as_completed(futures):
            label = futures[future]
            try:
                res = future.result()
                results.append(res)
                status_icon = "✓" if res.get("success") else "✗"
                print(f"[{status_icon}] Worker finished: {label}")
            except Exception as exc:
                print(f"[✗] Worker failed: {label}: {exc}")

    print("\n--- Worker Summary ---")
    for r in results:
        print(f"\n==> {r['label']} (exit {r.get('returncode')})")
        out = r.get("stdout") or r.get("error") or r.get("stderr") or "(no output)"
        lines = out.splitlines()
        preview = "\n".join(lines[:10]) + ("\n...[truncated]" if len(lines) > 10 else "")
        print(preview)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-Agent Orchestrator CLI helper")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # status
    p_status = subparsers.add_parser("status", help="Check status of all connected providers")
    p_status.add_argument("--json", action="store_true", help="Output JSON format")
    p_status.set_defaults(func=cmd_status)

    # plan
    p_plan = subparsers.add_parser("plan", help="Generate an optimized multi-agent execution plan")
    p_plan.add_argument("--task", required=True, help="Task description to plan")
    p_plan.add_argument("--json", action="store_true", help="Output JSON format")
    p_plan.set_defaults(func=cmd_plan)

    # dispatch
    p_dispatch = subparsers.add_parser("dispatch", help="Run external workers simultaneously")
    p_dispatch.add_argument("--workers", nargs="+", required=True, help="Workers in format engine:goal")
    p_dispatch.add_argument("--workdir", default=None, help="Working directory for workers")
    p_dispatch.set_defaults(func=cmd_dispatch)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
