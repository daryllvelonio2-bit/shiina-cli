"""A batch of parallel tool calls announces "preparing <tool>…" once per tool, not once per call (#10478)."""

from unittest.mock import patch

from tests.shiina_cli.test_tool_progress_scrollback import _make_cli
import tests.shiina_cli.test_tool_progress_scrollback as _scrollback


def _announce(cli, names):
    printed = []
    with patch.object(_scrollback._cli_mod, "_cprint", lambda line: printed.append(line)):
        for n in names:
            cli._on_tool_gen_start(n)
    return printed


def test_repeated_tool_in_one_batch_prints_once():
    cli = _make_cli(tool_progress="off")
    printed = _announce(cli, ["terminal", "terminal", "terminal", "read_file"])
    # "preparing <tool>…" lines are removed
    assert sum("preparing" in p for p in printed) == 0
