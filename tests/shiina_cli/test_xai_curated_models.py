"""Regression tests for xAI curated + models.dev picker-time merge."""

import json

from unittest.mock import patch

from shiina_cli.models import (
    _MODELS_DEV_PREFERRED,
    _PROVIDER_MODELS,
    provider_model_ids,
)


def test_grok_4_6_is_default_pin():
    models = _PROVIDER_MODELS["xai-oauth"]
    assert models[0] == "grok-4.6"


def test_xai_providers_are_models_dev_preferred():
    assert "xai" in _MODELS_DEV_PREFERRED
    assert "xai-oauth" in _MODELS_DEV_PREFERRED


def test_xai_oauth_picker_merges_models_dev_at_call_time():
    """xai-oauth must not return the import-frozen list; merge at picker time."""
    mdev = ["grok-build-0.1", "grok-new-from-models-dev", "grok-4.6"]
    with patch("agent.models_dev.list_agentic_models", return_value=mdev) as mocked:
        models = provider_model_ids("xai-oauth")

    mocked.assert_called()
    assert models[0] == "grok-4.6"
    assert "grok-new-from-models-dev" in models


def test_xai_api_key_picker_merges_models_dev_when_live_unavailable():
    """Without a live /v1/models hit, xai uses the models.dev preferred path."""
    mdev = ["grok-build-0.1", "grok-new-from-models-dev", "grok-4.6"]
    with (
        patch(
            "shiina_cli.auth.resolve_api_key_provider_credentials",
            side_effect=Exception("no key"),
        ),
        patch("agent.models_dev.list_agentic_models", return_value=mdev) as mocked,
    ):
        models = provider_model_ids("xai")

    mocked.assert_called()
    assert "grok-new-from-models-dev" in models
    assert models[0] == "grok-4.6"


def test_xai_pin_survives_when_top_model_only_in_extras():
    """If models.dev omits grok-4.6, curated extras + finalize still pin it."""
    mdev = ["grok-build-0.1", "grok-new-from-models-dev"]
    with patch("agent.models_dev.list_agentic_models", return_value=mdev):
        models = provider_model_ids("xai-oauth")

    assert models[0] == "grok-4.6"


def _write_cache_and_index(cache: dict) -> None:
    """Write a real models_dev_cache.json + its derived index into the temp SHIINA_HOME."""
    from agent import models_dev

    cache_path = models_dev._get_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache), encoding="utf-8")
    data, sig = models_dev._read_cache_file()
    assert sig is not None and data.get("xai")
    assert models_dev._write_index(data, sig)


def test_xai_curated_prefers_live_index_over_disk_cache():
    """With a provably-fresh index the curated floor never pays the full-cache parse."""
    from agent import models_dev
    from shiina_cli.models_catalog_static import _xai_curated_models, _xai_finalize_catalog

    index_models = {"grok-4.6": {}, "grok-4.5": {}, "grok-3": {}}
    _write_cache_and_index({"xai": {"models": index_models}})
    assert models_dev._load_index_provider("xai") == {"models": index_models}

    with patch(
        "agent.models_dev._load_disk_cache",
        side_effect=Exception("full parse must not run"),
    ):
        models = _xai_curated_models()

    assert models == _xai_finalize_catalog(sorted(index_models))
    assert models[0] == "grok-4.6"


def test_xai_curated_falls_back_to_disk_cache_without_index():
    """No index on disk: the disk cache is still consulted and its data used."""
    from shiina_cli.models_catalog_static import _xai_curated_models

    disk_registry = {"xai": {"models": {"grok-4.6": {}, "grok-disk-only-model": {}}}}
    with patch("agent.models_dev._load_disk_cache", return_value=disk_registry) as mocked:
        models = _xai_curated_models()

    mocked.assert_called()
    assert models[0] == "grok-4.6"
    assert "grok-disk-only-model" in models


def test_xai_curated_static_floor_when_no_index_and_no_cache():
    """No index and the disk cache raises: the static fallback still wins (never worse)."""
    from shiina_cli.models_catalog_static import _XAI_STATIC_FALLBACK, _xai_curated_models, _xai_finalize_catalog

    with patch("agent.models_dev._load_disk_cache", side_effect=Exception("no cache")):
        models = _xai_curated_models()

    assert models == _xai_finalize_catalog(list(_XAI_STATIC_FALLBACK))
