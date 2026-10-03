"""The subparser-builder table and the built tree agree; single builds route their target.

``_CLI_SUBPARSER_BUILDERS`` is the ordered source of the ``shiina --help`` tree and
``_SUBPARSER_BUILDER_BY_NAME`` maps every canonical name and alias to its builder.
Drift between the table and the tree (a name in one but not the other — ``help`` is
intentionally tree-only) would make the single-build path raise ``KeyError`` or
silently skip a command, so the parity is pinned here. ``_build_cli_parser(name)``
builds only that entry's subparser (top level + chat + the target) — the wiring
``main()`` uses to skip the other ~73 builds.
"""

from __future__ import annotations

import pytest

import shiina_cli.main as main_module
from shiina_cli.main import (
    _SUBPARSER_BUILDER_BY_NAME,
    _build_cli_parser,
    _parse_cli_args,
)


@pytest.fixture(scope="module")
def full_tree():
    """The FULL tree, with plugin CLI discovery patched off.

    The real full build calls ``_register_plugin_cli_commands``, which is a no-op
    only when discovery is not needed; un-patched it adds plugin commands to
    ``choices`` and would break the parity assertion.
    """
    mp = pytest.MonkeyPatch()
    mp.setattr(main_module, "_plugin_cli_discovery_needed", lambda: False)
    parser, subparsers = _build_cli_parser()
    yield parser, subparsers
    mp.undo()


def test_table_keys_equal_built_tree_choices(full_tree):
    """Anti-drift: every table name is in the tree, every tree name is in the table."""
    _parser, subparsers = full_tree
    tree_names = set(subparsers.choices)
    assert tree_names, "expected the built tree to register subcommands"
    assert set(_SUBPARSER_BUILDER_BY_NAME) == tree_names


def _routing_argv(name):
    # `import` requires its ``zipfile`` positional; every other subparser routes bare.
    return [name] + (["x"] if name == "import" else [])


@pytest.mark.parametrize("name", sorted(_SUBPARSER_BUILDER_BY_NAME))
def test_single_build_contains_chat_and_the_target(name):
    """A single build registers exactly chat + that entry's names, and routes the name.

    Aliases are table ``names`` keys, and argparse sets ``dest`` to the literal
    typed — so ``gui``/``learning``/``memory-graph`` route under their own name.
    """
    entry_names = {
        n
        for n, builder in _SUBPARSER_BUILDER_BY_NAME.items()
        if builder is _SUBPARSER_BUILDER_BY_NAME[name]
    }
    parser, subparsers = _build_cli_parser(name)
    assert set(subparsers.choices) == {"chat", *entry_names}

    args = _parse_cli_args(parser, subparsers, _routing_argv(name))
    assert getattr(args, "command", None) == name
