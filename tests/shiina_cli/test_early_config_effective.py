"""The early redaction / IPv4 bridge reads config.yaml without importing shiina_cli.config.

Two booleans (``security.redact_secrets``, ``network.force_ipv4``) used to pull the whole config
import graph — urllib, the provider registry, the plugin tables — onto every command's startup.
The minimal read must still honour the keys, and must defer to the canonical effective loader when
``${VAR}`` expansion is actually in play.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import shiina_cli.main

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_importing_main_never_imports_the_config_graph():
    """The signal criterion for this change: `import shiina_cli.main` must not pull the config
    module (and through it urllib + the provider/plugin tables) on a configured home."""
    code = textwrap.dedent(
        f"""
        import os, sys, tempfile
        from pathlib import Path

        home = Path(tempfile.mkdtemp()) / ".shiina"
        home.mkdir()
        (home / "config.yaml").write_text("display:\\n  interface: cli\\n", encoding="utf-8")
        os.environ["SHIINA_HOME"] = str(home)

        sys.path.insert(0, {str(REPO_ROOT)!r})
        import shiina_cli.main  # noqa: F401
        loaded = [m for m in ("shiina_cli.config", "providers", "shiina_cli.config_effective")
                  if m in sys.modules]
        assert not loaded, f"eagerly imported: {{loaded}}"
        """
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr


def _write_config(tmp_path, monkeypatch, body: str):
    home = tmp_path / ".shiina"
    home.mkdir()
    (home / "config.yaml").write_text(textwrap.dedent(body))
    monkeypatch.setenv("SHIINA_HOME", str(home))
    monkeypatch.setattr(shiina_cli.main, "get_shiina_home", lambda: home)
    monkeypatch.setattr(shiina_cli.main, "_EARLY_EFFECTIVE_CACHE", None)
    return home


def test_raw_keys_are_read(tmp_path, monkeypatch):
    _write_config(
        tmp_path, monkeypatch,
        """
        security:
          redact_secrets: false
        network:
          force_ipv4: true
        """,
    )
    raw = shiina_cli.main._config_early_effective()
    assert raw["security"]["redact_secrets"] is False
    assert raw["network"]["force_ipv4"] is True


def test_env_template_defers_to_the_canonical_loader(tmp_path, monkeypatch):
    """``${VAR}`` is only expanded by config_effective — the early read must not see a literal."""
    _write_config(
        tmp_path, monkeypatch,
        """
        network:
          force_ipv4: "${MY_IPV4_FLAG}"
        """,
    )
    monkeypatch.setenv("MY_IPV4_FLAG", "1")
    raw = shiina_cli.main._config_early_effective()
    assert raw["network"]["force_ipv4"] == "1"


def test_missing_config_is_an_empty_mapping(tmp_path, monkeypatch):
    home = tmp_path / ".shiina"
    home.mkdir()
    monkeypatch.setenv("SHIINA_HOME", str(home))
    monkeypatch.setattr(shiina_cli.main, "get_shiina_home", lambda: home)
    monkeypatch.setattr(shiina_cli.main, "_EARLY_EFFECTIVE_CACHE", None)
    assert shiina_cli.main._config_early_effective() == {}
