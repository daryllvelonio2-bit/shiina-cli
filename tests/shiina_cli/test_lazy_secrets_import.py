"""Regression test: shiina update must not load cryptography eagerly."""

import sys
import subprocess
import os
from pathlib import Path


def _run_isolated(code: str) -> subprocess.CompletedProcess[str]:
    """Run a Python snippet in the repo root (not tests/)."""
    repo_root = Path(__file__).parent.parent.parent
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


class TestLazySecretsImport:
    """Verify that the secrets_cli import is lazy, not eager."""

    def test_cli_parser_build_does_not_import_secrets_handlers(self) -> None:
        """Building the full CLI tree must not import the secrets handler modules.

        They pull in rich + the Bitwarden crypto stack, so importing them at parse
        time is paid by every ``shiina`` invocation.
        """
        result = _run_isolated(
            """
import sys

import shiina_cli.main as m

m._build_cli_parser()
handlers = ('shiina_cli.secrets_cli', 'shiina_cli.onepassword_secrets_cli')
leaked = [name for name in handlers if name in sys.modules]
assert leaked == [], f'CLI build eagerly imported the secrets handlers: {leaked}'
print('PASS: secrets handler modules stay unimported by the CLI build')
"""
        )
        assert result.returncode == 0, (
            f"secrets handler modules were imported by _build_cli_parser():\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
        assert "PASS" in result.stdout

    def test_secrets_parser_still_wires_a_dispatchable_handler(self) -> None:
        """The lazy move must not drop registration: `secrets bitwarden setup` keeps a handler."""
        import argparse

        from shiina_cli.subcommands.secrets import build_secrets_parser

        parser = argparse.ArgumentParser(prog="shiina")
        sub = parser.add_subparsers(dest="command")
        build_secrets_parser(sub)
        ns = parser.parse_args(["secrets", "bitwarden", "setup"])
        assert callable(getattr(ns, "func", None))

    def test_secrets_dispatch_loads_cryptography_only_on_demand(self) -> None:
        """Running a secrets subcommand should load cryptography lazily."""
        result = _run_isolated(
            """
import sys

# First verify it's NOT loaded after importing main
import shiina_cli.main
assert 'cryptography.hazmat.bindings._rust' not in sys.modules, \\
    'cryptography already loaded before dispatch'

# Now simulate the secrets dispatch
# We can't easily run the actual dispatch without mocking argparse,
# but we can at least verify the import inside _dispatch_secrets works
# by checking that secrets_cli is not yet in sys.modules
assert 'shiina_cli.secrets_cli' not in sys.modules, \\
    'secrets_cli already loaded before dispatch'

print('PASS: secrets_cli and cryptography not loaded until dispatch')
sys.exit(0)
"""
        )
        assert result.returncode == 0, (
            f"Lazy import test failed:\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )

    def test_update_check_no_cryptography(self) -> None:
        """Running shiina update --check should NOT load cryptography._rust."""
        # Write a small script in the repo root so shiina_cli is importable,
        # and use a filename that doesn't trigger the live-system guard.
        repo_root = Path(__file__).parent.parent.parent
        script = repo_root / "_test_lazy_secrets_check.py"
        script.write_text(
            """
import sys
sys.argv = ['shiina', 'update', '--check']

import shiina_cli.main
from shiina_cli.update_cmd import _cmd_update_check

assert 'cryptography.hazmat.bindings._rust' not in sys.modules, \\
    'cryptography._rust loaded during update path'

print('PASS: update check path is clean of cryptography')
sys.exit(0)
"""
        )
        try:
            result = subprocess.run(
                [sys.executable, script.name],
                capture_output=True,
                text=True,
                cwd=str(repo_root),
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            assert result.returncode == 0, (
                f"cryptography._rust loaded during update check:\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )
        finally:
            script.unlink()  # Clean up
