"""``shiina secrets`` subcommand parser."""

from __future__ import annotations

# ``agent.secret_sources.bitwarden._BWS_VERSION`` is the source of truth; the ``install`` help
# text below is the only reason a copy lives here — bump both together. See #86781.
_BWS_VERSION = "2.0.0"


def _arg(name: str, help_text: str, **kwargs) -> tuple:
    """One ``add_argument`` spec for :func:`_register_subcommands`."""
    return name, dict(help=help_text, **kwargs)


def _flag(name: str, help_text: str) -> tuple:
    """A boolean ``store_true`` spec for :func:`_register_subcommands`."""
    return _arg(name, help_text, action="store_true")


def _lazy(module: str, handler: str):
    """Resolve ``module.handler`` on dispatch; the handler module stays unimported at build time."""
    def _run(args):
        import importlib
        return getattr(importlib.import_module(module), handler)(args)
    _run.__name__ = handler          # keeps --help / tracebacks honest
    return _run


def _register_subcommands(parent, dest, commands) -> None:
    """Attach ``(name, help, handler, [arg(...), ...])`` subcommands to ``parent``."""
    sub = parent.add_subparsers(dest=dest)
    for name, help_text, handler, arguments in commands:
        parser = sub.add_parser(name, help=help_text)
        for arg_name, kwargs in arguments:
            parser.add_argument(arg_name, **kwargs)
        parser.set_defaults(func=handler)


def build_secrets_parser(subparsers) -> None:
    """Attach the ``secrets`` subcommand to ``subparsers``."""
    secrets_parser = subparsers.add_parser(
        "secrets", help="Manage external secret sources (Bitwarden, 1Password)",
        description="Pull API keys from an external secret manager at process startup "
            "instead of storing them in ~/.shiina/.env.  Supports Bitwarden "
            "Secrets Manager and 1Password.  See: "
            "https://shiina-agent.nousresearch.com/docs/user-guide/secrets/")
    secrets_subparsers = secrets_parser.add_subparsers(dest="secrets_command")

    secrets_bw = secrets_subparsers.add_parser(
        "bitwarden", aliases=["bw"], help="Bitwarden Secrets Manager integration")

    secrets_op = secrets_subparsers.add_parser(
        "onepassword", aliases=["op", "1password"], help="1Password (op:// references) integration")

    # Handlers resolve at dispatch, so secrets_cli / onepassword_secrets_cli (and the rich +
    # Bitwarden crypto payload they import) are paid only by the command that needs them.
    _register_subcommands(secrets_bw, "secrets_bw_command", (
        ("setup", "Interactive wizard: install bws, store access token, pick project",
         _lazy("shiina_cli.secrets_cli", "cmd_setup"), (
             _arg("--project-id", "Pre-select a project UUID instead of prompting"),
             _arg("--access-token", "Provide the access token non-interactively (will be stored in .env)"),
             _arg("--server-url", (
                 "Bitwarden region / self-hosted endpoint. Examples: "
                 "https://vault.bitwarden.com (US, default), "
                 "https://vault.bitwarden.eu (EU), or your self-hosted URL. "
                 "Skips the interactive region prompt."
             )),
         )),
        ("status", "Show config + binary + token validation status",
         _lazy("shiina_cli.secrets_cli", "cmd_status"), ()),
        ("token", "Rotate the access token: validate a new one and store it in .env",
         _lazy("shiina_cli.secrets_cli", "cmd_token"), (
             _arg("--access-token", "Provide the new token non-interactively (default: masked prompt)"),
             _flag("--no-verify", "Store without probing Bitwarden first (not recommended)"),
         )),
        ("sync", "Fetch secrets now and report what changed",
         _lazy("shiina_cli.secrets_cli", "cmd_sync"), (
             _flag("--apply", "Actually export the secrets into the current shell's env (default: dry-run)"),
         )),
        ("disable", "Turn off the Bitwarden integration",
         _lazy("shiina_cli.secrets_cli", "cmd_disable"), ()),
        ("install", f"Download and verify the pinned bws binary (v{_BWS_VERSION})",
         _lazy("shiina_cli.secrets_cli", "cmd_install"), (
             _flag("--force", "Re-download even if a managed copy already exists"),
         )),
    ))

    _register_subcommands(secrets_op, "secrets_op_command", (
        ("setup", "Verify the op CLI, set account / token env var, and enable",
         _lazy("shiina_cli.onepassword_secrets_cli", "cmd_setup"), (
             _arg("--account", "1Password account shorthand or sign-in address (op --account)"),
             _arg("--token-env", "Env var holding a service-account token (default OP_SERVICE_ACCOUNT_TOKEN)"),
             _arg("--token", "Service-account token to store in .env non-interactively"),
             _arg("--binary-path", "Absolute path to the op binary (skips PATH lookup)"),
         )),
        ("status", "Show config + op binary + references",
         _lazy("shiina_cli.onepassword_secrets_cli", "cmd_status"), ()),
        ("token", "Rotate the service-account token: validate and store it in .env",
         _lazy("shiina_cli.onepassword_secrets_cli", "cmd_token"), (
             _arg("--token", "Provide the new token non-interactively (default: masked prompt)"),
             _flag("--no-verify", "Store without probing 1Password first (not recommended)"),
         )),
        ("set", "Map an env var to an op:// reference",
         _lazy("shiina_cli.onepassword_secrets_cli", "cmd_set"), (
             _arg("env_var", "Environment variable name, e.g. OPENAI_API_KEY"),
             _arg("reference", "1Password reference, e.g. op://Private/OpenAI/api key"),
         )),
        ("remove", "Remove an env-var → reference mapping",
         _lazy("shiina_cli.onepassword_secrets_cli", "cmd_remove"), (
             _arg("env_var", "Environment variable name to unmap"),
         )),
        ("sync", "Resolve references now and report what changed",
         _lazy("shiina_cli.onepassword_secrets_cli", "cmd_sync"), (
             _flag("--apply", "Actually export resolved values into the current shell (default: dry-run)"),
         )),
        ("disable", "Turn off the 1Password integration",
         _lazy("shiina_cli.onepassword_secrets_cli", "cmd_disable"), ()),
    ))

    def _dispatch_secrets(args):  # noqa: ANN001
        sub = getattr(args, "secrets_command", None)
        if sub is None:
            secrets_parser.print_help()
            return 0
        return args.func(args)

    secrets_parser.set_defaults(func=_dispatch_secrets)
