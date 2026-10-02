"""Tests for the process-registry startup prewarm.

``prewarm_process_registry_async()`` pre-imports ``tools.process_registry``
(and runs its module-level delegation recovery) off the user's critical path
so the first status-bar paint is fast instead of blocking ~0.6-1s on the
import chain. Pins the same contracts as ``tests/shiina_cli/test_picker_prewarm.py``:
the warm path runs exactly once per process (no thread leak), and the worker
is delegated to a real import of the registry module.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

from shiina_cli import process_registry_prewarm


def _reset_guard():
    process_registry_prewarm._prewarm_done.clear()


def test_prewarm_imports_process_registry_once():
    """First call spawns a thread that imports tools.process_registry;
    the warm side effect is the completed import (modules in sys.modules)."""
    _reset_guard()
    # Ensure the module is NOT already imported so the warm path is observable.
    saved = sys.modules.pop("tools.process_registry", None)
    try:
        t = process_registry_prewarm.prewarm_process_registry_async()
        assert t is not None, "first call must spawn a prewarm thread"
        t.join(timeout=30)
        assert not t.is_alive(), "prewarm thread should finish promptly"
        assert "tools.process_registry" in sys.modules, (
            "prewarm thread must import tools.process_registry (the warm side effect)"
        )
    finally:
        if saved is not None and "tools.process_registry" not in sys.modules:
            sys.modules["tools.process_registry"] = saved


def test_prewarm_is_once_per_process():
    """Repeated calls never spawn another thread (the once-per-process guard)."""
    _reset_guard()
    t1 = process_registry_prewarm.prewarm_process_registry_async()
    assert t1 is not None
    assert process_registry_prewarm.prewarm_process_registry_async() is None
    assert process_registry_prewarm.prewarm_process_registry_async() is None
    t1.join(timeout=30)


def test_prewarm_import_failure_is_swallowed():
    """A failed import never escapes the worker thread (fire-and-forget contract)."""
    _reset_guard()
    saved = sys.modules.pop("tools.process_registry", None)
    try:
        import builtins

        real_import = builtins.__import__

        def _failing_import(name, *args, **kwargs):
            if name == "tools.process_registry":
                raise ImportError("simulated prewarm failure")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _failing_import):
            t = process_registry_prewarm.prewarm_process_registry_async()
            assert t is not None
            t.join(timeout=30)  # raises only if the worker leaked the exception
            assert not t.is_alive()
    finally:
        if saved is not None and "tools.process_registry" not in sys.modules:
            sys.modules["tools.process_registry"] = saved
