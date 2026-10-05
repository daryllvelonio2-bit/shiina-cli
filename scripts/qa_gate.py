#!/usr/bin/env python3
"""QA gate harness: regression suites + benchmarks across git worktrees.

This is the automated regression suite / benchmark harness / merge gate for the
`shiina-opt` optimization workstream. It runs the three project suites
(tsc typecheck, vitest, pytest) against an arbitrary worktree *using that
worktree's own source* (not the main checkout's editable install), records a
machine-readable report, and diffs two reports so a regression is visible at a
glance.

Why a harness instead of three raw commands:

  * A worktree has no `.venv` and no `node_modules`, and the main checkout's
    `.venv` is a *editable install pinned to the main tree*. Running pytest from
    a worktree works only because cwd (`''`) precedes the editable MetaPathFinder
    on `sys.path`; drop the cwd and tests silently exercise main's code. The
    `setenv` step makes that explicit and reproducible.
  * vitest must resolve `@shiina/ink` / `@shiina/shared` to the *worktree's*
    workspace packages, not main's, or a UI change is invisible to its own tests.

Usage:
    scripts/qa_gate.py setenv  --worktree PATH
    scripts/qa_gate.py run     --worktree PATH --label NAME [--js ui-tui|all|none]
                               [--pytest all|none|PATHS] [--jobs N] [--out DIR]
    scripts/qa_gate.py bench   --worktree PATH --label NAME [--out DIR]
    scripts/qa_gate.py compare --base LABEL --cand LABEL [--out DIR]

Reports land in <out>/<label>.json (default out: $SHIINA_QA_REPORTS or
./.qa/reports).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

WORKSPACE_PACKAGES = {  # worktree-local workspace deps that must NOT resolve to main
    "@shiina/ink": "../../packages/shiina-ink",
    "@shiina/shared": "../../../apps/shared",
}


def sh(cmd, cwd=None, timeout=None, env=None, check=False):
    p = subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
        timeout=timeout, env=env,
    )
    if check and p.returncode != 0:
        raise RuntimeError(f"command failed ({p.returncode}): {' '.join(cmd)}\n{p.stdout}\n{p.stderr}")
    return p


def main_repo(worktree: Path) -> Path:
    """Resolve the *main* checkout a linked worktree belongs to (the tree that
    owns .venv and node_modules)."""
    r = sh(["git", "-C", str(worktree), "rev-parse", "--path-format=absolute", "--git-common-dir"])
    if r.returncode != 0:  # older git without --path-format
        r = sh(["git", "-C", str(worktree), "rev-parse", "--git-common-dir"])
        return (worktree / r.stdout.strip()).resolve().parent
    common = Path(r.stdout.strip())
    return common.parent.resolve()


def reports_dir(out: str | None) -> Path:
    d = Path(out) if out else Path(os.environ.get("SHIINA_QA_REPORTS", ".qa/reports"))
    d.mkdir(parents=True, exist_ok=True)
    return d.resolve()


def write_report(out: str | None, label: str, data: dict) -> Path:
    d = reports_dir(out)
    path = d / f"{label}.json"
    data["label"] = label
    data.setdefault("finished_at", time.time())
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_report(out: str | None, label: str) -> dict:
    path = reports_dir(out) / f"{label}.json"
    if not path.exists():
        raise SystemExit(f"no report for label {label!r} at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


# ── environment wiring ────────────────────────────────────────────────────────

def ensure_env(worktree: Path, main: Path) -> list[str]:
    """Make a worktree able to run the suites against *its own* source.

    The main checkout's .venv is an editable install pinned to the main tree, but
    cwd ('') precedes the editable MetaPathFinder in sys.path, so running pytest
    with cwd=worktree imports the worktree. A .venv symlink is what lets
    run_tests.sh find a pytest-bearing interpreter at all.
    """
    wt = Path(worktree).resolve()
    done: list[str] = []
    venv = wt / ".venv"
    if not venv.exists():
        os.symlink(os.path.relpath(main / ".venv", wt), venv)
        done.append(f".venv -> {main / '.venv'}")
    for pkg, rel in WORKSPACE_PACKAGES.items():
        scope = wt / "ui-tui" / "node_modules" / pkg.split("/")[0]
        scope.mkdir(parents=True, exist_ok=True)
        link = scope / pkg.split("/")[1]
        if link.is_symlink():
            if os.readlink(link) == rel:
                continue
            link.unlink()
        elif link.exists():
            continue  # a real dir the worker installed; leave it alone
        os.symlink(rel, link)
        done.append(f"ui-tui/node_modules/{pkg} -> {rel}")
    note = _ensure_ink_dist(wt, main)
    if note:
        done.append(note)
    return done


def _ensure_ink_dist(wt: Path, main: Path) -> str | None:
    """`@shiina/ink`'s index.js re-exports `./dist/entry-exports.js`, which is a
    build artifact and absent from a fresh worktree. Rebuild it (≈0.2 s via
    esbuild) so the vitest suite can import the *worktree's* ink package."""
    pkg = wt / "ui-tui" / "packages" / "shiina-ink"
    src = pkg / "src" / "entry-exports.ts"
    esbuild = main / "node_modules" / ".bin" / "esbuild"
    if not src.exists() or not esbuild.exists():
        return None
    p = sh([str(esbuild), "src/entry-exports.ts", "--bundle", "--platform=node",
            "--format=esm", "--packages=external", "--outdir=dist"], cwd=pkg, timeout=300)
    return "shiina-ink dist rebuilt" if p.returncode == 0 else f"ink build failed: {p.stderr[-200:]}"


# ── suites ────────────────────────────────────────────────────────────────────

def run_typecheck(wt: Path, main: Path) -> dict:
    tsc = main / "node_modules" / "typescript" / "bin" / "tsc"
    if not tsc.exists():
        return {"status": "error", "detail": f"tsc not found at {tsc}"}
    t0 = time.time()
    p = sh(["node", str(tsc), "--noEmit", "-p", str(wt / "ui-tui" / "tsconfig.json")],
           cwd=wt / "ui-tui", timeout=900)
    errors = [ln for ln in (p.stdout + p.stderr).splitlines() if "error TS" in ln]
    return {
        "status": "pass" if p.returncode == 0 else "fail",
        "errors": len(errors),
        "error_sample": errors[:20],
        "seconds": round(time.time() - t0, 1),
    }


def run_vitest(wt: Path, main: Path, package: str, out_file: Path) -> dict:
    pkg_dir = wt / package
    if not (pkg_dir / "package.json").exists():
        return {"status": "error", "detail": f"no package.json in {pkg_dir}"}
    vitest = main / "node_modules" / ".bin" / "vitest"
    if not vitest.exists():
        return {"status": "error", "detail": f"vitest not found at {vitest}"}
    out_file.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    p = sh([str(vitest), "run", "--reporter=json", "--retry=2",
            f"--outputFile={out_file}"],
           cwd=pkg_dir, timeout=1800)
    data = {}
    if out_file.exists():
        try:
            data = json.loads(out_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    failed_files = sorted(
        os.path.relpath(r.get("name", ""), pkg_dir) for r in data.get("testResults", [])
        if r.get("status") == "failed"
    )
    return {
        "status": "pass" if p.returncode == 0 else "fail",
        "total": data.get("numTotalTests"),
        "passed": data.get("numPassedTests"),
        "failed": data.get("numFailedTests"),
        "failed_files": failed_files,
        "seconds": round(time.time() - t0, 1),
        "tail": (p.stdout + p.stderr)[-800:] if p.returncode != 0 and not data else "",
    }


_PY_SUMMARY = re.compile(
    r"Summary:\s*(\d+)\s*files?,\s*(\d+)\s*tests passed,\s*(\d+)\s*failed")


def run_pytest(wt: Path, paths: list[str], jobs: int, timeout: int = 5400) -> dict:
    runner = wt / "scripts" / "run_tests.sh"
    if not runner.exists():
        return {"status": "error", "detail": f"no run_tests.sh in {wt}"}
    cmd = ["bash", str(runner), *paths, "-j", str(jobs)]
    t0 = time.time()
    try:
        p = sh(cmd, cwd=wt, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "seconds": round(time.time() - t0, 1),
                "detail": f"exceeded {timeout}s"}
    text = p.stdout + p.stderr
    m = _PY_SUMMARY.search(text)
    summary = {"files": int(m.group(1)), "passed": int(m.group(2)), "failed": int(m.group(3))} if m else None
    failed_files = sorted(set(re.findall(r"✗\s+(\S+\.py)", text)))
    return {
        "status": "pass" if p.returncode == 0 else "fail",
        "summary": summary,
        "failed_files": failed_files,
        "seconds": round(time.time() - t0, 1),
        "tail": text[-1500:] if p.returncode != 0 else "",
    }


# ── benchmark harness ─────────────────────────────────────────────────────────

def _bench_env(home: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "SHIINA_PROFILE"}
    env["SHIINA_HOME"] = str(home)
    return env


def _stats(runs: list[float]) -> dict:
    if not runs:
        return {"runs": []}
    s = sorted(runs)
    return {"runs": [round(x, 1) for x in runs],
            "min_ms": round(s[0], 1), "median_ms": round(s[len(s) // 2], 1),
            "max_ms": round(s[-1], 1)}


def _wall_ms(cmd: list[str], cwd: Path, env: dict, runs: int, timeout: int = 600) -> dict:
    """Warm-up run first (bytecode compilation of a cold worktree is ~6x the warm
    cost — 2.7 s vs 0.44 s for `--version` — and would otherwise poison the median)."""
    try:
        sh(cmd, cwd=cwd, env=env, timeout=timeout)
        vals = []
        for _ in range(runs):
            t0 = time.perf_counter()
            sh(cmd, cwd=cwd, env=env, timeout=timeout)
            vals.append((time.perf_counter() - t0) * 1000)
    except subprocess.TimeoutExpired:
        return {"error": f"timeout after {timeout}s"}
    return _stats(vals)


_IMPORTTIME = re.compile(r"import time:\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(.+?)\s*$")


def _import_cum_ms(py: str, cwd: Path, env: dict, target: str, runs: int) -> dict:
    """In-process cumulative import cost of `target` (µs → ms) over `runs`
    subprocesses. This is home-shaped (main.py:666-681 reads config.yaml), so the
    caller pins SHIINA_HOME."""
    vals = []
    for _ in range(runs):
        p = sh([py, "-X", "importtime", "-c", f"import {target}"], cwd=cwd, env=env, timeout=600)
        cum = None
        for line in p.stderr.splitlines():
            m = _IMPORTTIME.match(line)
            if m and m.group(3).strip() == target:
                cum = int(m.group(2)) / 1000.0
        if cum is not None:
            vals.append(cum)
    return _stats(vals)


def _pin_homes(base: Path) -> tuple[Path, Path]:
    """Two SHIINA_HOMEs: one without config.yaml, one with. `import
    shiina_cli.main` differs (622 vs 989 ms) purely on this, so both are pinned."""
    none, cfg = base / "home-none", base / "home-cfg"
    none.mkdir(parents=True, exist_ok=True)
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.yaml").write_text(
        "security:\n  redact_secrets: true\nnetwork:\n  force_ipv4: false\n"
        "model:\n  provider: nvidia\n", encoding="utf-8")
    return none, cfg


MODEL_PATH_SCRIPT = (
    "import time;t=time.perf_counter();import shiina_cli.main;m=time.perf_counter();"
    "import shiina_cli.models;mm=time.perf_counter();import shiina_cli.model_setup_flows;"
    "e=time.perf_counter();"
    "print(round((m-t)*1000,1),round((mm-m)*1000,1),round((e-mm)*1000,1),round((e-t)*1000,1))"
)


def _model_path(py: str, cwd: Path, env: dict, runs: int) -> dict:
    """The `/model` cold path, decomposed by in-process elapsed time — main, then
    the models marginal, then the flows marginal, then the total.

    Elapsed deltas, not `-X importtime` cumulative columns: `import shiina_cli.models`
    and `import shiina_cli.main` are independent trees (main pulls neither models
    nor requests), so subtracting their standalone cumulative costs is meaningless."""
    try:
        sh([py, "-c", MODEL_PATH_SCRIPT], cwd=cwd, env=env, timeout=600)
        rows = []
        for _ in range(runs):
            p = sh([py, "-c", MODEL_PATH_SCRIPT], cwd=cwd, env=env, timeout=600)
            parts = p.stdout.split()
            if len(parts) == 4:
                rows.append([float(x) for x in parts])
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    if not rows:
        return {"error": "no output"}
    cols = list(zip(*rows))
    names = ("main_ms", "models_marginal_ms", "flows_marginal_ms", "total_ms")
    return dict(zip(names, (_stats(list(c)) for c in cols)))


def run_bench(wt: Path, main: Path, runs: int, home_base: Path) -> dict:
    """Pinned-startup KPIs for the optimization workstream.

    `-m` + cwd=worktree is required: a console script's sys.path[0] is bin/, so
    bare `shiina` would import the *main* tree through the editable finder."""
    py = str(wt / ".venv" / "bin" / "python")
    none, cfg = _pin_homes(home_base)
    env_none, env_cfg = _bench_env(none), _bench_env(cfg)
    return {
        "preconditions": {"homes": {"none": str(none), "config": str(cfg)},
                          "runs_per_metric": runs, "warmup": True},
        "main_cum_nocfg": _import_cum_ms(py, wt, env_none, "shiina_cli.main", runs),
        "main_cum_config": _import_cum_ms(py, wt, env_cfg, "shiina_cli.main", runs),
        "model_path": _model_path(py, wt, env_cfg, runs),
        "version": _wall_ms([py, "-m", "shiina_cli.main", "--version"], wt, env_cfg, runs),
    }




# ── compare ───────────────────────────────────────────────────────────────────

def compare_reports(base: dict, cand: dict) -> dict:
    out: dict = {"regressions": [], "fixed": [], "suite_deltas": {}}
    for suite in ("typecheck", "vitest_ui_tui", "vitest_web", "vitest_apps_desktop", "pytest"):
        b, c = base.get(suite), cand.get(suite)
        if not isinstance(b, dict) or not isinstance(c, dict):
            continue
        bf, cf = set(b.get("failed_files", [])), set(c.get("failed_files", []))
        new_fail = sorted(cf - bf)
        fixed = sorted(bf - cf)
        delta = {
            "base_status": b.get("status"), "cand_status": c.get("status"),
            "new_failures": new_fail, "fixed": fixed,
        }
        if "failed" in b or "failed" in c:
            delta["failed_base"] = b.get("failed")
            delta["failed_cand"] = c.get("failed")
        if "errors" in b or "errors" in c:
            delta["errors_base"] = b.get("errors")
            delta["errors_cand"] = c.get("errors")
        out["suite_deltas"][suite] = delta
        out["regressions"].extend(f"{suite}: {f}" for f in new_fail)
        out["fixed"].extend(f"{suite}: {f}" for f in fixed)
    return out


# ── git helpers ───────────────────────────────────────────────────────────────

def git_info(wt: Path) -> dict:
    branch = sh(["git", "-C", str(wt), "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    head = sh(["git", "-C", str(wt), "rev-parse", "HEAD"]).stdout.strip()
    dirty = bool(sh(["git", "-C", str(wt), "status", "--porcelain"]).stdout.strip())
    return {"branch": branch, "head": head, "dirty": dirty}


# ── commands ──────────────────────────────────────────────────────────────────

def cmd_setenv(args) -> int:
    wt = Path(args.worktree).resolve()
    actions = ensure_env(wt, main_repo(wt))
    print(f"env ready for {wt}: " + (", ".join(actions) if actions else "no changes"))
    return 0


def cmd_run(args) -> int:
    wt = Path(args.worktree).resolve()
    main = main_repo(wt)
    actions = ensure_env(wt, main)
    report: dict = {"worktree": str(wt), "main_repo": str(main), "env": actions,
                    "started_at": time.time(), **git_info(wt)}
    if args.typecheck:
        report["typecheck"] = run_typecheck(wt, main)
        print(f"typecheck: {report['typecheck'].get('status')} "
              f"({report['typecheck'].get('errors', '?')} errors)")
    pkgs = {"ui-tui": "vitest_ui_tui", "web": "vitest_web", "apps/desktop": "vitest_apps_desktop"}
    js = pkgs if args.js == "all" else ({"ui-tui": "vitest_ui_tui"} if args.js == "ui-tui" else {})
    raw = reports_dir(args.out) / "raw"
    for pkg, key in js.items():
        rep = run_vitest(wt, main, pkg, raw / f"{args.label}-{pkg.replace('/', '_')}.json")
        report[key] = rep
        print(f"vitest {pkg}: {rep.get('status')} "
              f"({rep.get('passed', '?')} passed / {rep.get('failed', '?')} failed)")
    if args.pytest != "none":
        paths = [] if args.pytest == "all" else args.pytest.split(":")
        report["pytest"] = run_pytest(wt, paths, args.jobs, timeout=args.pytest_timeout)
        s = report["pytest"].get("summary") or {}
        print(f"pytest: {report['pytest'].get('status')} "
              f"({s.get('passed', '?')} passed / {s.get('failed', '?')} failed)")
    path = write_report(args.out, args.label, report)
    print(f"report: {path}")
    return 0


def cmd_bench(args) -> int:
    wt = Path(args.worktree).resolve()
    main = main_repo(wt)
    ensure_env(wt, main)
    bench = run_bench(wt, main, args.runs, reports_dir(args.out) / "homes")
    report = {"worktree": str(wt), "started_at": time.time(), **git_info(wt), "bench": bench}
    path = write_report(args.out, args.label, report)
    mp = bench["model_path"]
    print(f"main cum (no config) : {bench['main_cum_nocfg'].get('median_ms')} ms")
    print(f"main cum (config)    : {bench['main_cum_config'].get('median_ms')} ms")
    print(f"models marginal      : {mp.get('models_marginal_ms', {}).get('median_ms')} ms")
    print(f"/model cold path     : {mp.get('total_ms', {}).get('median_ms')} ms")
    print(f"shiina --version     : {bench['version'].get('median_ms')} ms")
    print(f"report: {path}")
    return 0


def cmd_compare(args) -> int:
    diff = compare_reports(read_report(args.out, args.base), read_report(args.out, args.cand))
    print(json.dumps(diff, indent=2))
    write_report(args.out, f"compare-{args.base}-vs-{args.cand}", diff)
    return 1 if diff["regressions"] else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("setenv", help="wire a worktree to run the suites")
    s.add_argument("--worktree", required=True)
    s.set_defaults(func=cmd_setenv)

    r = sub.add_parser("run", help="run typecheck + vitest + pytest, write a report")
    r.add_argument("--worktree", required=True)
    r.add_argument("--label", required=True)
    r.add_argument("--js", choices=["ui-tui", "all", "none"], default="ui-tui")
    r.add_argument("--pytest", default="all",
                   help="'all', 'none', or colon-separated paths under the worktree")
    r.add_argument("--jobs", type=int, default=8)
    r.add_argument("--pytest-timeout", type=int, default=5400)
    r.add_argument("--typecheck", dest="typecheck", action="store_true", default=True)
    r.add_argument("--no-typecheck", dest="typecheck", action="store_false")
    r.add_argument("--out", default=None)
    r.set_defaults(func=cmd_run)

    b = sub.add_parser("bench", help="measure CLI startup KPIs")
    b.add_argument("--worktree", required=True)
    b.add_argument("--label", required=True)
    b.add_argument("--runs", type=int, default=3)
    b.add_argument("--out", default=None)
    b.set_defaults(func=cmd_bench)

    c = sub.add_parser("compare", help="diff two reports; exit 1 on regression")
    c.add_argument("--base", required=True)
    c.add_argument("--cand", required=True)
    c.add_argument("--out", default=None)
    c.set_defaults(func=cmd_compare)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

