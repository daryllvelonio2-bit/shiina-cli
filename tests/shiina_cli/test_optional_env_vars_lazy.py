"""``OPTIONAL_ENV_VARS`` expands on first read, not at ``shiina_cli.config`` import.

The provider/platform-plugin entries come from importing every plugin, which drags urllib and the
transport modules onto every command's startup for a registry only the setup / config / dashboard
surfaces read. The mapping must still be complete for anything that reads it.
"""

import subprocess
import sys
import textwrap


def test_importing_config_does_not_discover_providers():
    code = textwrap.dedent(
        """
        import sys
        import shiina_cli.config  # noqa: F401
        assert "providers" not in sys.modules, "provider discovery ran at config import"
        """
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr


def test_provider_entries_are_present_after_a_read():
    from providers import list_providers
    from shiina_cli.config import OPTIONAL_ENV_VARS

    expected = {var for p in list_providers() if p.auth_type == "api_key" for var in p.env_vars}
    assert expected, "expected at least one bundled api_key provider"
    assert expected <= set(OPTIONAL_ENV_VARS)
    # Every read path materializes the same mapping.
    assert set(OPTIONAL_ENV_VARS.keys()) == set(OPTIONAL_ENV_VARS)
    assert len(dict(OPTIONAL_ENV_VARS.items())) == len(OPTIONAL_ENV_VARS)


def test_expansion_is_idempotent():
    from shiina_cli import config

    first = dict(config.OPTIONAL_ENV_VARS.items())
    config._inject_profile_env_vars()
    config._inject_platform_plugin_env_vars()
    assert dict(config.OPTIONAL_ENV_VARS.items()) == first
    assert config.ensure_optional_env_vars() is config.OPTIONAL_ENV_VARS
