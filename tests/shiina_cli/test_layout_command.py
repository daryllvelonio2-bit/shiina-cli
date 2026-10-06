"""Tests for the /layout CLI command and the structural-layout config key.

/layout is registered in COMMAND_REGISTRY (advertised by /help, tab-completion and
the desktop slash registry) and must dispatch to its handler rather than falling
through to "Unknown command". The handler is the CLI half of one contract with the
TUI: both write ``display.layout`` and both accept exactly the LAYOUT_IDS words.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from cli import ShiinaCLI


def _import_cli():
    import shiina_cli.config as config_mod

    if not hasattr(config_mod, "save_env_value_secure"):
        config_mod.save_env_value_secure = lambda key, value: {
            "success": True,
            "stored_as": key,
            "validated": False,
        }

    import cli as cli_mod

    return cli_mod


def _make_cli():
    cli_obj = ShiinaCLI.__new__(ShiinaCLI)
    cli_obj.config = {}
    cli_obj.console = MagicMock()
    cli_obj.agent = None
    cli_obj.conversation_history = []
    cli_obj.session_id = None
    cli_obj._pending_input = MagicMock()
    return cli_obj


class TestLayoutDispatch(unittest.TestCase):
    def test_layout_dispatches_to_handler(self):
        cli_obj = _make_cli()
        with patch.object(cli_obj, "_handle_layout_command") as mock_handler:
            result = cli_obj.process_command("/layout studio")

        mock_handler.assert_called_once_with("/layout studio")
        self.assertTrue(result)

    def test_layout_is_not_unknown_command(self):
        cli_obj = _make_cli()
        with (
            patch("cli._cprint") as mock_cprint,
            patch("cli.save_config_value", return_value=True),
        ):
            result = cli_obj.process_command("/layout minimal")

        printed = " ".join(str(c) for c in mock_cprint.call_args_list)
        self.assertNotIn("Unknown command", printed)
        self.assertTrue(result)


class TestHandleLayoutCommand(unittest.TestCase):
    def _stub(self, current=None):
        config = {}
        if current is not None:
            config["display"] = {"layout": current}
        return SimpleNamespace(config=config)

    def test_no_args_shows_current_layout(self):
        cli_mod = _import_cli()
        stub = self._stub()
        with (
            patch.object(cli_mod, "_cprint") as mock_cprint,
            patch.object(cli_mod, "save_config_value") as mock_save,
        ):
            cli_mod.ShiinaCLI._handle_layout_command(stub, "/layout")

        mock_save.assert_not_called()
        # The unset key reads back as the default, never as blank.
        printed = " ".join(str(c) for c in mock_cprint.call_args_list)
        self.assertIn("workbench", printed)

    def test_valid_layout_saves_to_the_key_the_tui_reads(self):
        cli_mod = _import_cli()
        stub = self._stub("workbench")
        with (
            patch.object(cli_mod, "_cprint"),
            patch.object(cli_mod, "save_config_value", return_value=True) as mock_save,
        ):
            cli_mod.ShiinaCLI._handle_layout_command(stub, "/layout Studio")

        mock_save.assert_called_once_with("display.layout", "studio")
        self.assertEqual(stub.config["display"]["layout"], "studio")

    def test_unknown_layout_prints_usage_and_does_not_save(self):
        cli_mod = _import_cli()
        stub = self._stub("workbench")
        with (
            patch.object(cli_mod, "_cprint") as mock_cprint,
            patch.object(cli_mod, "save_config_value") as mock_save,
        ):
            cli_mod.ShiinaCLI._handle_layout_command(stub, "/layout emacs")

        mock_save.assert_not_called()
        self.assertEqual(stub.config["display"]["layout"], "workbench")
        printed = " ".join(str(c) for c in mock_cprint.call_args_list)
        self.assertIn("Usage: /layout", printed)


class TestLayoutRegistry(unittest.TestCase):
    def test_registry_entry_matches_the_shared_word_list(self):
        from shiina_cli.commands import COMMAND_REGISTRY
        from shiina_constants import LAYOUT_IDS

        layout = next(c for c in COMMAND_REGISTRY if c.name == "layout")

        self.assertEqual(layout.category, "Configuration")
        self.assertEqual(set(layout.subcommands), set(LAYOUT_IDS))
        self.assertEqual(layout.desktop, "terminal")


if __name__ == "__main__":
    unittest.main()
