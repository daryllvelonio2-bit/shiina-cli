# Shiina CLI

Your terminal AI agent — chat, code, automate, and run scheduled jobs, right from the command line. Stays updated by itself.

## Install

Copy-paste this into your terminal:

```bash
git clone --depth 1 https://github.com/daryllvelonio2-bit/shiina-cli.git ~/.shiina/shiina-agent \
  && cd ~/.shiina/shiina-agent \
  && bash scripts/install.sh
```

What this does: clones the CLI into `~/.shiina/shiina-agent`, sets up Python + dependencies, puts the `shiina` command on your PATH, and walks you through the setup wizard (model/API key).

Requirements: `git`, `curl`, Python 3.11+. The installer handles the rest (venv, Node, skills).

After install, restart your shell (or run `exec $SHELL -l`), then:

```bash
shiina
```

## Everyday use

```bash
shiina                  # interactive chat
shiina -q "summarize this repo"   # one-shot answer
shiina --version        # version + update status
shiina update           # manual update (also runs itself automatically)
shiina config set updates.auto_update false   # opt out of auto-updates
shiina cron add "every morning 9am" "send me a briefing"  # scheduled jobs
```

## Auto-updates

This CLI keeps itself current: once a day, when it spots new commits on first launch, it updates in the background and logs to `~/.shiina/logs/auto_update.log`. Just restart `shiina` to run the new code. Turn it off with:

```bash
shiina config set updates.auto_update false
```

## Uninstall

```bash
shiina uninstall --yes
```
