"""``--<unknown>`` means "resume a session named <unknown>" — but only for flags that really
are unknown (``shiina --tui --shiina``).

Regression: the known-flag set was collected from the root parser and its *direct*
subcommands only, so every flag defined one level deeper (``profile create --blank``,
``profile delete --yes``, ``profile create --clone-from``) was mistaken for a session name,
rewritten to ``--resume <flag>``, and then rejected by the top-level parser:

    shiina: error: unrecognized arguments: --resume blank
"""

from __future__ import annotations

import argparse
import re

import pytest

from shiina_cli.main import (
    _build_cli_parser,
    _parse_cli_args,
    _rewrite_named_session_flags,
)

# The rewrite ignores these prefixes, anything carrying a value, and the session flags it
# injects itself, so only flags it would genuinely consider are interesting here.
_ELIGIBLE = re.compile(r"^--(?!no-|print-|resume|continue)[^=]+$")


@pytest.fixture(scope="module")
def cli():
    return _build_cli_parser()


def _defined_options(parser, subparsers):
    """Every option string in the tree, via an independent walk of argparse internals."""
    stack = [parser, *subparsers.choices.values()]
    seen, options = set(), set()
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        for action in getattr(current, "_actions", []):
            options.update(action.option_strings)
            if isinstance(action, argparse._SubParsersAction):
                stack.extend(action.choices.values())
    return options


def test_no_real_flag_is_ever_rewritten_as_a_session_name(cli):
    """A flag the CLI defines anywhere must never be interpreted as a session name."""
    parser, subparsers = cli
    flags = sorted(f for f in _defined_options(parser, subparsers) if _ELIGIBLE.match(f))
    assert flags, "expected the CLI to define long options"
    # `--resume` is defined by the CLI, so it must be excluded before this assertion.
    assert "--resume" not in flags

    mistaken = [
        flag
        for flag in flags
        if _rewrite_named_session_flags([flag], parser, subparsers)[0] != [flag]
    ]
    assert not mistaken, f"real flags mistaken for session names: {mistaken}"


def test_nested_subcommand_flags_survive_the_rewrite(cli):
    """argv must reach argparse byte-identical for flags owned by a nested subcommand."""
    parser, subparsers = cli
    for argv in (
        ["profile", "create", "dev-1", "--blank"],
        ["profile", "create", "dev-1", "--clone-from", "default"],
        ["profile", "delete", "dev-1", "--yes"],
        ["profile", "create", "dev-1", "--description", "scratch profile"],
    ):
        rewritten, auto = _rewrite_named_session_flags(argv, parser, subparsers)
        assert rewritten == argv, f"{argv} was rewritten to {rewritten}"
        assert auto is False


def test_nested_subcommand_flag_parses(cli):
    """End-to-end: the nested flag must land on the parsed namespace."""
    parser, subparsers = cli
    args = _parse_cli_args(parser, subparsers, ["profile", "create", "dev-1", "--blank"])
    assert args.profile_name == "dev-1"
    assert args.blank is True


def test_unknown_flag_without_a_subcommand_is_still_a_session_name(cli):
    """The named-session convenience itself must keep working."""
    parser, subparsers = cli
    assert _rewrite_named_session_flags(["--shiina"], parser, subparsers) == (
        ["--resume", "shiina"],
        True,
    )
    assert _rewrite_named_session_flags(["--tui", "--shiina"], parser, subparsers) == (
        ["--tui", "--resume", "shiina"],
        True,
    )


def test_walker_reaches_deeply_nested_parsers(cli):
    """The known-flag walk must descend past depth one."""
    from shiina_cli.main import _iter_cli_parsers  # local: absent before the fix

    parser, subparsers = cli
    progs = {
        current.prog
        for current in _iter_cli_parsers(parser, subparsers)
        if getattr(current, "prog", None)
    }
    assert "shiina profile create" in progs
    assert len(progs) > 100
