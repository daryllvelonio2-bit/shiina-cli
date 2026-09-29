"""Tests for free-usage rotation presets (/shiina-setup, /shiina-free-<name>, /shiina-free)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from shiina_cli.free_presets import (
    DEFAULT_ROTATION_MODE,
    ROTATION_MODES,
    apply_free_preset,
    delete_preset,
    get_preset,
    handle_free_management,
    list_presets,
    load_presets,
    normalize_preset_name,
    run_setup_wizard,
    save_preset,
)
from agent.credential_pool import (
    STRATEGY_FILL_FIRST,
    STRATEGY_LEAST_USED,
    STRATEGY_RANDOM,
    STRATEGY_ROUND_ROBIN,
    load_pool,
)


@pytest.fixture(autouse=True)
def isolated_shiina_home(tmp_path, monkeypatch):
    """Point Shiina home and config to a clean isolated directory."""
    home_dir = tmp_path / ".shiina"
    home_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SHIINA_HOME", str(home_dir))
    from shiina_constants import reset_shiina_home_override, set_shiina_home_override

    token = set_shiina_home_override(home_dir)
    yield home_dir
    reset_shiina_home_override(token)


class DummyAgent:
    """Mock agent with switch_model and fallback chain attributes."""

    def __init__(self, model="init-model", provider="init-provider"):
        self.model = model
        self.provider = provider
        self.api_key = "init-key"
        self.base_url = "https://init.example.com"
        self.api_mode = "chat_completions"
        self._fallback_chain = []
        self._fallback_index = 0
        self._fallback_model = None
        self._credential_pool = None
        self._active_free_preset = None

    def switch_model(self, new_model, new_provider, api_key="", base_url="", api_mode=""):
        self.model = new_model
        self.provider = new_provider
        self.api_key = api_key
        self.base_url = base_url
        self.api_mode = api_mode
        # Simulates real switch_model pruning old primary
        self._fallback_chain = []


class DummyCLI:
    """Mock CLI session."""

    def __init__(self):
        self.model = "init-model"
        self.provider = "init-provider"
        self.requested_provider = "init-provider"
        self.api_key = ""
        self.base_url = ""
        self.api_mode = ""
        self._fallback_model = None
        self._active_free_preset = None
        self.agent = DummyAgent()


def test_normalize_preset_name():
    assert normalize_preset_name("deepseek") == "deepseek"
    assert normalize_preset_name("/shiina-free-deepseek") == "deepseek"
    assert normalize_preset_name("shiina-free-deepseek") == "deepseek"
    assert normalize_preset_name("shiina-free deepseek") == "deepseek"
    assert normalize_preset_name("  Free Tier v1  ") == "free-tier-v1"
    assert normalize_preset_name("///shiina-free-my_test-1.") == "my_test-1"


def test_save_load_list_delete_presets(isolated_shiina_home):
    providers = [
        {"provider": "nvidia", "model": "deepseek-ai/deepseek-r1"},
        {"provider": "openrouter", "model": "deepseek/deepseek-r1:free"},
    ]
    saved = save_preset(
        name="deepseek",
        providers=providers,
        rotation_mode=STRATEGY_ROUND_ROBIN,
    )
    assert saved["name"] == "deepseek"
    assert saved["rotation_mode"] == STRATEGY_ROUND_ROBIN
    assert len(saved["providers"]) == 2

    # Load and retrieve
    loaded = get_preset("deepseek")
    assert loaded is not None
    assert loaded["name"] == "deepseek"
    assert loaded["providers"] == providers

    # Also prefix tolerant
    loaded_prefix = get_preset("/shiina-free-deepseek")
    assert loaded_prefix is not None
    assert loaded_prefix["name"] == "deepseek"

    # List
    all_presets = list_presets()
    assert len(all_presets) == 1
    assert all_presets[0]["name"] == "deepseek"

    # Delete
    assert delete_preset("deepseek") is True
    assert get_preset("deepseek") is None
    assert list_presets() == []
    assert delete_preset("deepseek") is False


def test_preset_validation():
    with pytest.raises(ValueError, match="Preset name cannot be empty"):
        save_preset(name="", providers=[{"provider": "p", "model": "m"}])

    with pytest.raises(ValueError, match="at least one provider"):
        save_preset(name="test", providers=[])

    # Unsupported rotation mode defaults safely
    p = save_preset(
        name="test",
        providers=[{"provider": "openrouter", "model": "deepseek:free"}],
        rotation_mode="invalid_strategy",
    )
    assert p["rotation_mode"] == DEFAULT_ROTATION_MODE


def test_apply_free_preset(monkeypatch, isolated_shiina_home):
    providers = [
        {"provider": "nvidia", "model": "deepseek-ai/deepseek-r1"},
        {"provider": "openrouter", "model": "deepseek/deepseek-r1:free"},
        {"provider": "cline", "model": "deepseek/deepseek-chat"},
    ]
    save_preset(
        name="deepseek",
        providers=providers,
        rotation_mode=STRATEGY_ROUND_ROBIN,
    )

    cli = DummyCLI()
    ok, summary = apply_free_preset(cli, "deepseek")
    assert ok is True
    assert "Applied free rotation preset: deepseek" in summary
    assert "Active primary: nvidia" in summary
    assert "openrouter:deepseek/deepseek-r1:free" in summary
    assert "cline:deepseek/deepseek-chat" in summary

    # Primary active on CLI and Agent
    assert cli.provider == "nvidia"
    assert cli.model == "deepseek-ai/deepseek-r1"
    assert cli.agent.provider == "nvidia"
    assert cli.agent.model == "deepseek-ai/deepseek-r1"

    # Fallback chain configured on Agent
    assert len(cli.agent._fallback_chain) == 2
    assert cli.agent._fallback_chain[0] == {
        "provider": "openrouter",
        "model": "deepseek/deepseek-r1:free",
    }
    assert cli.agent._fallback_chain[1] == {
        "provider": "cline",
        "model": "deepseek/deepseek-chat",
    }
    assert cli.agent._fallback_index == 0

    # Config updated with rotation mode for providers
    from shiina_cli.config import load_config
    cfg = load_config()
    strategies = cfg.get("credential_pool_strategies", {})
    assert strategies.get("nvidia") == STRATEGY_ROUND_ROBIN
    assert strategies.get("openrouter") == STRATEGY_ROUND_ROBIN
    assert strategies.get("cline") == STRATEGY_ROUND_ROBIN


def test_shiina_free_management_commands(isolated_shiina_home):
    cli = DummyCLI()
    outputs = []

    def mock_print(msg):
        outputs.append(msg)

    # 1. Empty list
    handle_free_management(cli, "/shiina-free", out_print=mock_print)
    assert any("No free-usage rotation presets found" in o for o in outputs)
    outputs.clear()

    # 2. Add preset and list
    save_preset(
        name="free-mix",
        providers=[
            {"provider": "nvidia", "model": "meta/llama-3"},
            {"provider": "openrouter", "model": "meta/llama-3:free"},
        ],
        rotation_mode=STRATEGY_LEAST_USED,
    )
    handle_free_management(cli, "/shiina-free list", out_print=mock_print)
    assert any("free-mix" in o for o in outputs)
    assert any("mode: least_used" in o for o in outputs)
    outputs.clear()

    # 3. Show
    handle_free_management(cli, "/shiina-free show free-mix", out_print=mock_print)
    assert any("Preset Details: free-mix" in o for o in outputs)
    assert any("nvidia" in o for o in outputs)
    outputs.clear()

    # 4. Direct apply via /shiina-free <name>
    handle_free_management(cli, "/shiina-free free-mix", out_print=mock_print)
    assert cli.provider == "nvidia"
    assert cli.model == "meta/llama-3"
    assert any("Applied free rotation preset: free-mix" in o for o in outputs)
    outputs.clear()

    # 5. Direct apply via /shiina-free-<name>
    handle_free_management(cli, "/shiina-free-free-mix", out_print=mock_print)
    assert cli.provider == "nvidia"
    assert any("Applied free rotation preset: free-mix" in o for o in outputs)
    outputs.clear()

    # 6. Delete
    handle_free_management(cli, "/shiina-free delete free-mix", out_print=mock_print)
    assert any("Deleted preset 'free-mix'" in o for o in outputs)
    assert get_preset("free-mix") is None


def test_setup_wizard_scripted(monkeypatch, isolated_shiina_home):
    mock_usable = [
        {"slug": "nvidia", "name": "NVIDIA NIM", "models": ["deepseek-ai/deepseek-r1", "meta/llama-3"], "key_count": 2},
        {"slug": "openrouter", "name": "OpenRouter", "models": ["deepseek/deepseek-r1:free"], "key_count": 4},
        {"slug": "cline", "name": "Cline", "models": ["deepseek/deepseek-chat"], "key_count": 3},
    ]
    monkeypatch.setattr(
        "shiina_cli.free_presets.get_usable_providers_for_setup",
        lambda: mock_usable,
    )

    cli = DummyCLI()
    outputs = []

    def mock_print(msg):
        outputs.append(msg)

    # Scripted input sequence:
    # 1. Preset name: deepseek-free
    # 2. Providers: 1, 2
    # 3. Model for nvidia: 1 (deepseek-ai/deepseek-r1)
    # 4. Model for openrouter: 1 (deepseek/deepseek-r1:free)
    # 5. Rotation mode: 2 (round_robin)
    scripted_inputs = [
        "deepseek-free",
        "1, 2",
        "1",
        "1",
        "2",
    ]
    input_idx = [0]

    def mock_reader(_prompt):
        val = scripted_inputs[input_idx[0]]
        input_idx[0] += 1
        return val

    ok = run_setup_wizard(cli, reader=mock_reader, out_print=mock_print)
    assert ok is True

    preset = get_preset("deepseek-free")
    assert preset is not None
    assert preset["name"] == "deepseek-free"
    assert preset["rotation_mode"] == STRATEGY_ROUND_ROBIN
    assert len(preset["providers"]) == 2
    assert preset["providers"][0] == {"provider": "nvidia", "model": "deepseek-ai/deepseek-r1"}
    assert preset["providers"][1] == {"provider": "openrouter", "model": "deepseek/deepseek-r1:free"}
    assert any("/shiina-free-deepseek-free" in o for o in outputs)


def test_setup_wizard_via_flags(monkeypatch, isolated_shiina_home):
    mock_usable = [
        {"slug": "nvidia", "name": "NVIDIA NIM", "models": ["deepseek-ai/deepseek-r1"], "key_count": 2},
        {"slug": "openrouter", "name": "OpenRouter", "models": ["deepseek/deepseek-r1:free"], "key_count": 4},
    ]
    monkeypatch.setattr(
        "shiina_cli.free_presets.get_usable_providers_for_setup",
        lambda: mock_usable,
    )

    cli = DummyCLI()
    ok = run_setup_wizard(
        cli,
        args_str="my-setup --providers nvidia:deepseek-ai/deepseek-r1,openrouter:deepseek/deepseek-r1:free --mode least_used",
        out_print=lambda _m: None,
    )
    assert ok is True

    preset = get_preset("my-setup")
    assert preset is not None
    assert preset["name"] == "my-setup"
    assert preset["rotation_mode"] == STRATEGY_LEAST_USED
    assert len(preset["providers"]) == 2


def test_slash_completer_yields_presets(isolated_shiina_home):
    save_preset(
        name="alpha-preset",
        providers=[{"provider": "nvidia", "model": "meta/llama-3"}],
    )
    save_preset(
        name="beta-preset",
        providers=[{"provider": "openrouter", "model": "deepseek:free"}],
    )

    from prompt_toolkit.document import Document
    from shiina_cli.commands_completion import SlashCommandCompleter

    completer = SlashCommandCompleter()
    doc = Document("/shiina-free-a", cursor_position=len("/shiina-free-a"))
    completions = list(completer.get_completions(doc, None))

    matches = [c.text for c in completions if "alpha" in c.text]
    assert len(matches) >= 1
    assert "shiina-free-alpha-preset" in matches[0]


def test_setup_wizard_tui_mode_uses_clarify_callback_and_never_calls_raw_input(monkeypatch, isolated_shiina_home):
    """Regression test: when cli._app is active, setup wizard MUST route through
    _clarify_callback and NEVER invoke builtins.input (which locks up terminal input)."""
    import builtins
    from unittest.mock import patch

    mock_usable = [
        {"slug": "nvidia", "name": "NVIDIA NIM", "models": ["deepseek-ai/deepseek-r1"], "key_count": 2},
        {"slug": "openrouter", "name": "OpenRouter", "models": ["deepseek/deepseek-r1:free"], "key_count": 4},
    ]
    monkeypatch.setattr(
        "shiina_cli.free_presets.get_usable_providers_for_setup",
        lambda: mock_usable,
    )

    clarify_calls = []

    def mock_clarify(question, choices=None, multi_select=False, questions=None):
        clarify_calls.append({"question": question, "choices": choices, "multi_select": multi_select})
        # Step a: preset name
        if choices == []:
            return "tui-preset"
        # Step b: providers
        if multi_select:
            return "NVIDIA NIM (nvidia) — 2 keys, OpenRouter (openrouter) — 4 keys"
        # Step c: model
        if choices and "deepseek-ai/deepseek-r1" in choices:
            return "deepseek-ai/deepseek-r1"
        if choices and "deepseek/deepseek-r1:free" in choices:
            return "deepseek/deepseek-r1:free"
        # Step d: mode
        return "round_robin — Cycle through keys evenly"

    cli = DummyCLI()
    cli._app = MagicMock()  # Simulates active prompt_toolkit Application
    cli._clarify_callback = mock_clarify

    def _boom(*a, **k):
        raise AssertionError("builtins.input() was called while cli._app is active! Terminal lockup regression.")

    with patch.object(builtins, "input", _boom):
        ok = run_setup_wizard(cli, out_print=lambda _m: None)

    assert ok is True
    assert len(clarify_calls) >= 4  # name, providers, model1, model2, mode

    preset = get_preset("tui-preset")
    assert preset is not None
    assert preset["name"] == "tui-preset"
    assert preset["rotation_mode"] == STRATEGY_ROUND_ROBIN
    assert len(preset["providers"]) == 2
    assert preset["providers"][0]["provider"] == "nvidia"
    assert preset["providers"][1]["provider"] == "openrouter"


def test_setup_wizard_tui_mode_cancelled_exits_cleanly(monkeypatch, isolated_shiina_home):
    """When user cancels or clarify times out in TUI mode, wizard must cleanly return False."""
    import builtins
    from unittest.mock import patch

    cli = DummyCLI()
    cli._app = MagicMock()
    cli._clarify_callback = lambda *a, **k: "The user cancelled. Use your best judgement to proceed."

    def _boom(*a, **k):
        raise AssertionError("builtins.input() called on cancel")

    with patch.object(builtins, "input", _boom):
        ok = run_setup_wizard(cli, out_print=lambda _m: None)

    assert ok is False
    assert get_preset("tui-preset") is None


def test_setup_wizard_app_without_clarify_never_calls_raw_input(monkeypatch, isolated_shiina_home):
    """When cli._app exists but _clarify_callback is not present, raw input() must NOT be called."""
    import builtins
    from unittest.mock import patch

    cli = DummyCLI()
    cli._app = MagicMock()
    # No _clarify_callback attribute

    def _boom(*a, **k):
        raise AssertionError("builtins.input() called when app active without clarify callback")

    with patch.object(builtins, "input", _boom):
        ok = run_setup_wizard(cli, out_print=lambda _m: None)

    assert ok is False


def test_setup_wizard_shows_all_available_models(monkeypatch, isolated_shiina_home):
    """Verify that all available models for a provider are offered, not capped to 8 or 9."""
    models_list = [f"custom-model-{i}" for i in range(1, 26)]
    # Also add a free model to test free-model prioritization
    models_list.append("special/free-model:free")

    mock_usable = [
        {"slug": "testprov", "name": "Test Provider", "models": models_list, "key_count": 3},
    ]
    monkeypatch.setattr(
        "shiina_cli.free_presets.get_usable_providers_for_setup",
        lambda: mock_usable,
    )

    offered_choices = []

    def mock_clarify(question, choices=None, multi_select=False, initial_selected=0, preselected=None):
        if "select model" in question.lower():
            offered_choices.extend(choices or [])
            return "special/free-model:free"
        if choices == []:
            return "all-models-preset"
        if multi_select:
            return "Test Provider (testprov) — 3 keys"
        return "round_robin"

    cli = DummyCLI()
    cli._app = MagicMock()
    cli._clarify_callback = mock_clarify

    ok = run_setup_wizard(cli, out_print=lambda _m: None)
    assert ok is True
    # All 26 models must be present in choices
    assert len(offered_choices) == 26
    for m in models_list:
        assert m in offered_choices
    # :free model should be prioritized near the top
    assert offered_choices[0] == "special/free-model:free"


def test_setup_wizard_duplicate_preset_detection(monkeypatch, isolated_shiina_home):
    """When a preset already exists, wizard must ask whether to edit, replace, rename, or cancel."""
    save_preset(
        name="existing-preset",
        providers=[{"provider": "nvidia", "model": "deepseek-ai/deepseek-r1"}],
        rotation_mode=STRATEGY_ROUND_ROBIN,
    )

    mock_usable = [
        {"slug": "nvidia", "name": "NVIDIA NIM", "models": ["deepseek-ai/deepseek-r1", "meta/llama-3"], "key_count": 2},
        {"slug": "openrouter", "name": "OpenRouter", "models": ["deepseek/deepseek-r1:free"], "key_count": 4},
    ]
    monkeypatch.setattr(
        "shiina_cli.free_presets.get_usable_providers_for_setup",
        lambda: mock_usable,
    )

    # 1. User chooses Cancel on duplicate
    cli = DummyCLI()
    cli._app = MagicMock()
    interactions = [
        "existing-preset",  # name
        "Cancel",           # duplicate action
    ]
    it_idx = [0]

    def mock_clarify_cancel(*a, **k):
        val = interactions[it_idx[0]]
        it_idx[0] += 1
        return val

    cli._clarify_callback = mock_clarify_cancel
    ok = run_setup_wizard(cli, out_print=lambda _m: None)
    assert ok is False

    # 2. User chooses Edit existing configuration
    it_idx[0] = 0
    interactions = [
        "existing-preset",               # name
        "Edit existing configuration",   # duplicate action
        "NVIDIA NIM (nvidia) — 2 keys, OpenRouter (openrouter) — 4 keys",  # providers
        "meta/llama-3",                  # nvidia model
        "deepseek/deepseek-r1:free",     # openrouter model
        "least_used",                    # mode
    ]
    cli._clarify_callback = mock_clarify_cancel
    ok = run_setup_wizard(cli, out_print=lambda _m: None)
    assert ok is True
    edited = get_preset("existing-preset")
    assert edited is not None
    assert edited["rotation_mode"] == STRATEGY_LEAST_USED
    assert len(edited["providers"]) == 2
    assert edited["providers"][0]["model"] == "meta/llama-3"


def test_setup_wizard_cancelled_at_model_or_mode_stage(monkeypatch, isolated_shiina_home):
    """Esc / Ctrl+C cancellation during model or mode stage must stop immediately."""
    mock_usable = [
        {"slug": "nvidia", "name": "NVIDIA NIM", "models": ["deepseek-ai/deepseek-r1"], "key_count": 2},
    ]
    monkeypatch.setattr(
        "shiina_cli.free_presets.get_usable_providers_for_setup",
        lambda: mock_usable,
    )

    cli = DummyCLI()
    cli._app = MagicMock()

    # Cancel at model selection step
    def mock_clarify_cancel_at_model(question, choices=None, **k):
        if "model" in question.lower():
            return "The user cancelled. Use your best judgement to proceed."
        if choices == []:
            return "cancel-preset"
        return "1"

    cli._clarify_callback = mock_clarify_cancel_at_model
    ok = run_setup_wizard(cli, out_print=lambda _m: None)
    assert ok is False
    assert get_preset("cancel-preset") is None


def test_tui_handle_escape_modal_cancels_clarify():
    """Verify that _tui_handle_escape_modal cancels _clarify_state in prompt_toolkit."""
    import queue
    from cli import ShiinaCLI

    cli = ShiinaCLI.__new__(ShiinaCLI)
    q = queue.Queue()
    cli._clarify_state = {"response_queue": q}
    cli._clarify_freetext = True
    cli._clarify_multi_base = ["dummy"]
    cli._secret_state = None
    cli._sudo_state = None
    cli._slash_confirm_state = None

    event = MagicMock()
    cli._tui_handle_escape_modal(event)

    assert cli._clarify_state is None
    assert cli._clarify_freetext is False
    assert cli._clarify_multi_base is None
    res = q.get_nowait()
    assert "user cancelled" in res.lower()


def test_setup_wizard_providers_removes_other_and_enables_search(monkeypatch, isolated_shiina_home):
    """Verify that provider selection in setup wizard passes allow_other=False and searchable=True,
    and model selection passes allow_other=True and searchable=True."""
    mock_usable = [
        {"slug": "testprov", "name": "Test Provider", "models": ["model-a", "model-b"], "key_count": 1},
    ]
    monkeypatch.setattr(
        "shiina_cli.free_presets.get_usable_providers_for_setup",
        lambda: mock_usable,
    )

    calls = []

    def mock_clarify(question, choices=None, multi_select=False, initial_selected=0,
                     preselected=None, allow_other=True, searchable=False):
        calls.append({
            "question": question,
            "choices": choices,
            "multi_select": multi_select,
            "allow_other": allow_other,
            "searchable": searchable,
        })
        if choices == []:
            return "search-preset"
        if multi_select:
            return "Test Provider (testprov) — 1 key"
        if "model" in question.lower():
            return "model-a"
        return "round_robin"

    cli = DummyCLI()
    cli._app = MagicMock()
    cli._clarify_callback = mock_clarify

    ok = run_setup_wizard(cli, out_print=lambda _m: None)
    assert ok is True

    # Find the provider call
    prov_calls = [c for c in calls if c.get("multi_select")]
    assert len(prov_calls) == 1
    assert prov_calls[0]["allow_other"] is False
    assert prov_calls[0]["searchable"] is True

    # Find the model call
    model_calls = [c for c in calls if "model" in c.get("question", "").lower()]
    assert len(model_calls) == 1
    assert model_calls[0]["allow_other"] is True
    assert model_calls[0]["searchable"] is True


def test_clarify_display_fragments_allow_other_false():
    """Verify that allow_other=False omits the 'Other' item from clarify display fragments."""
    from cli import ShiinaCLI

    cli = ShiinaCLI.__new__(ShiinaCLI)
    cli._clarify_freetext = False
    cli._clarify_deadline = None
    cli._app = None

    choices = ["Option 1", "Option 2"]

    # With allow_other=False:
    cli._clarify_state = {
        "question": "Choose a provider:",
        "choices": choices,
        "selected": 0,
        "multi_select": False,
        "selected_indices": set(),
        "allow_other": False,
        "filter": "",
    }
    frags_no_other = cli._get_clarify_display_fragments()
    text_no_other = "".join(part[1] for part in frags_no_other)
    assert "Option 1" in text_no_other
    assert "Option 2" in text_no_other
    assert "Other" not in text_no_other

    # With allow_other=True:
    cli._clarify_state["allow_other"] = True
    frags_with_other = cli._get_clarify_display_fragments()
    text_with_other = "".join(part[1] for part in frags_with_other)
    assert "Other" in text_with_other


def test_clarify_display_fragments_search_filtering():
    """Verify that typing a query filters the choices in real-time."""
    from cli import ShiinaCLI

    cli = ShiinaCLI.__new__(ShiinaCLI)
    cli._clarify_freetext = False
    cli._clarify_deadline = None
    cli._app = None

    all_models = [
        "google/gemini-2.5-flash:free",
        "deepseek/deepseek-chat",
        "deepseek/deepseek-r1:free",
        "meta-llama/llama-3.3-70b-instruct:free",
    ]

    # Matching logic tests
    assert ShiinaCLI._choice_matches("flash", "google/gemini-2.5-flash:free") is True
    assert ShiinaCLI._choice_matches("gemini flash", "google/gemini-2.5-flash:free") is True
    assert ShiinaCLI._choice_matches("free flash", "google/gemini-2.5-flash:free") is True
    assert ShiinaCLI._choice_matches("llama", "deepseek/deepseek-chat") is False
    assert ShiinaCLI._choice_matches("ds-r1", "deepseek/deepseek-r1:free") is True

    # Render with filter="deepseek"
    cli._clarify_state = {
        "question": "Select model:",
        "choices": all_models,
        "selected": 0,
        "multi_select": False,
        "selected_indices": set(),
        "allow_other": True,
        "filter": "deepseek",
    }
    frags = cli._get_clarify_display_fragments()
    rendered = "".join(part[1] for part in frags)
    assert "deepseek/deepseek-chat" in rendered
    assert "deepseek/deepseek-r1:free" in rendered
    assert "gemini-2.5-flash" not in rendered
    assert "llama-3.3" not in rendered
    assert "Filter: deepseek" in rendered

    # Render with filter="flash"
    cli._clarify_state["filter"] = "flash"
    frags_flash = cli._get_clarify_display_fragments()
    rendered_flash = "".join(part[1] for part in frags_flash)
    assert "gemini-2.5-flash" in rendered_flash
    assert "deepseek" not in rendered_flash

    # Render with non-matching filter
    cli._clarify_state["filter"] = "nonexistent-model-xyz"
    frags_empty = cli._get_clarify_display_fragments()
    rendered_empty = "".join(part[1] for part in frags_empty)
    assert "no choices match" in rendered_empty


def test_clarify_escape_clears_search_filter_before_cancelling():
    """Verify that Escape clears the search input first, and cancels only on second Escape."""
    import queue
    from cli import ShiinaCLI

    cli = ShiinaCLI.__new__(ShiinaCLI)
    q = queue.Queue()
    cli._clarify_state = {
        "question": "Pick model",
        "choices": ["model-a", "model-b"],
        "selected": 1,
        "response_queue": q,
        "allow_other": True,
        "filter": "mod",
    }
    cli._clarify_freetext = False
    cli._clarify_multi_base = None
    cli._secret_state = None
    cli._sudo_state = None
    cli._slash_confirm_state = None

    # Simulate app with current_buffer having "mod"
    mock_buf = MagicMock()
    mock_buf.text = "mod"
    def _reset():
        mock_buf.text = ""
    mock_buf.reset = _reset

    mock_app = MagicMock()
    mock_app.current_buffer = mock_buf
    cli._app = mock_app

    event = MagicMock()
    event.app = mock_app

    # First Escape: should clear the buffer and filter, but NOT cancel the modal
    cli._tui_handle_escape_modal(event)
    assert cli._clarify_state is not None
    assert mock_buf.text == ""
    assert cli._clarify_state["filter"] == ""
    assert cli._clarify_state["selected"] == 0
    assert q.empty()

    # Second Escape: buffer is empty, should cancel the modal
    cli._tui_handle_escape_modal(event)
    assert cli._clarify_state is None
    assert not q.empty()
    assert "user cancelled" in q.get_nowait().lower()


def test_clarify_enter_selects_filtered_choice():
    """Verify that pressing Enter selects the filtered choice correctly."""
    import queue
    from cli import ShiinaCLI

    cli = ShiinaCLI.__new__(ShiinaCLI)
    q = queue.Queue()
    all_choices = ["alpha-one", "beta-two", "gamma-three"]
    cli._clarify_state = {
        "question": "Pick one",
        "choices": all_choices,
        "selected": 0,
        "response_queue": q,
        "allow_other": False,
        "filter": "gamma",
    }
    cli._clarify_freetext = False
    cli._clarify_multi_base = None

    mock_buf = MagicMock()
    mock_buf.text = "gamma"
    mock_app = MagicMock()
    mock_app.current_buffer = mock_buf
    cli._app = mock_app
    event = MagicMock()
    event.app = mock_app

    # Generating display fragments populates _filtered_pairs
    cli._get_clarify_display_fragments()
    assert len(cli._clarify_state["_filtered_pairs"]) == 1
    assert cli._clarify_state["_filtered_pairs"][0][1] == "gamma-three"

    cli._tui_enter_clarify_choice(event)
    assert cli._clarify_state is None
    assert not q.empty()
    assert q.get_nowait() == "gamma-three"



