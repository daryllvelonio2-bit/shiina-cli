"""Every registered subcommand must be able to render its own help.

Regression: ``shiina portal`` declared ``description=(... ,)`` — a trailing comma turned the
description into a 1-tuple. ``argparse`` only touches it in ``format_help()``, so the command
worked until ``shiina portal -h`` hit ``re._pattern.sub(' ', <tuple>)`` → ``TypeError``. The
failure was invisible because ``main._parse_cli_args`` had swapped ``sys.stderr`` for a
StringIO and only restored it on ``SystemExit``.

Rendering help for every subparser here covers the whole class, not just ``portal``.
"""

import io

import pytest


@pytest.fixture(scope="module")
def built_parser():
    from shiina_cli.main import _build_cli_parser

    parser, subparsers = _build_cli_parser()
    return parser, subparsers


def _subcommands(subparsers):
    """``subparsers`` is the ``add_subparsers()`` action itself, not a parser."""
    return subparsers.choices.items()


def test_every_subcommand_renders_help(built_parser):
    _, subparsers = built_parser

    broken = []
    for name, subparser in _subcommands(subparsers):
        try:
            subparser.format_help()
        except Exception as exc:  # noqa: BLE001 — collecting the whole class of failures
            broken.append(f"{name}: {type(exc).__name__}: {exc}")

    assert not broken, "subcommands whose help cannot render:\n" + "\n".join(broken)


def test_subcommand_parse_errors_reach_stderr(monkeypatch, capsys):
    """A parse failure must not leave ``sys.stderr`` pointing at a dead buffer.

    ``_parse_cli_args`` suppresses argparse's first-attempt usage dump; that swap has to be
    undone on EVERY exit path or the traceback and all later stderr writes vanish.
    """
    import sys

    from shiina_cli.main import _parse_cli_args, _build_cli_parser

    parser, subparsers = _build_cli_parser()
    real_stderr = sys.stderr

    boom = RuntimeError("boom")
    monkeypatch.setattr(parser, "parse_args", lambda argv: (_ for _ in ()).throw(boom))

    with pytest.raises(RuntimeError):
        _parse_cli_args(parser, subparsers, ["doctor"])

    assert sys.stderr is real_stderr, "sys.stderr was left redirected after a parse failure"
    assert not isinstance(sys.stderr, io.StringIO)
