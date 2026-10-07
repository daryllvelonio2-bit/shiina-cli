"""``shiina design`` — list, switch, inspect and seed TUI designs.

A design is the complete look of the TUI and it is pure data: colours, glyphs,
borders, prompt symbol, animations, status-bar fields and the structural
arrangement. Files live in ``~/.shiina/designs/*.yaml``; the shipped built-ins
are ``shiina_cli/designs/`` and ``shiina_cli/designs/README.md`` is the schema.

``init`` seeds the folder so the files are yours to edit. Editing one bumps its
mtime and the gateway's change watcher repaints every live surface within ~a
second — no restart.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from shiina_constants import display_shiina_home

# Every key a design file may set, with the values the renderer accepts. This is
# the machine-readable half of the contract: `design keys` prints it so a human
# or an agent can author a design without reading engine source. Keep in step
# with ui-tui/src/domain/design.ts and shiina_cli/designs/README.md.
_DESIGN_KEYS: tuple[tuple[str, str], ...] = (
    ("name", "must match the filename stem; the id you pass to `design use`"),
    ("description", "free text, shown by `design list`"),
    ("extends", "another design to inherit from (default: the file you copy)"),
    ("dynamic", "true = take the palette live from the desktop scheme (Caelestia)"),
    ("colors.<key>", "palette override: accent, primary, border, text, muted, ok, warn, error, "
                     "tool, thinking, prompt, label, sessionLabel, sessionBorder, shellDollar, "
                     "statusBg, statusFg, statusGood, statusWarn, statusBad, statusCritical, "
                     "selectionBg, completionBg, completionCurrentBg, completionMetaBg, "
                     "completionMetaCurrentBg, diffAdded, diffRemoved, diffAddedWord, "
                     "diffRemovedWord, syntaxString, syntaxNumber, syntaxKeyword, syntaxComment"),
    ("prompt", "composer prompt symbol, e.g. '>' or '\u276f'"),
    ("design.density", "compact | normal | roomy — vertical rhythm"),
    ("design.panel", "single | round | double | bold | none — panel/overlay border; none draws no box"),
    ("design.alert", "single | round | double | bold | none — attention panels (approvals, warnings); "
                     "independent of `panel`, defaults to the built-in 'double'"),
    ("design.rule", "horizontal rule character, e.g. '\u2500' or '\u2501'"),
    ("design.flank", "rule | space | none — what flanks a title/header: a drawn rule, blank air, "
                     "or nothing"),
    ("design.header.case", "upper | lower | none — header label transform"),
    ("design.header.emphasis", "bold | dim | none — header label weight"),
    ("design.header.marker", "chevron | rule | none — what a header is drawn with before its label"),
    ("design.indent.unit", "one nesting level, repeated per depth; '' flattens the tree "
                           "(tool output, subagents, ledger steps)"),
    ("design.indent.stem", "rail drawn inside a level whose branch continues (default '\u2502 ')"),
    ("design.indent.branch", "lead before a non-final child (default '\u251c\u2500 ')"),
    ("design.indent.last", "lead before the final child (default '\u2514\u2500 ')"),
    ("design.spacing.<name>", "overlayPadX, overlayPadY, panelPadX, panelPadY, insetPadX, insetPadY, "
                              "rowGap, sectionGap — override the density scale individually"),
    ("design.glyphs.<name>", "active, alert, barEmpty, barFill, blocked, bullet, busy, cache, chain, check, "
                             "checkboxOff, checkboxOn, chevronClosed, chevronOpen, cross, disclosure, "
                             "dot, dotSeparator, ellipsis, focus, halt, idle, latency, off, partial, pending, "
                             "progress, railElbow, railTee, railVertical, resume, rulerTick, scrollThumb, "
                             "selected, separator, statusHead, timeout, tps, waiting, warn"),
    ("design.status_bar.segments", "list of status fields, or null for the built-in order"),
    ("spinner.think", "animation names, e.g. [dna, helix, snake]"),
    ("spinner.tool", "animation names, e.g. [rain, columns, fillsweep]"),
    ("layout.regions.<name>", "boolean region override: rails, dock, pet, statusRule, fileChanges, "
                              "agentsDock, todoUnderPrompt, stickyPrompt, scrollbar, sideColumn, "
                              "ledger"),
    ("layout.sections.<name>", "hidden | collapsed | live | expanded for thinking, tools, subagents, "
                               "activity (live = open during the turn, folds to one row when it settles)")
)


def _active_design() -> str:
    from shiina_cli.config import load_config
    display = (load_config() or {}).get("display") or {}
    return str(display.get("design") or "default")


def _use(name: str) -> None:
    """Activate a design (persists display.design via the shared config writer)."""
    from shiina_cli.config import config_command
    config_command(argparse.Namespace(config_command="set", key="display.design", value=name, force=True))


def _design_list() -> int:
    from shiina_cli.design_engine import list_designs
    active = _active_design()
    for entry in list_designs():
        mark = "*" if entry["name"] == active else " "
        print(f"{mark} {entry['name']:<12} {entry.get('source', ''):<8} {entry.get('description', '')}")
    return 0


def _design_show(name: str | None) -> int:
    import json
    from shiina_cli.design_engine import load_design
    design = load_design(name or _active_design())
    print(f"design   : {design.name}")
    print(f"file     : {design.path or '(built-in)'}")
    print(f"source   : {design.source or 'builtin'}")
    print(f"dynamic  : {design.dynamic}")
    print(f"empty    : {design.is_empty()}  (true = the built-in look; changes nothing)")
    print(f"prompt   : {design.prompt!r}")
    print(f"colors   : {len(design.colors)}")
    print(f"spinner  : {design.spinner or '{}'}")
    print(f"layout   : {design.layout or '{}'}")
    print("payload  :")
    print(json.dumps(design.to_payload(), indent=2, sort_keys=True)[:4000])
    return 0


def _design_path(name: str | None) -> int:
    """Print the file to edit — the user's copy when seeded, else the built-in."""
    from shiina_cli.design_engine import _builtin_designs_dir, _designs_dir, _find_file
    target = name or _active_design()
    path, source = _find_file(target)
    if path is None:
        print(f"{_designs_dir() / f'{target}.yaml'}  (not found; `shiina design init` seeds the built-ins)",
              file=sys.stderr)
        return 1
    print(path)
    if source == "builtin":
        print(f"# built-in — `shiina design init` copies it to {_designs_dir()} for editing",
              file=sys.stderr)
    return 0


def _design_init(overwrite: bool) -> int:
    from shiina_cli.design_engine import ensure_designs_dir
    result = ensure_designs_dir(overwrite=overwrite)
    target = f"{display_shiina_home()}/designs"
    written, kept, unchanged = result["written"], result["kept"], result["unchanged"]

    if written:
        print(f"✓ seeded/upgraded {', '.join(written)} in {target}")
    if kept:
        # Only possible when the file differs from what we seeded — i.e. the user
        # edited it. Never clobber silently.
        print(f"• kept your edits to {', '.join(kept)} (use --force to discard them)")
    if unchanged and not written and not kept:
        print(f"✓ {target} already up to date")
    return 0


def _design_keys() -> int:
    print("Design file keys (also documented in shiina_cli/designs/README.md):\n")
    width = max(len(k) for k, _ in _DESIGN_KEYS)
    for key, doc in _DESIGN_KEYS:
        print(f"  {key:<{width}}  {doc}")
    print("\nEvery key is optional. Omit one and the built-in value is kept.\n"
          "A design that sets nothing is `default` — the built-in look.")
    return 0


def design_command(args) -> None:
    """Dispatch ``shiina design <verb>``."""
    verb = getattr(args, "design_command", None)
    if verb == "use":
        _use(args.name)
        print(f"✓ active design → {args.name} (live within ~1s)")
    elif verb == "show":
        sys.exit(_design_show(getattr(args, "name", None)))
    elif verb == "path":
        sys.exit(_design_path(getattr(args, "name", None)))
    elif verb == "init":
        sys.exit(_design_init(bool(getattr(args, "force", False))))
    elif verb == "keys":
        sys.exit(_design_keys())
    else:  # list / default
        sys.exit(_design_list())
