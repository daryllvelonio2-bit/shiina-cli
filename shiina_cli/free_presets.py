"""Free-usage rotation presets for Shiina CLI.

Provides persistent storage, interactive setup wizard (/shiina-setup),
preset application with multi-level rotation (/shiina-free-<name>),
and preset management (/shiina-free [list|show|delete]).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from shiina_constants import get_shiina_home
from agent.credential_pool import (
    STRATEGY_FILL_FIRST,
    STRATEGY_LEAST_USED,
    STRATEGY_RANDOM,
    STRATEGY_ROUND_ROBIN,
    SUPPORTED_POOL_STRATEGIES,
    load_pool,
)

logger = logging.getLogger(__name__)

PRESETS_FILENAME = "free_presets.json"

ROTATION_MODES: dict[str, str] = {
    STRATEGY_FILL_FIRST: "Use first key until exhausted, then next",
    STRATEGY_ROUND_ROBIN: "Cycle through keys evenly",
    STRATEGY_LEAST_USED: "Always pick the least-used key",
    STRATEGY_RANDOM: "Random selection",
}

DEFAULT_ROTATION_MODE = STRATEGY_ROUND_ROBIN


# ── Storage & Data Model ──────────────────────────────────────────────────


def get_presets_file_path() -> Path:
    """Return the absolute path to ~/.shiina/free_presets.json."""
    return get_shiina_home() / PRESETS_FILENAME


def normalize_preset_name(name: str) -> str:
    """Normalize preset name by stripping command prefix and invalid chars."""
    clean = (name or "").strip()
    clean = re.sub(r"^[/\\]+", "", clean)
    if clean.lower().startswith("shiina-free-"):
        clean = clean[len("shiina-free-") :]
    elif clean.lower().startswith("shiina-free"):
        clean = clean[len("shiina-free") :].lstrip("-_ ")
    clean = re.sub(r"[^\w\-\.]", "-", clean)
    return clean.strip("-_.").lower()


def load_presets() -> dict[str, dict]:
    """Load all presets from disk; returns {normalized_name: preset_dict}."""
    path = get_presets_file_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {
                normalize_preset_name(k): v
                for k, v in data.items()
                if isinstance(v, dict) and normalize_preset_name(k)
            }
    except Exception as exc:
        logger.warning("Failed to load free presets from %s: %s", path, exc)
    return {}


def save_preset(
    name: str,
    providers: list[dict],
    rotation_mode: str = DEFAULT_ROTATION_MODE,
    description: str = "",
) -> dict:
    """Save or update a preset persistently. Returns the saved preset dict."""
    norm_name = normalize_preset_name(name)
    if not norm_name:
        raise ValueError("Preset name cannot be empty.")
    if not providers:
        raise ValueError("Preset must contain at least one provider entry.")

    mode = rotation_mode.strip().lower()
    if mode not in SUPPORTED_POOL_STRATEGIES:
        mode = DEFAULT_ROTATION_MODE

    validated_providers: list[dict] = []
    for p in providers:
        prov = str(p.get("provider") or "").strip().lower()
        model = str(p.get("model") or "").strip()
        if not prov or not model:
            continue
        validated_providers.append({
            "provider": prov,
            "model": model,
        })

    if not validated_providers:
        raise ValueError("At least one valid provider and model pair is required.")

    preset_data = {
        "name": norm_name,
        "providers": validated_providers,
        "rotation_mode": mode,
        "description": description or f"Free rotation preset {norm_name}",
        "updated_at": time.time(),
    }

    presets = load_presets()
    presets[norm_name] = preset_data

    path = get_presets_file_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(presets, indent=2), encoding="utf-8")
        tmp_path.replace(path)
    except Exception as exc:
        logger.error("Failed to save free presets to %s: %s", path, exc)
        raise

    return preset_data


def get_preset(name: str) -> dict | None:
    """Fetch a preset by name (case-insensitive, prefix-tolerant)."""
    norm = normalize_preset_name(name)
    if not norm:
        return None
    presets = load_presets()
    return presets.get(norm)


def delete_preset(name: str) -> bool:
    """Delete a preset by name. Returns True if found and deleted."""
    norm = normalize_preset_name(name)
    if not norm:
        return False
    presets = load_presets()
    if norm not in presets:
        return False
    del presets[norm]
    path = get_presets_file_path()
    try:
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(presets, indent=2), encoding="utf-8")
        tmp_path.replace(path)
        return True
    except Exception as exc:
        logger.error("Failed to persist deletion to %s: %s", path, exc)
        return False


def list_presets() -> list[dict]:
    """Return all presets as a list sorted by updated_at descending."""
    presets = load_presets()
    items = list(presets.values())
    items.sort(key=lambda p: p.get("updated_at", 0), reverse=True)
    return items


# ── Usable Providers & Models Discovery ───────────────────────────────────


def get_usable_providers_for_setup() -> list[dict]:
    """Discover authenticated/usable providers and their models."""
    from shiina_cli.model_switch_providers import list_authenticated_providers

    try:
        rows = list_authenticated_providers()
    except Exception as exc:
        logger.warning("list_authenticated_providers failed: %s", exc)
        rows = []

    usable: list[dict] = []
    for r in rows:
        slug = str(r.get("slug") or "").strip().lower()
        if not slug:
            continue
        try:
            pool = load_pool(slug)
            entries = list(pool.entries()) if pool else []
            key_count = len(entries)
        except Exception:
            key_count = 1 if r.get("source") != "built-in" else 0

        models = [str(m) for m in r.get("models") or [] if str(m).strip()]
        usable.append({
            "slug": slug,
            "name": r.get("name") or slug,
            "models": models,
            "key_count": key_count,
        })

    return usable


# ── Preset Application & Execution ────────────────────────────────────────


def apply_free_preset(cli: Any, name_or_preset: str | dict) -> tuple[bool, str]:
    """Apply a free preset to the live CLI and agent session."""
    if isinstance(name_or_preset, dict):
        preset = name_or_preset
    else:
        preset = get_preset(name_or_preset)
        if not preset:
            norm = normalize_preset_name(name_or_preset)
            available = [p["name"] for p in list_presets()]
            avail_str = f" Available presets: {', '.join(available)}" if available else " No presets saved yet. Run /shiina-setup to create one."
            return False, f"Preset '{norm}' not found.{avail_str}"

    preset_name = preset.get("name", "unnamed")
    providers = preset.get("providers", [])
    if not providers:
        return False, f"Preset '{preset_name}' has no configured providers."

    rotation_mode = preset.get("rotation_mode", DEFAULT_ROTATION_MODE)

    # 1. Update credential pool strategies for all providers in preset
    try:
        from shiina_cli.config import load_config, save_config

        cfg = load_config()
        pool_strategies = cfg.get("credential_pool_strategies")
        if not isinstance(pool_strategies, dict):
            pool_strategies = {}
        for p in providers:
            prov = p.get("provider")
            if prov:
                pool_strategies[prov] = rotation_mode
        cfg["credential_pool_strategies"] = pool_strategies
        save_config(cfg)
    except Exception as exc:
        logger.debug("Failed to save pool strategies to config.yaml: %s", exc)

    # 2. Update active in-memory pools
    for p in providers:
        prov = p.get("provider")
        if prov:
            try:
                pool = load_pool(prov)
                pool._strategy = rotation_mode
            except Exception:
                pass

    # 3. Primary provider and model
    primary = providers[0]
    primary_prov = primary["provider"]
    primary_model = primary["model"]
    fallback_chain = [
        {"provider": p["provider"], "model": p["model"]}
        for p in providers[1:]
    ]

    # 4. Resolve credentials and switch CLI state
    resolved = None
    try:
        from shiina_cli.runtime_provider import resolve_runtime_provider

        resolved = resolve_runtime_provider(
            requested=primary_prov, target_model=primary_model
        )
    except Exception as exc:
        logger.debug("resolve_runtime_provider error: %s", exc)

    cli.model = primary_model
    cli.provider = primary_prov
    cli.requested_provider = primary_prov
    if resolved:
        if resolved.get("api_key"):
            cli.api_key = resolved["api_key"]
        if resolved.get("base_url"):
            cli.base_url = resolved["base_url"]
        if resolved.get("api_mode"):
            cli.api_mode = resolved["api_mode"]
        if resolved.get("credential_pool"):
            cli._credential_pool = resolved["credential_pool"]

    cli._fallback_model = list(fallback_chain)
    cli._active_free_preset = preset

    # 5. Switch active agent if running
    agent = getattr(cli, "agent", None)
    if agent is not None:
        try:
            agent.switch_model(
                new_model=primary_model,
                new_provider=primary_prov,
                api_key=getattr(cli, "api_key", ""),
                base_url=getattr(cli, "base_url", ""),
                api_mode=getattr(cli, "api_mode", ""),
            )
        except Exception as exc:
            logger.warning("agent.switch_model error on preset apply: %s", exc)

        # Ensure fallback chain is configured
        agent._fallback_chain = list(fallback_chain)
        agent._fallback_index = 0
        agent._fallback_model = fallback_chain[0] if fallback_chain else None
        agent._active_free_preset = preset

    # 6. Build clean user-facing summary
    chain_labels = [f"{p['provider']}:{p['model']}" for p in providers]
    summary_lines = [
        f"  ✨ Applied free rotation preset: {preset_name}",
        f"  • Active primary: {primary_prov} ({primary_model})",
    ]
    if fallback_chain:
        summary_lines.append(
            f"  • Fallback chain: {' → '.join(chain_labels[1:])}"
        )
    summary_lines.append(
        f"  • Key rotation mode: {rotation_mode} ({ROTATION_MODES.get(rotation_mode, '')})"
    )
    return True, "\n".join(summary_lines)


# ── Interactive Setup Wizard (/shiina-setup) ──────────────────────────────


def _is_clarify_cancelled(resp: Any) -> bool:
    """Check if the clarify modal response was explicitly cancelled or timed out."""
    if resp is None:
        return True
    s = str(resp).strip()
    lower = s.lower()
    if "cancelled" in lower or "did not provide a response" in lower or s == "__CANCELLED__":
        return True
    return False


def _ask_wizard(
    cli: Any = None,
    prompt: str = "",
    choices: Optional[list[str]] = None,
    multi_select: bool = False,
    default: str = "",
    reader: Optional[Callable[[str], str]] = None,
    initial_selected: int = 0,
    preselected: Optional[list[int]] = None,
    allow_other: bool = True,
    searchable: bool = False,
) -> str | None:
    """Prompt the user safely inside or outside prompt_toolkit.

    Never calls built-in input() when prompt_toolkit's event loop owns stdin
    (getattr(cli, "_app", None) is not None), as doing so blocks on the daemon thread
    and swallows all user keystrokes. In interactive TUI mode with _clarify_callback,
    it leverages the TUI modal overlay.
    """
    if reader is not None:
        try:
            val = reader(prompt)
            if val is None or _is_clarify_cancelled(val):
                return None
            val_str = str(val).strip()
            if not val_str and default:
                return default
            return val_str
        except (EOFError, KeyboardInterrupt):
            return None

    app = getattr(cli, "_app", None) if cli else None

    # TUI mode: app is running and cli has _clarify_callback
    if app is not None and hasattr(cli, "_clarify_callback") and callable(cli._clarify_callback):
        try:
            try:
                import inspect
                sig = inspect.signature(cli._clarify_callback)
                kwargs = {}
                if "initial_selected" in sig.parameters:
                    kwargs["initial_selected"] = initial_selected
                if "preselected" in sig.parameters:
                    kwargs["preselected"] = preselected
                if "allow_other" in sig.parameters:
                    kwargs["allow_other"] = allow_other
                if "searchable" in sig.parameters:
                    kwargs["searchable"] = searchable
                res = cli._clarify_callback(
                    prompt,
                    choices=choices or [],
                    multi_select=multi_select,
                    **kwargs,
                )
            except (TypeError, ValueError):
                res = cli._clarify_callback(
                    prompt,
                    choices=choices or [],
                    multi_select=multi_select,
                )

            if _is_clarify_cancelled(res):
                return None
            res_str = str(res).strip()
            if not res_str and default:
                return default
            return res_str
        except Exception as exc:
            logger.warning("Error in _clarify_callback during setup wizard: %s", exc)
            return None

    # App is running but no _clarify_callback (or unsupported off-main thread):
    # Under no circumstances should input() be called while app owns stdin.
    if app is not None:
        prompt_helper = getattr(cli, "_prompt_text_input", None)
        if callable(prompt_helper):
            try:
                res = prompt_helper(prompt)
                if res is not None and str(res).strip():
                    return str(res).strip()
            except Exception:
                pass
        return None

    # Non-TUI / headless / script console (no prompt_toolkit app running):
    prompt_helper = getattr(cli, "_prompt_text_input", None) if cli else None
    if callable(prompt_helper):
        try:
            res = prompt_helper(prompt)
            if res is not None and str(res).strip():
                return str(res).strip()
        except Exception:
            pass

    try:
        raw = input(prompt)
        raw_str = raw.strip()
        if not raw_str and default:
            return default
        return raw_str
    except (EOFError, KeyboardInterrupt):
        return None


def _ask_input(
    prompt: str,
    cli: Any = None,
    reader: Optional[Callable[[str], str]] = None,
) -> str | None:
    """Prompt the user for single-line text (backwards compatibility)."""
    return _ask_wizard(cli=cli, prompt=prompt, reader=reader)


def run_setup_wizard(
    cli: Any,
    args_str: str = "",
    reader: Optional[Callable[[str], str]] = None,
    out_print: Callable[[str], None] = print,
) -> bool:
    """Run the interactive /shiina-setup wizard."""
    parsed_args = {}
    if args_str.strip():
        tokens = shlex.split(args_str)
        if tokens and not tokens[0].startswith("--"):
            parsed_args["name"] = tokens[0]
            tokens = tokens[1:]
        idx = 0
        while idx < len(tokens):
            t = tokens[idx]
            if t == "--name" and idx + 1 < len(tokens):
                parsed_args["name"] = tokens[idx + 1]
                idx += 2
            elif t == "--providers" and idx + 1 < len(tokens):
                parsed_args["providers"] = tokens[idx + 1]
                idx += 2
            elif t == "--mode" and idx + 1 < len(tokens):
                parsed_args["mode"] = tokens[idx + 1]
                idx += 2
            else:
                idx += 1

    is_tui = (
        cli is not None
        and getattr(cli, "_app", None) is not None
        and hasattr(cli, "_clarify_callback")
        and reader is None
    )

    out_print("\n  🔮 Shiina Free-Usage Rotation Preset Setup\n")

    # Step a: Setup name (with duplicate detection and Edit/Replace flow)
    is_edit = False
    existing = None
    name = None

    while True:
        if not name:
            name = parsed_args.get("name")
        if not name:
            step_a_prompt = (
                "Preset name (e.g. deepseek, free-tier):"
                if is_tui
                else "  Preset name (e.g. deepseek, free-tier): "
            )
            name = _ask_wizard(
                cli=cli,
                prompt=step_a_prompt,
                choices=[] if is_tui else None,
                reader=reader,
            )
        if name is None:
            out_print("  Cancelled setup.\n")
            return False
        if not name.strip():
            out_print("  Cancelled setup: no preset name provided.\n")
            return False

        norm_name = normalize_preset_name(name)
        if not norm_name:
            out_print("  ✗ Invalid preset name.\n")
            return False

        existing = get_preset(norm_name)
        if existing and not ("providers" in parsed_args and "mode" in parsed_args):
            out_print(f"\n  ⚠️  Preset '{norm_name}' already exists.")
            action_prompt = f"Preset '{norm_name}' already exists. What would you like to do?"
            action_choices = [
                "Edit existing configuration",
                "Replace / Overwrite with new setup",
                "Choose a different name",
                "Cancel",
            ]
            action = _ask_wizard(
                cli=cli,
                prompt=action_prompt,
                choices=action_choices,
                allow_other=False,
                searchable=False,
                reader=reader,
            )
            if action is None:
                out_print("  Cancelled setup.\n")
                return False

            act_str = str(action).strip().lower()
            if "cancel" in act_str:
                out_print("  Cancelled setup.\n")
                return False
            elif "diff" in act_str or "different" in act_str or act_str.startswith("3"):
                name = None
                parsed_args.pop("name", None)
                continue
            elif "edit" in act_str or act_str.startswith("1"):
                is_edit = True
                break
            else:
                # Replace / overwrite
                is_edit = False
                break
        else:
            break

    # Step b: Usable providers
    usable = get_usable_providers_for_setup()
    if not usable:
        out_print("  ✗ No usable/authenticated providers detected in your configuration.\n")
        return False

    existing_prov_slugs = []
    if is_edit and existing:
        existing_prov_slugs = [p.get("provider") for p in existing.get("providers", [])]
        out_print(f"  Current providers in '{norm_name}': {', '.join(existing_prov_slugs)}")

    if not is_tui:
        out_print(f"  Setting up preset: {norm_name}\n")
        out_print("  Available providers:")
        for idx, p in enumerate(usable, 1):
            key_label = f"{p['key_count']} key{'s' if p['key_count'] != 1 else ''}"
            out_print(f"    {idx}. {p['name']} ({p['slug']}) — {key_label}")

    selected_providers: list[dict] = []

    # Check if passed via flags
    if "providers" in parsed_args:
        # Format: prov1:model1,prov2:model2
        pairs = parsed_args["providers"].split(",")
        for pair in pairs:
            if ":" in pair:
                p_slug, m_name = pair.split(":", 1)
                selected_providers.append({
                    "provider": p_slug.strip().lower(),
                    "model": m_name.strip(),
                })
    else:
        if is_tui:
            prov_choices = [
                f"{p['name']} ({p['slug']}) — {p['key_count']} key{'s' if p['key_count'] != 1 else ''}"
                for p in usable
            ]
            preselected = []
            if is_edit and existing_prov_slugs:
                preselected = [idx for idx, p in enumerate(usable) if p["slug"] in existing_prov_slugs]

            prov_prompt = f"Select providers to include in '{norm_name}' (Space toggles):"
            raw_choice = _ask_wizard(
                cli=cli,
                prompt=prov_prompt,
                choices=prov_choices,
                multi_select=True,
                preselected=preselected,
                allow_other=False,
                searchable=True,
                reader=reader,
            )
        else:
            out_print("")
            prov_prompt = "  Select providers in rotation order (comma-separated, e.g. 1, 3, 2): "
            raw_choice = _ask_wizard(
                cli=cli,
                prompt=prov_prompt,
                reader=reader,
            )

        if raw_choice is None:
            out_print("  Cancelled setup.\n")
            return False

        chosen_indices = []
        raw_parts = [p.strip() for p in raw_choice.split(",") if p.strip()]
        if len(raw_parts) == 1 and " " in raw_parts[0] and all(x.isdigit() for x in raw_parts[0].split()):
            raw_parts = raw_parts[0].split()

        for part in raw_parts:
            matched_idx = None
            try:
                num = int(part)
                if 1 <= num <= len(usable):
                    matched_idx = num - 1
            except ValueError:
                pass

            if matched_idx is None:
                part_lower = part.lower()
                for idx_u, u in enumerate(usable):
                    slug = u["slug"].lower()
                    name_u = u["name"].lower()
                    if slug == part_lower or name_u == part_lower:
                        matched_idx = idx_u
                        break
                    if slug in part_lower or name_u in part_lower:
                        matched_idx = idx_u
                        break

            if matched_idx is not None and matched_idx not in chosen_indices:
                chosen_indices.append(matched_idx)

        # If editing and user pressed Enter without selecting, keep existing providers
        if not chosen_indices and is_edit and existing_prov_slugs:
            for ep in existing_prov_slugs:
                for idx_u, u in enumerate(usable):
                    if u["slug"] == ep and idx_u not in chosen_indices:
                        chosen_indices.append(idx_u)
                        break

        if not chosen_indices:
            out_print("  ✗ No valid providers selected.\n")
            return False

        # Step c: Choose model for each chosen provider (ALL available models included)
        for i in chosen_indices:
            prov = usable[i]
            prov_slug = prov["slug"]
            prov_models = prov["models"] or []

            # Prioritize free models at the top while preserving all available models
            free_models = [m for m in prov_models if ":free" in m.lower() or "-free" in m.lower()]
            other_models = [m for m in prov_models if m not in free_models]
            all_models = free_models + other_models

            # Determine default model (if editing, use previous model for this provider)
            existing_model = ""
            if is_edit and existing:
                existing_model = next(
                    (p.get("model") for p in existing.get("providers", []) if p.get("provider") == prov_slug),
                    ""
                )
            default_model = existing_model or (all_models[0] if all_models else "")

            initial_idx = 0
            if default_model in all_models:
                initial_idx = all_models.index(default_model)

            if is_tui:
                model_choices = list(all_models)
                model_prompt = f"Select model for {prov['name']} ({prov_slug}):"
                model_choice = _ask_wizard(
                    cli=cli,
                    prompt=model_prompt,
                    choices=model_choices,
                    default=default_model,
                    initial_selected=initial_idx,
                    allow_other=True,
                    searchable=True,
                    reader=reader,
                )
            else:
                out_print(f"\n  --- Models for {prov['name']} ({prov_slug}) ---")
                for m_idx, m in enumerate(all_models, 1):
                    out_print(f"    {m_idx}. {m}")

                prompt = f"  Select model [1-{len(all_models)}] or enter custom model [{default_model}]: "
                model_choice = _ask_wizard(
                    cli=cli,
                    prompt=prompt,
                    default=default_model,
                    reader=reader,
                )

            if model_choice is None:  # User cancelled via Esc / Ctrl+C
                out_print("  Cancelled setup.\n")
                return False

            picked_model = ""
            if not model_choice:
                picked_model = default_model
            else:
                try:
                    m_num = int(model_choice)
                    if 1 <= m_num <= len(all_models):
                        picked_model = all_models[m_num - 1]
                    else:
                        picked_model = model_choice
                except ValueError:
                    picked_model = model_choice

            if not picked_model:
                picked_model = default_model or "default"

            selected_providers.append({
                "provider": prov_slug,
                "model": picked_model,
            })

    if not selected_providers:
        out_print("  ✗ No providers configured.\n")
        return False

    # Step d: Rotation mode
    mode = parsed_args.get("mode")
    if not mode:
        mode_keys = list(ROTATION_MODES.keys())
        default_mode = DEFAULT_ROTATION_MODE
        if is_edit and existing:
            default_mode = existing.get("rotation_mode", DEFAULT_ROTATION_MODE)

        initial_mode_idx = 0
        if default_mode in mode_keys:
            initial_mode_idx = mode_keys.index(default_mode)

        if is_tui:
            mode_choices = [f"{mk} — {ROTATION_MODES[mk]}" for mk in mode_keys]
            mode_prompt = f"Choose API-key rotation mode [default: {default_mode}]:"
            mode_choice = _ask_wizard(
                cli=cli,
                prompt=mode_prompt,
                choices=mode_choices,
                default=default_mode,
                initial_selected=initial_mode_idx,
                allow_other=False,
                searchable=False,
                reader=reader,
            )
        else:
            out_print("\n  API-Key Rotation Modes (for providers with multiple keys):")
            for m_idx, mk in enumerate(mode_keys, 1):
                out_print(f"    {m_idx}. {mk:12s} — {ROTATION_MODES[mk]}")

            mode_choice = _ask_wizard(
                cli=cli,
                prompt=f"  Choose mode [1-{len(mode_keys)}, default: {default_mode}]: ",
                default=default_mode,
                reader=reader,
            )

        if mode_choice is None:  # User cancelled via Esc / Ctrl+C
            out_print("  Cancelled setup.\n")
            return False

        if not mode_choice:
            mode = default_mode
        else:
            cleaned = mode_choice.split("—")[0].split("-")[0].strip().lower()
            if cleaned in SUPPORTED_POOL_STRATEGIES:
                mode = cleaned
            else:
                try:
                    m_num = int(mode_choice)
                    if 1 <= m_num <= len(mode_keys):
                        mode = mode_keys[m_num - 1]
                    else:
                        mode = mode_choice.strip().lower()
                except ValueError:
                    mode = mode_choice.strip().lower()

    if mode not in SUPPORTED_POOL_STRATEGIES:
        mode = DEFAULT_ROTATION_MODE

    # Step e: Save preset
    saved = save_preset(
        name=norm_name,
        providers=selected_providers,
        rotation_mode=mode,
    )

    action_word = "updated" if is_edit else "saved"
    out_print(f"\n  ✓ Preset '{norm_name}' {action_word} successfully!")
    out_print("  Providers in rotation order:")
    for idx, sp in enumerate(saved["providers"], 1):
        out_print(f"    {idx}. {sp['provider']} → model: {sp['model']}")
    out_print(f"  API-Key rotation mode: {saved['rotation_mode']} ({ROTATION_MODES.get(saved['rotation_mode'], '')})")
    out_print(f"\n  To activate this preset anytime, type:")
    out_print(f"    /shiina-free-{norm_name}\n")
    return True


# ── Preset Management (/shiina-free) ──────────────────────────────────────


def handle_free_management(
    cli: Any,
    command: str,
    out_print: Callable[[str], None] = print,
) -> bool:
    """Handle /shiina-free and /shiina-free-<name> commands."""
    cmd_stripped = command.strip()
    cmd_lower = cmd_stripped.lower()
    first_word = cmd_lower.split()[0] if cmd_lower else ""

    # Case 1: Directly invoked via /shiina-free-<name>
    if first_word.startswith("/shiina-free-") and len(first_word) > len("/shiina-free-"):
        preset_name = first_word[len("/shiina-free-") :].strip()
        ok, msg = apply_free_preset(cli, preset_name)
        out_print(msg)
        return ok

    parts = cmd_stripped.split()
    args = parts[1:] if len(parts) > 1 else []

    # Case 2: Bare /shiina-free or /shiina-free list
    if not args or args[0].lower() in ("list", "ls"):
        presets = list_presets()
        if not presets:
            out_print("  No free-usage rotation presets found.")
            out_print("  Create your first preset with: /shiina-setup\n")
            return True

        out_print("\n  📦 Saved Free-Usage Rotation Presets:")
        for p in presets:
            p_name = p["name"]
            prov_summaries = [f"{pr['provider']}:{pr['model']}" for pr in p.get("providers", [])]
            chain_str = " → ".join(prov_summaries)
            mode_str = p.get("rotation_mode", DEFAULT_ROTATION_MODE)
            out_print(f"  • {p_name:20s} [mode: {mode_str}]")
            out_print(f"    Route: {chain_str}")
            out_print(f"    Run:   /shiina-free-{p_name}\n")
        return True

    subcmd = args[0].lower()

    # Case 3: /shiina-free show <name>
    if subcmd in ("show", "info", "view", "get"):
        if len(args) < 2:
            out_print("  Usage: /shiina-free show <preset-name>")
            return False
        preset = get_preset(args[1])
        if not preset:
            out_print(f"  ✗ Preset '{args[1]}' not found.")
            return False

        out_print(f"\n  📦 Preset Details: {preset['name']}")
        out_print(f"  Rotation mode: {preset.get('rotation_mode')} ({ROTATION_MODES.get(preset.get('rotation_mode', ''), '')})")
        out_print("  Providers in failover order:")
        for idx, pr in enumerate(preset.get("providers", []), 1):
            slug = pr["provider"]
            try:
                pool = load_pool(slug)
                cnt = len(list(pool.entries()))
            except Exception:
                cnt = 0
            out_print(f"    {idx}. {slug:15s} model: {pr['model']} ({cnt} key{'s' if cnt != 1 else ''} in pool)")
        out_print(f"\n  To apply: /shiina-free-{preset['name']}\n")
        return True

    # Case 4: /shiina-free delete <name>
    if subcmd in ("delete", "remove", "rm", "del"):
        if len(args) < 2:
            out_print("  Usage: /shiina-free delete <preset-name>")
            return False
        target = args[1]
        if delete_preset(target):
            out_print(f"  ✓ Deleted preset '{target}'.")
            return True
        else:
            out_print(f"  ✗ Preset '{target}' not found.")
            return False

    # Case 5: /shiina-free <preset-name> (direct apply)
    ok, msg = apply_free_preset(cli, args[0])
    out_print(msg)
    return ok
