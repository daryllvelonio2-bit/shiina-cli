"""The subparser-builder table and the built tree agree; single builds route their target.

``_CLI_SUBPARSER_BUILDERS`` is the ordered source of the ``shiina --help`` tree and
``_SUBPARSER_BUILDER_BY_NAME`` maps every canonical name and alias to its builder.
Drift between the table and the tree (a name in one but not the other — ``help`` is
intentionally tree-only) would make the single-build path raise ``KeyError`` or
silently skip a command, so the parity is pinned here. ``_build_cli_parser(name)``
builds only that entry's subparser (top level + chat + the target) — the wiring
``main()`` uses to skip the other ~73 builds.

The s3 section pins ``main()``'s path selection: ``_single_build_target`` resolves the one
command to build in isolation (everything else defers to the full build), and
``_build_tree_for_argv`` adds the post-build rewrite guard. Every expected target/exit
below is the FULL build's outcome on the current tree, so these pins are red on a
resolver that defers too little and green on one that defers too much — a deferral can
only forgo a speedup, never change a parse.
"""

from __future__ import annotations

import sys

import pytest

import shiina_cli.main as main_module
from shiina_cli.main import (
    _SUBPARSER_BUILDER_BY_NAME,
    _build_cli_parser,
    _build_tree_for_argv,
    _parse_cli_args,
    _rewrite_named_session_flags,
    _single_build_target,
)

# The REAL ``_plugin_cli_discovery_needed``, captured at import time — before the
# ``full_tree`` fixture patches it — so test_plugin_discovery_still_needed_for_scan
# can restore it despite the module-scoped patch still being active.
_REAL_PLUGIN_DISCOVERY = main_module._plugin_cli_discovery_needed


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


@pytest.fixture(scope="module")
def single_trees(full_tree):
    """Every target's single build, built ONCE and shared by the parity sweeps.

    ``_build_cli_parser(name)`` is ~50 ms on a loaded box; rebuilding the 74 singles
    per parametrized instance was pure waste (the trees are read-only for the parse).
    """
    _full_p, full_s = full_tree
    return {name: _build_cli_parser(name) for name in full_s.choices}


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


# ---------------------------------------------------------------------------
# s3: single-subparser construction in main() — path selection and parity.
#
# Every FULL-tree parse here runs on the ``full_tree`` fixture's module-level
# discovery patch. ``_build_tree_for_argv`` builds real trees, but never a full
# one for the argv below (the resolver defers those), so the patch is not
# required for it.
# ---------------------------------------------------------------------------


def _outcome(P, S, argv):
    try:
        return ("ok", getattr(_parse_cli_args(P, S, argv), "command", None))
    except SystemExit as exc:
        return ("exit", exc.code)


@pytest.mark.parametrize(
    "argv, expected",
    [
        (["logs", "--help"], "logs"),
        (["--help", "logs"], None),  # top-level help lists all 74
        (["-c", "logs"], None),  # session named `logs` → chat
        (["completion", "bash"], None),  # completion introspects the whole tree
        (["scan"], None),  # plugin discovery is needed for `scan` today
        (["photon", "--help"], None),  # plugin/unknown token
        (["gui", "--help"], "gui"),  # aliases route under their own name
        (["learning", "--help"], "learning"),
        (["--blank", "logs"], None),  # not a top-level option: SystemExit(2) today —
        (["--force", "logs"], None),  # the single build must not rewrite and RUN
        (["--json", "logs"], None),
        (["--project-id", "x", "logs"], None),
        (["--reasoning", "high", "logs"], "logs"),  # defined top-level value flags
        (["--tui", "logs"], "logs"),
        (["chat"], None),  # chat always defers: its subparser defines `--resume`, so
        (["chat", "--tui"], None),  # a single-built chat tree rewrites the post-positional
        (["chat", "--force"], None),  # flag and RUNS where the full build exits 2
        (["chat", "--json"], None),
        (["-c", "x", "logs"], None),  # every session-name flag defers —
        (["-r", "x", "logs"], None),  # `_coalesce_session_name_args` reshapes argv around
        (["--continue", "x", "logs"], None),  # them and the rewrite guard cannot fire
        (["--resume", "x", "logs"], None),
        (["-c", "x", "kanban", "acp"], None),  # r4 counterexamples: the r3 resolver
        (["-r", "pets", "egress", "plugins"], None),  # returned kanban/egress/resume and
        (["--resume", "y", "resume", "--tui", "update"], None),  # exited 2 where the full tree routes
    ],
)
def test_single_build_target(argv, expected):
    assert _single_build_target(argv) == expected


def test_session_flag_argv_routes_on_the_full_tree(full_tree):
    """The r4 counterexample, end-to-end: `-c x kanban acp` → command == "acp".

    A single-built kanban tree exits 2 here (session flags are the rewrite
    guard's blind spot), so this pin only holds on the full tree the resolver
    now defers to.
    """
    full_p, full_s = full_tree
    args = _parse_cli_args(full_p, full_s, ["-c", "x", "kanban", "acp"])
    assert args.command == "acp"


def test_malformed_pre_positional_flag_still_exits_2(full_tree):
    """`--blank logs` must exit 2 — the exact behaviour a single build would break."""
    full_p, full_s = full_tree
    with pytest.raises(SystemExit) as excinfo:
        _parse_cli_args(full_p, full_s, ["--blank", "logs"])
    assert excinfo.value.code == 2


def test_chat_post_positional_flag_still_exits_2(full_tree):
    """`chat --force` must exit 2 on the full tree (single-built chat would run it)."""
    full_p, full_s = full_tree
    with pytest.raises(SystemExit) as excinfo:
        _parse_cli_args(full_p, full_s, ["chat", "--force"])
    assert excinfo.value.code == 2


@pytest.mark.parametrize(
    "argv",
    [
        ["-c", "x", "kanban", "acp"],
        ["-r", "pets", "egress", "plugins"],
        ["--resume", "y", "resume", "--tui", "update"],
    ],
)
def test_build_tree_for_argv_defers_session_flag_counterexamples(full_tree, argv):
    """``_build_tree_for_argv`` hands the r4 counterexamples to the full build."""
    full_p, full_s = full_tree
    eff_p, eff_s = _build_tree_for_argv(argv)
    # `_build_cli_parser()` is NOT memoized, so `eff_p is full_p` is False even on a
    # correct guard-fire; the 74-key choice set is the identity-free discriminator.
    assert set(eff_s.choices) == set(full_s.choices), argv
    assert _outcome(eff_p, eff_s, argv) == _outcome(full_p, full_s, argv), argv


ABBREV = [
    ("desktop", "--force"),
    ("gui", "--force"),
    ("journey", "--force"),
    ("learning", "--force"),
    ("memory-graph", "--force"),
    ("desktop", "--setup"),
    ("gui", "--skip"),
    ("dashboard", "--skip"),
    ("serve", "--skip"),
    ("verify", "--skip"),
    ("model", "--ref"),
    ("setup", "--port"),
    ("update", "--keep"),
    ("update", "--switch"),
    ("desktop", "--skip"),
    ("gui", "--setup"),
]


@pytest.mark.parametrize("target, flag", ABBREV)
def test_effective_tree_defers_post_positional_rewrites(full_tree, target, flag):
    """The measured argparse-abbreviation argv: the effective tree is the full tree.

    The resolver only admits pre-positional top-level options, so a single
    build can only rewrite a POST-positional token whose option string lives
    elsewhere in the full tree — exactly these 16 measured argv, where the
    full build's argparse accepts an abbreviation of a target-subtree option
    that the single build would instead rewrite into `--resume <token>`.
    """
    full_p, full_s = full_tree
    argv = [target, flag]
    eff_p, eff_s = _build_tree_for_argv(argv)
    assert set(eff_s.choices) == set(full_s.choices), "guard must hand this argv to the full build"
    assert _outcome(eff_p, eff_s, argv) == _outcome(full_p, full_s, argv), argv


@pytest.mark.parametrize("flag", ["--force", "--setup", "--skip", "--ref", "--port", "--keep", "--switch"])
def test_no_target_changes_outcome_for_foreign_flags(full_tree, single_trees, flag):
    """74 targets × the colliding flags: same outcome as the full build (518 parses).

    The effective tree is ``_build_tree_for_argv``'s decision, replayed against one
    prebuilt full tree and the singles — the same shape as
    ``test_resolver_sweep_reproduces_the_full_outcome``. Calling the real builder here
    would re-build the FULL tree on every guard fire (493/518 argv × ~1.4 s), which
    adds no coverage: the resolver+guard decision is deterministic and already pinned
    by the sweep. Same 518 argv, same outcome-parity assertion.
    """
    full_p, full_s = full_tree
    singles = single_trees
    for target in _SUBPARSER_BUILDER_BY_NAME:
        argv = [target, flag]
        if _single_build_target(argv) is None:
            continue  # deferred → the full build is the authority by construction
        sp, ss = singles[target]
        if _rewrite_named_session_flags(argv, sp, ss)[1]:
            continue  # guard fires → effective tree IS the full build → trivially equal
        assert _outcome(sp, ss, argv) == _outcome(full_p, full_s, argv), argv


def test_guard_preserves_single_build_for_the_metric_path():
    """`logs --help` keeps the single build — the guard must not fire on the metric path."""
    eff_p, eff_s = _build_tree_for_argv(["logs", "--help"])
    assert sorted(eff_s.choices) == ["chat", "logs"]


SESSION = ["-c", "-r", "--continue", "--resume"]


def test_session_name_argv_always_defers():
    """The r4 session-name sweep: every target × session flag × foreign command defers.

    The plan's per-assert full-build parity loop is bounded here to the resolver —
    which covers every argv in this class, load-independently, with zero tree
    builds — plus the effective-tree parity of the measured counterexample rows
    (test_build_tree_for_argv_defers_session_flag_counterexamples). Same
    coverage; ~6 min of redundant full builds per parametrized instance saved.
    """
    for s_flag in SESSION:
        for target in _SUBPARSER_BUILDER_BY_NAME:
            for foreign in ("acp", "logs", "backup", "plugins", "update", "status", "egress"):
                if foreign == target:
                    continue
                for argv in (
                    [s_flag, "x", target, foreign],
                    [target, s_flag, "x", foreign],
                    [s_flag, foreign, target],
                ):
                    assert _single_build_target(argv) is None, argv


def test_resolver_sweep_reproduces_the_full_outcome(full_tree, single_trees):
    """Every argv the resolver admits (all 74 targets × every eligible long flag)
    reproduces the FULL build's parse outcome — 0 divergences, no timing.

    The argv carry no session-name flag (that class is deferral-only, swept by
    test_session_name_argv_always_defers). The sweep shape mirrors the plan's
    C4c: single builds are prebuilt once per target, the effective tree of a
    rewrite fires the guard to the full build, and the FULL outcome comes from
    the shared full tree — ~26,640 argv, no timing.

    A guard-fire argv's effective tree IS the full build, so its parity check
    (``_outcome(full) == _outcome(full)``) is trivially true and is skipped;
    only the rows that actually parse the single build are compared. Without
    that skip this one test spent minutes re-parsing the full tree against
    itself (~95% of the 26,640 argv fire the guard).
    """
    full_p, full_s = full_tree
    opts = set()
    for p in main_module._iter_cli_parsers(full_p, full_s):
        for a in getattr(p, "_actions", []):
            opts.update(
                o
                for o in a.option_strings
                if o.startswith("--")
                and len(o) > 2
                and "=" not in o
                and not o.startswith("--no-")
                and not o.startswith("--print-")
                and o not in ("--resume", "--continue")
            )
    singles = single_trees
    bad = []
    for target in sorted(full_s.choices):
        sp, ss = singles[target]
        for opt in sorted(opts):
            argv = [target, opt]
            if _single_build_target(argv) is None:
                continue  # deferred → the full build is the authority by construction
            if _rewrite_named_session_flags(argv, sp, ss)[1]:
                continue  # guard fires → effective tree IS the full build → trivially equal
            if _outcome(sp, ss, argv) != _outcome(full_p, full_s, argv):
                bad.append(argv)
    assert not bad, f"single/effective build diverges from FULL: {bad}"


def test_plugin_discovery_still_needed_for_scan():
    """The `scan` deferral preserves the discovery path, not just the parser.

    The module-scoped ``full_tree`` patch on ``_plugin_cli_discovery_needed`` is
    still active here (fixture teardown is at module end), so restore the REAL
    function — captured at import time, before any fixture patch — for this
    assertion, then undo.
    """
    mp = pytest.MonkeyPatch()
    mp.setattr(main_module, "_plugin_cli_discovery_needed", _REAL_PLUGIN_DISCOVERY)
    try:
        sys.argv = ["shiina", "scan"]
        assert main_module._plugin_cli_discovery_needed() is True
    finally:
        mp.undo()


def test_nested_flags_are_never_mistaken_for_session_names_on_single_tree():
    """The single-built profile parser still leaves nested flags alone."""
    parser, subparsers = _build_cli_parser("profile")
    argv, rewritten = _rewrite_named_session_flags(
        ["profile", "create", "x", "--blank"], parser, subparsers
    )
    assert argv == ["profile", "create", "x", "--blank"]
    assert rewritten is False
