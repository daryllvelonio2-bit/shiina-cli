"""``shiina egress`` subcommand: parser + lazy dispatch into ``proxy_cli``.

``build_egress_parser`` runs on EVERY ``shiina`` start (part of the argparse
tree), so it must not import ``proxy_cli`` (rich + iron-proxy chain, ~0.4s of
every startup). The tree is declared as plain data HERE; the handlers resolve
lazily from ``proxy_cli`` at dispatch time.
"""

from __future__ import annotations

import argparse

# Copies of the two iron-proxy constants the help text embeds — kept in sync
# with agent/proxy_sources/iron_proxy.py (its tests assert equality).
_IRON_PROXY_VERSION = "0.39.0"
_DEFAULT_TUNNEL_PORT = 9090


def build_egress_parser(subparsers) -> None:
    """Attach the ``egress`` subcommand to ``subparsers``."""
    # OUTBOUND egress firewall (iron-proxy); `shiina proxy` is the separate INBOUND
    # OAuth-aggregator reverse proxy.
    egress_parser = subparsers.add_parser(
        "egress", help="Manage the iron-proxy egress credential-injection firewall",
        description="Manage iron-proxy, the optional TLS-intercepting egress firewall "
            "that swaps proxy tokens for real API credentials before outbound "
            "requests leave a sandbox.  Disabled by default.  See: "
            "https://shiina-agent.nousresearch.com/docs/user-guide/egress/iron-proxy")
    egress_parser.set_defaults(func=_dispatch_egress, _egress_parser=egress_parser)

    sub = egress_parser.add_subparsers(dest="egress_command")
    # (name, help, handler attr name on shiina_cli.proxy_cli, [(flag, kwargs), ...]) —
    # declaration order is the ``--help`` order, so keep it stable.
    commands = [
        ("install", f"Download iron-proxy binary (v{_IRON_PROXY_VERSION})", "cmd_install", [
            ("--force", dict(action="store_true", help="Re-download even if a managed copy already exists")),
        ]),
        ("setup", "Interactive wizard: install + CA + mint tokens + write config", "cmd_setup", [
            ("--tunnel-port", dict(type=int, default=None,
                                   help=f"Override the tunnel port (default {_DEFAULT_TUNNEL_PORT})")),
            ("--from-bitwarden", dict(action="store_true", help=(
                "Treat secrets as managed by Bitwarden — discover provider keys "
                "from secrets.bitwarden config instead of the current env.  Fails "
                "loudly if BW is unreachable rather than silently falling back."))),
            ("--no-bitwarden", dict(action="store_true", help=(
                "Explicitly switch credential_source back to env on re-setup "
                "(only meaningful when the previous setup used --from-bitwarden)."))),
            ("--rotate-tokens", dict(action="store_true", help=(
                "Mint fresh proxy tokens for every provider (default is to "
                "preserve tokens for providers that already had one — avoids "
                "401-ing already-running sandboxes on re-setup)."))),
            ("--restart", dict(dest="restart", action="store_true", default=None, help=(
                "If a daemon is already running, restart it automatically after "
                "writing the new config/tokens (non-interactive default on a tty is to ask)."))),
            ("--no-restart", dict(dest="restart", action="store_false", help=(
                "Do not restart a running daemon after setup; you'll need to run "
                "`shiina egress restart` yourself for changes to take effect."))),
        ]),
        ("start", "Start the managed iron-proxy", "cmd_start", []),
        ("stop", "Stop the managed iron-proxy", "cmd_stop", []),
        ("restart", "Restart the managed iron-proxy (stop if running, then start)", "cmd_restart", []),
        ("reload", "Hot-reload the running daemon's ruleset from proxy.yaml "
                   "(management API — no restart, no dropped connections)", "cmd_reload", []),
        ("status", "Show proxy state and mappings", "cmd_status", [
            ("--show-tokens", dict(action="store_true", help=(
                "Print the proxy tokens (default: redacted prefix only). "
                "Beware: tokens may persist in your shell history."))),
        ]),
        ("disable", "Turn off the proxy integration", "cmd_disable", []),
        ("config", "Print the generated proxy.yaml path", "cmd_config", []),
    ]
    for name, help_text, handler_attr, arguments in commands:
        parser = sub.add_parser(name, help=help_text)
        for flag, kwargs in arguments:
            parser.add_argument(flag, **kwargs)
        parser.set_defaults(func=_proxy_handler(handler_attr), _egress_parser=egress_parser)


def _proxy_handler(attr: str):
    """Resolve ``proxy_cli.<attr>`` lazily; monkeypatching ``proxy_cli.<attr>`` keeps working."""

    def handler(args: argparse.Namespace):
        from shiina_cli import proxy_cli  # first real import: at dispatch time only
        return getattr(proxy_cli, attr)(args)

    handler.__name__ = handler.__qualname__ = attr
    return handler


def _dispatch_egress(args):  # noqa: ANN001
    # dest='egress_command' stays disjoint from ``shiina proxy`` (dest='proxy_command').
    sub = getattr(args, "egress_command", None)
    if sub is not None and hasattr(args, "func") and args.func is not _dispatch_egress:
        return args.func(args)
    egress_parser = getattr(args, "_egress_parser", None)
    if egress_parser is not None:
        egress_parser.print_help()
    return 0
