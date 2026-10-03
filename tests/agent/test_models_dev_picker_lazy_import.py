"""Regression for PLAN-10 s3: the model picker must not drag in the heavy static catalog.

``list_provider_models`` only needs ``normalize_provider``. Importing it from
``shiina_cli.provider_identity`` keeps ``shiina_cli.models_catalog_static`` (and the ~2.3 s
``shiina_cli.models`` import that pulls it in) off the first-call path.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_picker_does_not_import_static_catalog():
    """A fresh process must not leave shiina_cli.models_catalog_static in sys.modules."""
    code = (
        "import sys; from agent.models_dev import list_provider_models; "
        "list_provider_models('openrouter', allow_network=False); "
        "assert 'shiina_cli.models_catalog_static' not in sys.modules"
    )
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr


def test_picker_resolves_through_provider_identity(monkeypatch):
    """Seam contract: list_provider_models normalizes via shiina_cli.provider_identity."""
    from agent.models_dev import list_provider_models

    calls = []

    def fake(provider):
        calls.append(provider)
        return "openrouter"

    monkeypatch.setattr("shiina_cli.provider_identity.normalize_provider", fake)
    list_provider_models("google", allow_network=False)
    assert calls == ["google"]


def test_google_alias_matches_gemini():
    from agent.models_dev import list_provider_models

    assert list_provider_models("google", allow_network=False) == list_provider_models(
        "gemini", allow_network=False
    )
