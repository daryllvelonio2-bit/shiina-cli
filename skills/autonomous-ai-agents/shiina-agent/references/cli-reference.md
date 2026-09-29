# Shiina CLI Reference

Live sources when anything looks stale: `shiina --help`, `shiina <command> --help`,
https://shiina-agent.nousresearch.com/docs/reference/cli-commands

### Global Flags

```
shiina [flags] [command]        (no subcommand = interactive chat)

  --version, -V             Show version
  -z, --oneshot PROMPT      One-shot: print ONLY the final response (for scripts/pipes)
  -m MODEL  --provider P    Model/provider override for this invocation
  -t, --toolsets LIST       Comma-separated toolsets for this invocation
  --resume, -r SESSION      Resume session by ID or title
  --continue, -c [NAME]     Resume by name, or most recent session
  --worktree, -w            Isolated git worktree mode (parallel agents)
  --skills, -s SKILL        Preload skills (comma-separate or repeat)
  --profile, -p NAME        Use a named profile
  --yolo                    Skip dangerous command approval
  --tui / --cli             Force the Ink TUI / classic REPL
  --ignore-rules            Skip AGENTS.md/SOUL.md/memory/skill injection
  --safe-mode               Disable ALL customizations (troubleshooting)
  --pass-session-id         Include session ID in system prompt
```

### Chat

```
shiina chat [flags]
  -q, --query TEXT          Single query, non-interactive
  --image PATH              Attach a local image to a single query
  -Q, --quiet               Suppress banner, spinner, tool previews
  --checkpoints             Enable filesystem checkpoints (/rollback)
  --max-turns N             Cap tool-calling iterations
  --source TAG              Session source tag (default: cli)
```
(plus the global flags above)

### Configuration

```
shiina setup [section]      Wizard (model|tts|terminal|gateway|tools|agent)
shiina model                Interactive model/provider picker
shiina fallback [add|remove|list]  Fallback provider chain
shiina config [show|edit|get|set|unset|path|env-path|check|migrate]
shiina login / logout       OAuth sign-in / clear stored auth
shiina doctor [--fix]       Check dependencies and config
shiina status [--all]       Component status
```

### Tools & Skills

```
shiina tools [list|enable NAME|disable NAME]   Per-platform toolsets (curses UI with no args)

shiina skills list|browse|search QUERY|inspect ID
shiina skills install ID    Hub identifier OR a direct https://…/SKILL.md URL
shiina skills config        Enable/disable skills per platform
shiina skills check|update|uninstall|publish PATH
shiina skills tap add REPO  Add a GitHub repo as a skill source
shiina bundles              Skill bundles (one /<name> alias loads several skills)
```

### MCP Servers

```
shiina mcp add NAME (--url or --command) | remove | list | test NAME
shiina mcp catalog | install NAME     Curated catalog install
shiina mcp configure NAME             Toggle tool selection
shiina mcp serve                      Run Shiina as an MCP server
```
Details (transport, tool discovery, catalog): `references/native-mcp.md`.

### Gateway (Messaging Platforms)

```
shiina gateway run|install|start|stop|restart|status|setup
```

20+ platforms: Telegram, Discord, Slack, WhatsApp (Baileys + Business Cloud API), iMessage (Photon — `shiina photon setup`), Signal, Email, SMS, Matrix, Mattermost, Teams, LINE, SimpleX, ntfy, Google Chat, Home Assistant, DingTalk, Feishu, WeCom, Weixin, API Server, Webhooks. Open WebUI connects via the API Server adapter. Most adapters ship under `plugins/platforms/`.
Docs: https://shiina-agent.nousresearch.com/docs/user-guide/messaging/

### Sessions

```
shiina sessions list|browse|rename ID TITLE|delete ID|export OUT|prune|stats
```

### Cron / Webhooks

```
shiina cron list|create SCHED|edit ID|pause|resume|run ID|remove|status
    Schedules: '30m', 'every 2h', '0 9 * * *', ISO timestamp
shiina webhook subscribe NAME|list|remove NAME|test NAME
```
Webhook payloads/routes: `references/webhooks.md`.

### Profiles

```
shiina profile list|create NAME (--clone|--clone-all|--clone-from)|use|show|delete
shiina profile rename A B | alias NAME | export NAME | import FILE
shiina profile migrate-identity A B   Retry a completed rename's session/routing identity migration
```

### Credentials & Pools

```
shiina auth                 Interactive credential manager
shiina auth add [PROVIDER]  Add OAuth or API-key credential (nous, openai-codex, qwen-oauth, …)
shiina auth list|remove P IDX|reset PROVIDER|status
```
Multiple credentials per provider form a pool that rotates automatically and skips exhausted keys.

### Other

```
shiina desktop / gui        Native desktop app
shiina dashboard            Web admin panel + embedded chat (--stop / --status)
shiina proxy                OpenAI-compatible local proxy backed by an OAuth provider
shiina portal               Quick setup / sign in via Nous Portal
shiina kanban <verb>        Multi-agent work-queue board
shiina project              Named multi-folder workspaces
shiina skin list|use|set    Switch/tweak skins (see references/themes.md)
shiina pets <verb>          Pet mascots (see references/petdex.md)
shiina memory setup|status|off|reset   Memory provider
shiina secrets bitwarden|onepassword   External secret stores
shiina moa                  Mixture-of-Agents slots
shiina hooks / security / backup / import / checkpoints / console
shiina logs [-f] [errors]   View agent/error logs
shiina send                 One-off message through a gateway platform
shiina pairing / plugins / insights / journey / computer-use
shiina acp                  ACP server (IDE integration)
shiina completion bash|zsh|fish
shiina update / uninstall / claw migrate
```

Plugin- and provider-supplied subcommands (e.g. `shiina photon setup`) only appear once their plugin is installed/active.

### Where to Find Things

| Looking for... | Location |
|---|---|
| Config options | `shiina config edit` · [Configuration docs](https://shiina-agent.nousresearch.com/docs/user-guide/configuration) |
| Tools / toolsets | `shiina tools list` · [Tools reference](https://shiina-agent.nousresearch.com/docs/reference/tools-reference) |
| Skills catalog | `shiina skills browse` · [Skills catalog](https://shiina-agent.nousresearch.com/docs/reference/skills-catalog) |
| Provider setup | `shiina model` · [Providers guide](https://shiina-agent.nousresearch.com/docs/integrations/providers) |
| Env variables | `shiina config env-path` · [Env vars reference](https://shiina-agent.nousresearch.com/docs/reference/environment-variables) |
| Gateway logs | `~/.shiina/logs/gateway.log` (or `shiina logs`) |
| Sessions | `shiina sessions browse` (reads state.db) |
