"""Contract tests for the lazily-resolved provider catalog.

``_PROVIDER_MODELS``'s xAI / openai-codex entries are built from the models.dev disk cache and the
Codex model metadata. Building them at module import pulled ``agent.models_dev`` (→ ``requests``)
and ``agent.model_metadata`` (→ ``shiina_cli.config``) into every `shiina` start, including the ones
that never open the ``/model`` picker, in a module whose docstring says "data only — no network".
They now resolve on first access; the values are unchanged.
"""

import subprocess
import sys
import textwrap


def test_importing_models_does_not_import_the_network_stack():
    code = textwrap.dedent(
        """
        import sys
        import shiina_cli.models  # noqa: F401
        loaded = [m for m in ("agent.models_dev", "agent.model_metadata", "requests")
                  if m in sys.modules]
        assert not loaded, f"eagerly imported: {loaded}"
        """
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr


def test_provider_catalog_materializes_the_derived_entries():
    from shiina_cli import models, models_catalog_static

    catalog = models._PROVIDER_MODELS  # PEP 562: resolves on first access
    assert catalog is models_catalog_static._PROVIDER_MODELS
    assert models.provider_models() is catalog
    # The static entries resolved together with the disk-derived ones.
    assert catalog["nous"] and catalog["anthropic"]
    assert catalog["xai"] == catalog["xai-oauth"]
    assert catalog["openai-codex"]
    assert catalog["xai-oauth"][0] == "grok-4.6"


def test_module_level_override_still_intercepts_the_catalog(monkeypatch):
    """``monkeypatch.setattr(models, "_PROVIDER_MODELS", ...)`` keeps working, as it did when the
    name was bound at import (tests and callers rely on that seam)."""
    from shiina_cli import models

    monkeypatch.setattr(models, "_PROVIDER_MODELS", {"zai": ["only-static"]})
    assert models.provider_models() == {"zai": ["only-static"]}
    assert models.get_default_model_for_provider("zai") == "only-static"
    assert models.get_default_model_for_provider("anthropic") == ""
