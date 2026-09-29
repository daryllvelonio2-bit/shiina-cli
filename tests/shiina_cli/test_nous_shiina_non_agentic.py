"""Tests for the Nous-Shiina-3/4 non-agentic warning detector.

Prior to this check, the warning fired on any model whose name contained
``"shiina"`` anywhere (case-insensitive). That false-positived on unrelated
local Modelfiles such as ``shiina-brain:qwen3-14b-ctx16k`` — a tool-capable
Qwen3 wrapper that happens to live under the "shiina" tag namespace.

``is_nous_shiina_non_agentic`` should only match the actual Nous Research
Shiina-3 / Shiina-4 chat family.
"""

from __future__ import annotations

import pytest

from shiina_cli.model_switch import (
    _SHIINA_MODEL_WARNING,
    _check_shiina_model_warning,
    is_nous_shiina_non_agentic,
)


@pytest.mark.parametrize(
    "model_name",
    [
        "NousResearch/Shiina-3-Llama-3.1-70B",
        "NousResearch/Shiina-3-Llama-3.1-405B",
        "shiina-3",
        "Shiina-3",
        "shiina-4",
        "shiina-4-405b",
        "shiina_4_70b",
        "openrouter/shiina3:70b",
        "openrouter/nousresearch/shiina-4-405b",
        "NousResearch/Shiina3",
        "shiina-3.1",
    ],
)
def test_matches_real_nous_shiina_chat_models(model_name: str) -> None:
    assert is_nous_shiina_non_agentic(model_name), (
        f"expected {model_name!r} to be flagged as Nous Shiina 3/4"
    )
    assert _check_shiina_model_warning(model_name) == _SHIINA_MODEL_WARNING


