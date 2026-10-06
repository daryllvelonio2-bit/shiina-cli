"""``shiina design`` subcommand parser."""

from __future__ import annotations

from typing import Callable


def build_design_parser(subparsers, *, cmd_design: Callable) -> None:
    """Attach the ``design`` subcommand to ``subparsers``."""
    design_parser = subparsers.add_parser(
        "design", help="List, switch, inspect and seed TUI designs",
        description="Manage TUI designs — the complete look of the terminal UI "
                    "(colours, glyphs, borders, prompt, animations, structure). "
                    "Files are pure data in ~/.shiina/designs/.")
    design_subparsers = design_parser.add_subparsers(dest="design_command")

    design_subparsers.add_parser("list", help="List available designs")

    design_use = design_subparsers.add_parser("use", help="Switch the active design")
    design_use.add_argument("name", help="Design name")

    design_show = design_subparsers.add_parser(
        "show", help="Print a design as resolved (defaults: the active one)")
    design_show.add_argument("name", nargs="?", help="Design name")

    design_path = design_subparsers.add_parser(
        "path", help="Print the YAML file to edit (defaults: the active design)")
    design_path.add_argument("name", nargs="?", help="Design name")

    design_init = design_subparsers.add_parser(
        "init", help="Copy the shipped designs into ~/.shiina/designs/ for editing")
    design_init.add_argument("--force", action="store_true",
                             help="Overwrite existing files (discards your edits)")

    design_subparsers.add_parser("keys", help="List every configurable key and its allowed values")

    design_parser.set_defaults(func=cmd_design)
