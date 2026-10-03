"""Rate-limit respawn cooldown.

Built-in default: consecutive quota-wall requeues DOUBLE the respawn-guard
cooldown (300s → 600s → 1200s → 1800s cap) instead of holding a flat 300s, so a
multi-hour provider wall costs a handful of respawns rather than one per cooldown.
An explicit ``SHIINA_KANBAN_RATE_LIMIT_COOLDOWN_SECONDS`` override is instead FLAT
at every step — the operator named one exact wait, not a floor that doubles. The
counter is the trailing run of ``rate_limited`` outcomes, so a successful run
resets the backoff, and 0 disables the cooldown (next-tick probe).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from shiina_cli import kanban_db as kb
from shiina_cli import kanban_db_connect as kbc
from shiina_cli import kanban_db_dispatch as kbd


@pytest.fixture
def kanban_home(tmp_path, monkeypatch):
    """Isolated SHIINA_HOME with an empty kanban DB."""
    home = tmp_path / ".shiina"
    home.mkdir()
    monkeypatch.setenv("SHIINA_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    kb.init_db()
    return home


def _seed_run(conn, tid: str, outcome: str, ended_at: int) -> None:
    """Close a fresh run on ``tid`` with ``outcome`` and requeue it to ``ready``.

    Mirrors what the dispatcher does for a dead worker: the run lands a terminal
    ``outcome`` row and the task goes back to the source phase with the quota
    error stamped (cleared for a successful run so ``blocker_auth`` can't fire).
    """
    kb.claim_task(conn, tid)
    task = kb.get_task(conn, tid)
    assert task is not None
    run_id = task.current_run_id
    conn.execute(
        "UPDATE task_runs SET outcome = ?, status = ?, ended_at = ? WHERE id = ?",
        (outcome, outcome, ended_at, run_id),
    )
    conn.execute(
        "UPDATE tasks SET status = 'ready', current_run_id = NULL, claim_lock = NULL, "
        "claim_expires = NULL, worker_pid = NULL, last_failure_error = ? WHERE id = ?",
        (
            None if outcome == "completed"
            else "pid 1 exited rate-limited (quota wall) — requeued",
            tid,
        ),
    )
    conn.commit()


def test_cooldown_sequence_doubles_then_caps(monkeypatch):
    """The pure schedule: 300, 600, 1200, then flat 1800 (the default)."""
    monkeypatch.delenv("SHIINA_KANBAN_RATE_LIMIT_COOLDOWN_SECONDS", raising=False)
    seq = [kbd.rate_limit_cooldown_seconds(step) for step in range(1, 8)]
    assert seq[:4] == [300, 600, 1200, 1800]
    assert all(value == 1800 for value in seq[3:])
    # A programmatic ``base`` keeps the doubling ladder.
    assert [kbd.rate_limit_cooldown_seconds(s, base=300) for s in range(1, 5)] == [
        300, 600, 1200, 1800,
    ]
    # base=0 disables the cooldown entirely (next-tick probe).
    assert kbd.rate_limit_cooldown_seconds(1, base=0) == 0


def test_explicit_env_override_is_flat(monkeypatch):
    """An explicit operator override is the FLAT wait at every step — no doubling.

    The operator set 180 expecting a flat 3 minutes; the override must not climb
    toward the 1800 ceiling.
    """
    monkeypatch.setenv("SHIINA_KANBAN_RATE_LIMIT_COOLDOWN_SECONDS", "180")
    assert [kbd.rate_limit_cooldown_seconds(s) for s in range(1, 6)] == [180] * 5
    # A larger override is still flat (the ceiling governs the default ladder only).
    monkeypatch.setenv("SHIINA_KANBAN_RATE_LIMIT_COOLDOWN_SECONDS", "900")
    assert kbd.rate_limit_cooldown_seconds(5) == 900
    # 0 disables (next-tick probe), through the override path.
    monkeypatch.setenv("SHIINA_KANBAN_RATE_LIMIT_COOLDOWN_SECONDS", "0")
    assert kbd.rate_limit_cooldown_seconds(3) == 0


def test_invalid_override_falls_back_to_default_ladder(monkeypatch):
    """Garbage / negative values are not an override: the default ladder applies."""
    for raw in ("nope", "-5"):
        monkeypatch.setenv("SHIINA_KANBAN_RATE_LIMIT_COOLDOWN_SECONDS", raw)
        assert kbd.rate_limit_cooldown_seconds(1) == 300, raw
        assert kbd.rate_limit_cooldown_seconds(2) == 600, raw


def test_consecutive_rate_limits_escalate_then_cap(kanban_home, monkeypatch):
    """Drive consecutive rate-limited requeues for one task id and assert the
    guard's cooldown follows 300 → 600 → 1200 → 1800 → 1800."""
    import shiina_cli.kanban_db as _kb

    monkeypatch.delenv("SHIINA_KANBAN_RATE_LIMIT_COOLDOWN_SECONDS", raising=False)
    clock = {"now": 5_000_000}
    monkeypatch.setattr(_kb.time, "time", lambda: clock["now"])

    with kbc.connect() as conn:
        tid = kb.create_task(conn, title="rl-backoff", assignee="a")
        expected = [300, 600, 1200, 1800, 1800]
        for step, cooldown in enumerate(expected, start=1):
            ended = 5_000_000 + step * 10_000
            _seed_run(conn, tid, "rate_limited", ended)

            clock["now"] = ended + cooldown - 1
            assert kbd.check_respawn_guard(conn, tid) == "rate_limit_cooldown", step

            clock["now"] = ended + cooldown + 1
            assert kbd.check_respawn_guard(conn, tid) is None, step

            if step > 1 and cooldown > expected[step - 2]:
                # The previous step's shorter cooldown must NOT have allowed the
                # probe: proves the wait actually escalated, not stayed flat.
                clock["now"] = ended + expected[step - 2] + 1
                assert kbd.check_respawn_guard(conn, tid) == "rate_limit_cooldown", step


def test_flat_override_holds_through_guard(kanban_home, monkeypatch):
    """env=180: every consecutive quota wall waits the same 180s — the guard clears
    at 181s on step 5, which the old doubling ladder (1800s) would still hold."""
    import shiina_cli.kanban_db as _kb

    monkeypatch.setenv("SHIINA_KANBAN_RATE_LIMIT_COOLDOWN_SECONDS", "180")
    clock = {"now": 6_000_000}
    monkeypatch.setattr(_kb.time, "time", lambda: clock["now"])

    with kbc.connect() as conn:
        tid = kb.create_task(conn, title="rl-flat", assignee="a")
        for step in range(1, 6):
            ended = 6_000_000 + step * 10_000
            _seed_run(conn, tid, "rate_limited", ended)
            assert kbd._rate_limit_streak(conn, tid) == step

            clock["now"] = ended + 179
            assert kbd.check_respawn_guard(conn, tid) == "rate_limit_cooldown", step

            clock["now"] = ended + 181
            assert kbd.check_respawn_guard(conn, tid) is None, step


def test_zero_override_disables_guard(kanban_home, monkeypatch):
    """env=0 disables the cooldown: a quota-walled task is not held back."""
    import shiina_cli.kanban_db as _kb

    monkeypatch.setenv("SHIINA_KANBAN_RATE_LIMIT_COOLDOWN_SECONDS", "0")
    clock = {"now": 7_000_000}
    monkeypatch.setattr(_kb.time, "time", lambda: clock["now"])

    with kbc.connect() as conn:
        tid = kb.create_task(conn, title="rl-zero", assignee="a")
        _seed_run(conn, tid, "rate_limited", 7_010_000)
        clock["now"] = 7_010_000
        assert kbd.check_respawn_guard(conn, tid) is None


def test_successful_run_resets_backoff(kanban_home, monkeypatch):
    """A completed run ends the streak, so the next quota wall waits 300s again."""
    import shiina_cli.kanban_db as _kb

    monkeypatch.delenv("SHIINA_KANBAN_RATE_LIMIT_COOLDOWN_SECONDS", raising=False)
    clock = {"now": 5_000_000}
    monkeypatch.setattr(_kb.time, "time", lambda: clock["now"])

    with kbc.connect() as conn:
        tid = kb.create_task(conn, title="rl-reset", assignee="a")
        # Escalate to step 2 …
        _seed_run(conn, tid, "rate_limited", 5_010_000)
        _seed_run(conn, tid, "rate_limited", 5_020_000)
        clock["now"] = 5_020_000 + 500
        assert kbd.check_respawn_guard(conn, tid) == "rate_limit_cooldown"
        assert kbd._rate_limit_streak(conn, tid) == 2

        # … a successful run breaks it …
        _seed_run(conn, tid, "completed", 5_030_000)
        clock["now"] = 5_030_000 + 100
        assert kbd._rate_limit_streak(conn, tid) == 0

        # … and the next quota wall is back to the 300s floor.
        _seed_run(conn, tid, "rate_limited", 5_040_000)
        assert kbd._rate_limit_streak(conn, tid) == 1
        clock["now"] = 5_040_000 + 299
        assert kbd.check_respawn_guard(conn, tid) == "rate_limit_cooldown"
        clock["now"] = 5_040_000 + 301
        assert kbd.check_respawn_guard(conn, tid) is None
