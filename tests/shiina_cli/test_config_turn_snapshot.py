"""PLAN-OPT15-17 s1: a turn-scoped readonly config snapshot collapses the per-turn config
reload storm. tool_search/approval readers call ``load_config_readonly()`` ~10 times across one
turn and each falls through to ``_load_config_impl`` (the 0.25 s fast cache does not span a
turn); inside ``turn_config_snapshot()`` they all share the one object loaded at scope entry.
"""
import os
from unittest.mock import patch

from shiina_cli import config as config_mod


def _reset():
    config_mod._LOAD_CONFIG_CACHE.clear()
    config_mod._RAW_CONFIG_CACHE.clear()
    config_mod._FAST_READONLY_CACHE.clear()


def test_turn_snapshot_collapses_readonly_loads(tmp_path):
    with patch.dict(os.environ, {"SHIINA_HOME": str(tmp_path)}):
        (tmp_path / "config.yaml").write_text("model:\n  default: aaaa-route\n", encoding="utf-8")
        real = config_mod._load_config_impl
        calls = []

        def counting(*, want_deepcopy):
            calls.append(want_deepcopy)
            return real(want_deepcopy=want_deepcopy)

        # Baseline: reads spread across a turn (>0.25 s apart) each re-validate. Simulated here by
        # clearing the time-keyed fast cache between reads.
        _reset()
        with patch.object(config_mod, "_load_config_impl", counting):
            for _ in range(10):
                config_mod._FAST_READONLY_CACHE.clear()
                config_mod.load_config_readonly()
        assert len(calls) == 10

        # Same 10 reads inside the scope: one load, shared object.
        calls.clear()
        _reset()
        with patch.object(config_mod, "_load_config_impl", counting):
            with config_mod.turn_config_snapshot():
                reads = []
                for _ in range(10):
                    config_mod._FAST_READONLY_CACHE.clear()
                    reads.append(config_mod.load_config_readonly())
        assert len(calls) == 1
        assert all(r is reads[0] for r in reads)
        # Identity invariant: the snapshot is the same object the load cache holds.
        assert reads[0] is config_mod._LOAD_CONFIG_CACHE[str(config_mod.get_config_path())][8]


def test_save_config_inside_scope_rearms_loader(tmp_path):
    with patch.dict(os.environ, {"SHIINA_HOME": str(tmp_path)}):
        (tmp_path / "config.yaml").write_text("model:\n  default: aaaa-route\n", encoding="utf-8")
        _reset()
        real = config_mod._load_config_impl
        calls = []

        def counting(*, want_deepcopy):
            calls.append(want_deepcopy)
            return real(want_deepcopy=want_deepcopy)

        with patch.object(config_mod, "_load_config_impl", counting):
            with config_mod.turn_config_snapshot() as snapshot:
                assert config_mod.load_config_readonly() is snapshot
                assert len(calls) == 1
                config_mod.save_config({"model": {"default": "bbbb-route"}})
                refreshed = config_mod.load_config_readonly()

        assert len(calls) == 2
        assert refreshed is not snapshot
        assert refreshed["model"]["default"] == "bbbb-route"
