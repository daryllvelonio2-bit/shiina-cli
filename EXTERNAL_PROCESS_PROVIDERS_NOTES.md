# External-Process Providers — Where Things Live, and What Was Fixed

Working notes for the local-subprocess ("external process") providers that drive an
installed agent CLI: **kiro**, **antigravity**, **freebuff**, **opencode-cli**, and
**copilot-acp**. These providers do NOT talk to an HTTP endpoint; they shell out to a
binary the user already has installed and logged in.

Keep this file append-friendly — add new sections as more of these providers get fixed.

Last updated: 2026-09-30

---

## 1. The mental model (read this first)

An external-process provider resolves through a **ladder** in
`shiina_cli/runtime_provider.py::_ladder_rungs`. Each rung yields a runtime dict
(`provider`, `api_mode`, `base_url`, `api_key`, `command`, `args`, `source`) or nothing;
the first non-empty rung wins.

Order (matters — the bug was an ordering/fallback problem):

```
0  requested shortcuts (moa, azure-foundry, vertex)
1  named custom provider / llamacpp alias
2  local-endpoint bypass
3  explicit --api-key / --base-url
4  credential pool            <-- _resolve_from_pool   (shipped HERE, above rung 6)
5  OAuth runtime (nous/codex/xai/qwen, minimax-oauth)
6  EXTERNAL PROCESS           <-- _resolve_external_process_runtime  (supplies ://local + command)
7  anthropic env / bedrock / registry api_key providers
8  OpenRouter / bare-custom fallback
```

Key consequence: a **credential-pool entry can short-circuit the external-process rung.**
If the pool yields a runtime, rung 6 never runs and its `command`/`base_url` are lost.

The whole ladder is verified with:

```bash
cd /home/janelle/Downloads/shiina
.venv/bin/python -c "
from shiina_cli import runtime_provider as rp
for i, r in enumerate(rp._ladder_rungs('kiro', None, None, 'qwen3-coder-next')):
    if r: print(i, r.get('provider'), repr(r.get('base_url')), r.get('source'))
    else: print(i, 'EMPTY')
"
```

---

## 2. Where each piece lives

| What | File | Symbol / line |
|---|---|---|
| Runtime ladder + pool rung + base_url finalize | `shiina_cli/runtime_provider.py` | `_ladder_rungs` (883), `_resolve_from_pool` (542), `_resolve_runtime_from_pool_entry` (487→), `_pool_entry_mode_and_url` (451), `_finalize_base_url` (349), `_pool_entry_base_url` (333) |
| External-process rung + auth-type probe | `shiina_cli/runtime_provider_backends.py` | `_is_external_process_provider` (225), `_resolve_external_process_runtime` (246) |
| Credential resolution for external processes | `shiina_cli/auth.py` | `resolve_external_process_provider_credentials` (2183), `_external_process_spec` (1993), `_external_process_auth_evidence` (1882) |
| Provider registry (auto-built from plugin profiles) | `shiina_cli/auth.py` | `PROVIDER_REGISTRY` (248), `_register_plugin_provider` (258) |
| Static overlay (transport/auth_type/base_url_override) | `shiina_cli/providers.py` | `SHIINA_OVERLAYS` — kiro (98), antigravity (92), freebuff (118), opencode-cli (124) |
| Aliases | `shiina_cli/providers.py` | `_ALIAS_GROUPS` (153) |
| Display labels | `shiina_cli/providers.py` | `_LABEL_OVERRIDES` (185) |
| **Provider profile (source of truth for base_url/command/args)** | `plugins/model-providers/<name>/__init__.py` | e.g. `plugins/model-providers/kiro/__init__.py` |
| Credential-pool seeding (reads the local CLI's own store) | `agent/credential_pool.py` | `_seed_kiro_singleton` (2527), `_seed_antigravity_singleton` (2492), `_seed_freebuff_singleton` (2513), `_seed_opencode_singleton` (2555) |
| Pool persistence / read | `agent/credential_pool.py` | `load_pool` (2833), `read_credential_pool`, `write_credential_pool` |
| The client that actually shells out | `agent/kiro_client.py` (KiroClient, ~246), `agent/freebuff_client.py`, `agent/antigravity_client.py`, `agent/opencode_client.py` | |

Provider profiles registered under `plugins/model-providers/` get auto-added to
`PROVIDER_REGISTRY` by `_register_plugin_provider`: `auth_type=external_process` providers
carry `inference_base_url = profile.base_url` (e.g. `kiro://local`). So
`PROVIDER_REGISTRY['kiro'].inference_base_url` is the canonical endpoint to fall back to.

---

## 3. The bug that was fixed (kiro, 2026-09-30)

**Symptom** (seen in the CLI after `shiina model` → kiro → chat):

```
⚠️  Provider resolver returned an empty base URL. Check your provider config or run: shiina setup
```

A "Model switched" banner showed `Provider: kiro` right before it.

**Why:** `_seed_kiro_singleton` reads `~/.local/share/kiro-cli/data.sqlite3`
(`auth_kv.kirocli:social:token`) and writes a pool entry with `access_token` +
`refresh_token` but **no `base_url`** (source `sqlite`, label `Kiro (google)`). On the next
resolution the credential-pool rung (rung 4) selected that entry, returned
`provider='kiro'`, `base_url=''` — and the external-process rung (rung 6) that would have
supplied `kiro://local` never ran. Everything downstream then rejected the empty URL.

Same latent bug existed for **antigravity**, **freebuff**, **opencode-cli** — all seed
token-only pool entries from a local store.

**Fix** — `shiina_cli/runtime_provider.py::_pool_entry_mode_and_url`, in the generic tail
(~line 479-490). When a pool entry carries no endpoint, fall back to the provider's
registered `inference_base_url`, then still honour an explicit `model.base_url`:

```python
pconfig = PROVIDER_REGISTRY.get(provider)
if pconfig:
    # A pool entry whose credential carries no endpoint (external-process providers seeded
    # from a local store — kiro, antigravity, freebuff, opencode-cli — have only a token)
    # must fall back to the provider's own base_url, or the runtime is rejected downstream as
    # an empty base URL even though the subprocess endpoint is well known.
    if not base_url.strip():
        base_url = pconfig.inference_base_url
    if base_url.rstrip("/") == pconfig.inference_base_url.rstrip("/"):
        base_url = _config_base_url_for_provider(model_cfg, provider) or base_url
```

Why here and not by reordering the ladder: reordering would break the frontends that
legitimately need the pool token; the endpoint is *known static data* for the provider, so
filling it is the narrow fix and it repairs every sibling provider in one place.

**Test** — `tests/plugins/test_kiro_provider.py::TestKiroProvider::test_pool_entry_without_base_url_keeps_provider_endpoint`
(writes a token-only kiro pool entry via `agent.credential_pool.write_credential_pool`, then
asserts `resolve_runtime_provider(requested='kiro')['base_url'] == 'kiro://local'`).
Proven red on base (`'' != 'kiro://local'`), green with the fix.

Also fixed in the same test file: `test_resolve_runtime_provider` asserted
`rt["source"] == "process"`, which only holds when no Kiro local store exists — it fails for
anyone actually logged into Kiro. Dropped that environment-dependent snapshot; the contract
is `base_url` / `provider`.

---

## 4. How to reproduce / verify (copy-paste)

```bash
cd /home/janelle/Downloads/shiina

# 1. Does the credential pool carry a token-only kiro entry? (no base_url key = the trigger)
.venv/bin/python - <<'PY'
from agent.credential_pool import read_credential_pool
for e in read_credential_pool('kiro'):
    d = dict(e); d.pop('access_token', None); d.pop('refresh_token', None)
    print(d)
PY

# 2. Does the runtime resolve a base_url? (this is the exact thing that broke)
.venv/bin/python -c "
from shiina_cli.runtime_provider import resolve_runtime_provider
rt = resolve_runtime_provider(requested='kiro', target_model='qwen3-coder-next')
print({k: rt.get(k) for k in ('provider','api_mode','base_url','source')})
"

# 3. Sweep every external-process provider at once
.venv/bin/python -c "
from shiina_cli.runtime_provider import resolve_runtime_provider
for p in ('kiro','antigravity','freebuff','opencode-cli','copilot-acp'):
    try:
        rt = resolve_runtime_provider(requested=p, target_model='auto')
        print(f'{p:14} {rt.get(\"base_url\")!r}')
    except Exception as e:
        print(f'{p:14} ERR {type(e).__name__}: {str(e)[:70]}')
"

# 4. True end-to-end: build a real agent and talk to the subprocess
.venv/bin/python - <<'PY'
from shiina_cli.runtime_provider import resolve_runtime_provider
from run_agent import AIAgent
rt = resolve_runtime_provider(requested='kiro', target_model='qwen3-coder-next')
agent = AIAgent(model='qwen3-coder-next', api_key=rt.get('api_key'), base_url=rt.get('base_url'),
                provider=rt.get('provider'), api_mode=rt.get('api_mode'),
                quiet_mode=True, skip_memory=True, skip_context_files=True,
                max_iterations=2, platform='cli', enabled_toolsets=[])
print('REPLY:', agent.chat('Reply with exactly: KIRO_OK'))
PY

# 5. Tests (ALWAYS via the script, never bare pytest)
scripts/run_tests.sh tests/plugins/test_kiro_provider.py
scripts/run_tests.sh tests/shiina_cli/test_external_process_provider_seam.py
```

Expected: step 2/3 print `kiro://local` / `agy://local` / `freebuff://local` /
`opencode://local`; step 4 prints `KIRO_OK`.

---

## 5. Where the real credentials/state live (per host)

These are the on-disk stores the seeders read. Nothing here is written by Shiina.

| Provider | Local store | Notes |
|---|---|---|
| kiro | `~/.local/share/kiro-cli/data.sqlite3` → table `auth_kv`, key `kirocli:social:token` | JSON with `access_token`, `refresh_token`, `provider` |
| antigravity | read via `agent/antigravity_client.py::GoogleOAuthTokenManager` | Google OAuth |
| freebuff | `~/.config/manicode/credentials.json` | via `agent/freebuff_client.get_freebuff_token` |
| opencode-cli | via `agent/opencode_client.get_opencode_credentials` | |
| copilot-acp | `~/.copilot/config.json`, `~/.config/github-copilot/{hosts,apps}.json`, env tokens | |

Binary discovery: `SHIINA_KIRO_COMMAND` / `KIRO_BIN` / `KIRO_CLI_PATH` (kiro),
`AGY_*` (antigravity), `SHIINA_<NAME>_COMMAND` per profile's `process_command_env_vars`,
`process_args_env_var` for args. If the binary isn't found you get
`AuthError: Could not find the '<provider>' CLI command` (code `missing_external_process_cli`).

---

## 6. Diagnosis cheat-sheet

| Symptom | Likely cause | Look at |
|---|---|---|
| `Provider resolver returned an empty base URL` | pool rung returned an entry with no endpoint (this doc §3) | `_pool_entry_mode_and_url` tail; `read_credential_pool(<provider>)` |
| `Unknown provider '<x>'` | profile not registered / typo | `PROVIDER_REGISTRY`, `_register_plugin_provider`, `plugins/model-providers/<x>/` |
| `Could not find the '<x>' CLI command` | binary missing or wrong env var | `_external_process_spec`, provider profile `process_command*` |
| Chat works but no reply / hangs | subprocess invocation wrong | `agent/<x>_client.py` (`_create_chat_completion`), args in profile |
| Provider shows but model switch does nothing | alias/label missing | `_ALIAS_GROUPS`, `_LABEL_OVERRIDES` in `shiina_cli/providers.py` |

---

## 7. Showing these providers in `/usage`, and removing them

Driven by: "after some modification we made, now it doesnt show most of my providers usage"
(2026-10-01). Two problems — local CLIs never appeared in the quota dashboard, and removing one
did not stick.

### 7.1 The dashboard only showed providers with a usage API

`discover_quota_providers` (`shiina_cli/usage_visualizer.py`) only put providers with a
`_USAGE_FETCHERS` entry (or a hand-listed `SUPPORTED_QUOTA_PROVIDERS` name) into the fetch list.
Kiro / OpenCode / freebuff have no quota endpoint, so they fell through to the one dim
"Other connected providers: kiro (3 keys) …" summary line — which reads as "my providers aren't
showing". They also showed up several times because each alias (`kiro-cli`, `kiro-ai`,
`opencode-local`, …) is its own pool entry.

Fix, three parts:

1. **`agent/account_usage.py::_external_process_connected_snapshot`** — when a provider has no
   fetcher, and it is a registered `auth_type="external_process"` provider with auth evidence
   (`_external_process_auth_evidence`), return a snapshot describing the connection
   ("Connected — Kiro SQLite store (google)"). `fetch_account_usage` calls it before returning
   `None`. Title comes from `shiina_cli.providers.get_label`.
2. **`discover_quota_providers`** folds alias variants onto the canonical name via
   `shiina_cli.providers.ALIASES` (a variant with its own fetcher — `xkiro`, `cline` — keeps its
   identity), and adds external-process providers with credentials to the fetch list.
   `other_providers` counts are summed per canonical so the summary reads "qoder (4 keys)".
3. **`_LABEL_OVERRIDES`** gained `"kiro": "Kiro"` so the row is not lowercase.

Still in the summary line (by design): plain `api_key` providers with no usage fetcher —
`qoder` (`https://api2.qoder.sh`, PAT over HTTP), `custom:*`, `openai-api`. Giving every
API-key provider its own row would flood the dashboard for users with many keys.

### 7.2 `shiina auth remove <cli>` did not stick

The pool re-seeds from the CLI's own store on every `load_pool()`, and no
`RemovalStep` was registered for those sources, so `auth_remove_command` returned early
(`find_removal_step` → `None`) and the entry came straight back.

Fix — `agent/credential_sources.py` now registers suppress-only steps for
(freebuff, codebuff, freebuff-cli)→`credentials`, (kiro, kiro-cli, kiro-ai, xkiro)→`sqlite`,
(opencode, opencode-cli, opencode-local, opencode-agent, opencode-bin)→`opencode:*`.
Suppress-only: these stores belong to the CLI (never deleted). Descriptions are
`"{provider}: {backing}"` — the registry tests require unique, non-empty descriptions.

Removing freebuff for real:

```bash
cd /home/janelle/Downloads/shiina
.venv/bin/python shiina auth list freebuff          # find the index
.venv/bin/python shiina auth remove freebuff 1      # prints "Suppressed credentials …"
.venv/bin/python shiina auth remove freebuff-cli 1
.venv/bin/python shiina auth remove codebuff 1
# verify it stays gone (no re-seed):
.venv/bin/python -c "from agent.credential_pool import load_pool; print(len(load_pool('freebuff').entries()))"  # 0
# re-enable: shiina auth add freebuff
```

### 7.3 Tests

- `tests/agent/test_account_usage_fetch.py::test_fetch_account_usage_reports_local_cli_connection`
- `tests/shiina_cli/test_usage_visualizer.py::test_discover_quota_providers_folds_alias_variants`
- `tests/shiina_cli/test_auth_commands.py::test_auth_remove_external_process_cli_suppresses_reseed`

All three proven red on base, green with the fix. Also repaired while here:
`tests/plugins/test_qoder_provider.py::test_resolve_runtime_provider` required an ambient
`QODER_PAT` (failed on a clean checkout for everyone) — now passes an explicit key.

### 7.4 Verify the dashboard end-to-end

```bash
.venv/bin/python - <<'PY'
from shiina_cli.usage_visualizer import discover_quota_providers, fetch_all_provider_usage, build_usage_dashboard
quota, other = discover_quota_providers()
print("fetch:", quota, "| other:", other)
print(build_usage_dashboard(fetch_all_provider_usage(quota), other_providers=other).renderable)
PY
```

Expected rows: **Antigravity** (real quota), **OpenRouter** (credits), **Kiro** and
**OpenCode CLI** (connected, no usage API), with only `custom:*` / `openai-api` / `qoder`
left in the summary line.

---

## 8. Multi-account usage showed the ACTIVE account's quota for every row

Reported: antigravity's two accounts (`daryllvelonio@gmail.com` = 9% left,
`daryllvelonio9@gmail.com` = 1% left) both rendered the same numbers — "it treats the active
account in agy as the only query for usage".

Cause: `agent/account_usage.py::_fetch_antigravity_account_usage` ignored its `api_key`
argument and always called `GoogleOAuthTokenManager().get_access_token()`, which resolves the
ACTIVE `agy` login. `fetch_all_provider_usage` passes each pool entry's own
`entry.access_token`, so the plumbing existed — the fetcher just threw it away. Every row was
therefore the active account's quota.

Fix (three files):

1. `agent/antigravity_client.py` — `GoogleOAuthTokenManager(access_token=, refresh_token=,
   persist=False)` binds the manager to a caller-supplied credential. `persist=False` is
   required: `_save_to_auth_json` writes the single `providers.antigravity` slot, so refreshing
   a NON-active account would clobber the active account's tokens. With an explicit
   `access_token` the expiry starts at `inf` ("trust it until a 401 forces a refresh").
   Also fixed the hardcoded `Path.home()/".shiina"/"auth.json"` → `get_shiina_home()` in both
   `_load_initial_tokens` and `_save_to_auth_json` (root rule: never hardcode `~/.shiina`;
   it broke profiles).
2. `agent/account_usage.py::_antigravity_token_manager` — builds that manager for the account
   behind the pooled `api_key`, looking up its `refresh_token` from `load_pool("antigravity")`.
   No `api_key` (the singleton path) still uses the default active-account manager.
3. `_fetch_antigravity_account_usage` now distinguishes HTTP status from transport failure and
   retries once with `force_refresh=True` on 401/403 — a token re-issued elsewhere leaves the
   pooled copy stale.

Verify:

```bash
.venv/bin/python - <<'PY'
import httpx
from agent.credential_pool import load_pool
for e in load_pool("antigravity").entries():
    r = httpx.post("https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary",
                   headers={"Authorization": f"Bearer {e.access_token}",
                            "Content-Type": "application/json", "User-Agent": "antigravity/1.2.7"},
                   json={}, timeout=10.0)
    print(e.label, [f"{b['window']}={b.get('remainingFraction')}" for g in r.json().get("groups", []) for b in g.get("buckets", [])])
PY
```

Each account must return different `remainingFraction` values. Then
`fetch_all_provider_usage(["antigravity"])` → two rows with distinct percentages and reset
times.

Test: `tests/agent/test_account_usage_fetch.py::test_fetch_account_usage_antigravity_queries_each_account_with_its_own_token`
— red on base with `['Bearer active-account-token', 'Bearer active-account-token']` instead of
`['Bearer tok-a', 'Bearer tok-b']`.

---

## 9. Add more below

<!-- Append new providers, bugs, and verification steps here. -->

### 9.1 xKiro (hosted OpenAI-compatible API, key-authenticated)

`xkiro` is NOT the local `kiro-cli` provider — it is a hosted multi-vendor API at
`https://api.xkiro.com/v1` (Bearer token, OpenAI `chat_completions` wire). It was previously
aliased to `kiro` in three places, which shadowed any key-authenticated use; those aliases are
removed and `xkiro` now has its own profile.

**Location / how:**
- Profile: `plugins/model-providers/xkiro/__init__.py` (`auth_type="api_key"`,
  `env_vars=("XKIRO_API_KEY",)`, `base_url="https://api.xkiro.com/v1"`). `fetch_models()` lists
  live from `GET /v1/models` and falls back to the curated `XKIRO_MODELS`.
- Secret: `XKIRO_API_KEY` in `$SHIINA_HOME/.env` (keys look like `sk-xt-...`).
- Aliases: canonical `xkiro`; `x-kiro` / `xkiro-api` resolve to it
  (`shiina_cli/providers.py` `_ALIAS_GROUPS`, `shiina_cli/auth.py` alias map).
  `kiro` keeps only `kiro-cli` / `kiro-ai` / `kiro-dev`.

**Data needed:** one API key. Free tier is 1,000,000 tokens/day and needs no plan; `access_tier`
in the catalog marks `free` vs `paid` vs `premium`. Premium/prepaid models return HTTP 403
("requires an active paid plan or real deposited balance") while the wallet is $0.00 — that is
expected billing state, not a broken key.

**Verify:**

```bash
.venv/bin/python - <<'PY'
import os, httpx
from pathlib import Path
for line in Path(os.path.expanduser("~/.shiina/.env")).read_text().splitlines():
    if line.strip() and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
from shiina_cli.runtime_provider import resolve_runtime_provider
rt = resolve_runtime_provider(requested="xkiro")
r = httpx.post(f"{rt['base_url'].rstrip('/')}/chat/completions",
               headers={"Authorization": f"Bearer {rt['api_key']}"},
               json={"model": "qwen/qwen3.7-flash:free",
                     "messages": [{"role": "user", "content": "say OK"}], "max_tokens": 5},
               timeout=60.0)
print(r.status_code, r.json()["choices"][0]["message"]["content"])
PY
```

Expect `200 OK`. `GET /v1/usage` returns the account, daily free-token balance and wallet; it is
already wired as an account-usage source (`agent/account_usage.py::_fetch_xkiro_account_usage`,
keyed `"xkiro"` / `"custom:xkiro"`).
