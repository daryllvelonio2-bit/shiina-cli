# Shiina CLI — External AI Tools Integration & Credential Pooling Architecture

## 1. Executive Summary & Purpose

This document serves as an exhaustive technical guide and operational handover document. It captures the architecture, implementation history, lessons learned, and reproduction steps for integrating external AI CLI tools into **Shiina**, enabling multi-account persistence, credential protection, account identity resolution, and automated tool discovery via `shiina scan`.

Any AI engineer or coding agent working on this or a similar codebase should read this document to understand:
1. How external CLI accounts (Antigravity/agy, OpenCode, Kiro, Freebuff, Cline) are discovered and executed.
2. Why credentials were disappearing or being overwritten, and the exact architectural fix implemented.
3. How account identities (e.g. Gmail addresses) are extracted from native OS keychains and opaque OAuth tokens.
4. How the `shiina scan` command orchestrates cross-CLI discovery without destructive state overwrites.

---

## 2. Supported External Tools Matrix

| Tool | Provider Name(s) | Primary Storage / Discovery Location | Auth Mechanism | Model Calling Strategy |
| :--- | :--- | :--- | :--- | :--- |
| **Antigravity (`agy`)** | `antigravity`, `agy` | Linux `secret-tool` / SecretService (`service: gemini`), macOS Keychain (`service: gemini`), or `~/.shiina/auth.json` | Google One / Code Assist OAuth (`access_token`, `refresh_token`, `id_token`) | Direct Google Cloud Code Assist REST API (`daily-cloudcode-pa.googleapis.com`) bypassing subprocess |
| **OpenCode** | `opencode`, `opencode-cli` | `~/.local/share/opencode/auth.json`, `~/.config/opencode/auth.json`, or binary CLI | Multi-provider API keys (`groq`, `openrouter`, `anthropic`, etc.) or headless binary | Headless CLI subprocess / JSON streaming or direct provider routing |
| **Kiro CLI** | `kiro`, `kiro-cli` | SQLite store at `~/.local/share/kiro-cli/data.sqlite3` (`auth_kv` table) | Social/Google OAuth session (`access_token`, `refresh_token`, `profile_arn`) | Direct headless CLI invocation or session token proxy |
| **Freebuff (Codebuff)** | `freebuff`, `codebuff` | `~/.config/manicode/credentials.json`, `~/.shiina/auth.json`, or environment variables | API Key / Auth Token (`ba3c36e2-...`) | PTY-wrapped subprocess driving interactive terminal session |
| **Cline** | `cline` | `~/.shiina/auth.json` (manual/pool storage) | Bot API Key (`sk_c...`) | Standard OpenAI-compatible HTTP client |

---

## 3. The Core Problems & Root Causes Solved

### Problem A: "Credentials Disappearing on Reload"
* **Symptom:** When a user had multiple accounts or updated a token, restarting Shiina or running commands wiped existing accounts or stripped their secret tokens.
* **Root Cause:**
  1. `agent/credential_persistence.py` contained a hardcoded allowlist (`_PERSISTABLE_PROVIDER_SOURCES`, `_OWNED_AUTH_PROVIDERS`, `_OWNED_AUTH_SOURCES`). Any provider or source not on the list was categorized as "borrowed" (reference-only).
  2. For borrowed sources, `sanitize_borrowed_credential_payload` stripped all secrets (`access_token`, `refresh_token`, `api_key`) and only kept a SHA-256 fingerprint on disk.
  3. During `load_pool()`, `_prune_stale_seeded_entries()` checked whether the singleton source was still active in memory. If not found in the current pass, entries were deleted from `auth.json`.

### Problem B: "New Account Not Added; Stuck on Old Account"
* **Symptom:** User logged into `daryllvelonio@gmail.com` via `agy`, but Shiina retained the older `daryllvelonio9@gmail.com` credential and never added the new account.
* **Root Cause:**
  1. **Virtualenv isolation from D-Bus:** Shiina runs inside a Python virtual environment (`.venv`) where python packages `secretstorage` and `keyring` were not installed. When trying to inspect SecretService, Python raised `ModuleNotFoundError: No module named 'secretstorage'`.
  2. Because the exception was swallowed, it fell back to reading `~/.shiina/auth.json` which held the *old* account's tokens.
  3. **Opaque labels:** Antigravity accounts were saved with a static generic label `"Google Antigravity OAuth (agy)"` and no `user_id`.
  4. **Blocked label updates:** In `_upsert_entry()`, the logic read `if (key == "label" and existing.label): continue`. Even if a new account was processed, its label was discarded if the old entry already had a label.
  5. **No identity collision detection:** Because `user_id` was missing, Shiina could not determine whether an incoming token belonged to a different user.

---

## 4. Architectural Solutions Implemented

### 4.1. OS-Native Secret Recovery (`agent/antigravity_client.py`)
To bypass virtualenv python package limitations, a subprocess fallback using Linux's native `secret-tool` was introduced:
```python
# 1. Try python secretstorage
# 2. If missing or fails on Linux, call native secret-tool:
if sys.platform.startswith("linux") and shutil.which("secret-tool"):
    proc = subprocess.run(
        ["secret-tool", "lookup", "service", "gemini", "username", "antigravity"],
        capture_output=True, text=True, timeout=5,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        raw = json.loads(proc.stdout.strip())
        ...
```

### 4.2. Account Email Resolution (Without Network Latency)
Google OAuth tokens in SecretService contain an `id_token` (JWT). We decode the payload section in base64 without needing third-party libraries or network requests:
```python
def _extract_account_metadata(self, raw: Any) -> None:
    id_tok = raw.get("id_token") or (raw.get("token", {}).get("id_token"))
    if id_tok and isinstance(id_tok, str) and "." in id_tok:
        parts = id_tok.split(".")
        if len(parts) >= 2:
            padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
            claims = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
            if claims.get("email"):
                self._email = str(claims["email"]).strip()
```
If `id_token` is unavailable, `get_authenticated_email()` falls back to Google's fast endpoint:
`https://oauth2.googleapis.com/tokeninfo?access_token=<token>` (with a 3s timeout).

### 4.3. Multi-Account Coexistence in Credential Pool (`agent/credential_pool.py`)
1. **Identity Matching:** `_find_matching_entry_index()` checks `entry.extra.get("user_id") == incoming_user_id`. When a user authenticates with `daryllvelonio@gmail.com`, it does **not** match `daryllvelonio9@gmail.com`.
2. **Coexistence:** Since `existing_idx` returns `None`, the new account is appended as a distinct pool entry with its own `id`, `label`, and `priority`.
3. **Generic Label Replacement:** If an existing entry had a generic fallback label (e.g. `"Google Antigravity OAuth (agy)"`), `_upsert_entry()` updates it to the user's authentic email upon token rotation.
4. **Non-Destructive Pruning:** `_prune_stale_seeded_entries()` explicitly protects any entry containing valid credentials (`access_token`, `refresh_token`, `api_key`), ensuring accounts are only deleted when the user runs `shiina auth remove <provider> <target>`.

### 4.4. Credential Persistence Allowlist (`agent/credential_persistence.py`)
Added all external providers and source prefixes (`opencode:*`, `kiro:*`, `antigravity`, `freebuff`, `cline`) to `_PERSISTABLE_PROVIDER_SOURCES` and `is_borrowed_credential_source()`. Tokens for these providers are guaranteed never to be stripped at the JSON disk boundary.

---

## 5. The Unified `shiina scan` Command

A top-level CLI command `shiina scan` (also available as `shiina auth scan`) was created to discover, report, and synchronize accounts from all installed CLI tools.

### User Flow & CLI Output
```bash
$ shiina scan
Scanning available external CLI tools and accounts...

CLI Tool             Status           Account / Details                  Pool Count
--------------------------------------------------------------------------------
antigravity (agy)    Connected        daryllvelonio@gmail.com            2
opencode             Connected        groq                               1
kiro                 Connected        Session (google)                   1
freebuff             Connected        Active Token                       1
cline                Connected        3 key(s) configured                3

Synced detected accounts into credential pool.
```

### Checking Configured Accounts
```bash
$ shiina auth list antigravity
antigravity (2 credentials):
  #1  Google Antigravity OAuth (agy) oauth   id=5703d4 priority=0 oauth ←
  #2  daryllvelonio@gmail.com        oauth   id=3ddad2 priority=1 oauth
```

Both accounts are preserved and available for automatic failover / load balancing according to the configured pool strategy (`fill_first`, `round_robin`, `least_used`, `random`).

---

## 6. Comprehensive File Modification Map

When implementing or extending this in another environment, here are the key files and the exact modifications made:

| File | Changes Made |
| :--- | :--- |
| `agent/antigravity_client.py` | Added `secret-tool` subprocess fallback in `GoogleOAuthTokenManager._load_initial_tokens()`. Added `_extract_account_metadata()` to decode JWT `id_token` claims. Added `get_authenticated_email()` with fast tokeninfo fallback. |
| `agent/credential_pool.py` | Updated `_seed_antigravity_singleton()` to set `label=email` and `user_id=email`. Updated `_seed_opencode_singleton()` to parse all token keys (`token`, `access_token`, `apiKey`, `key`). Updated `_upsert_entry()` to allow label upgrades from generic defaults. Added `scan_all_clis()` scanner function. |
| `agent/credential_persistence.py` | Updated `is_borrowed_credential_source()` to permit dynamic prefixes (`opencode:*`, `kiro:*`) and external tools so secrets are written to disk intact. |
| `shiina_cli/auth_commands.py` | Implemented `auth_scan_command()` to format and print the CLI scan table. Added `"scan"` to `_AUTH_ACTIONS`. |
| `shiina_cli/subcommands/auth.py` | Registered `auth_subparsers.add_parser("scan")`. |
| `shiina_cli/main.py` | Forwarded `cmd_scan = _forward_command(..., "auth_scan_command")` and added top-level `scan` subcommand parser so users can run `shiina scan` directly. |
| `tests/agent/test_multi_account_persistence.py` | Unit tests verifying multi-account persistence, token preservation across reloads, and non-destructive pruning. |

---

## 7. How Another AI Should Test & Validate Changes

To verify that credential pooling and CLI scanning are healthy on any machine:

1. **Run the Full Test Suite**:
   ```bash
   .venv/bin/pytest tests/agent/test_multi_account_persistence.py tests/agent/test_credential_pool.py -v
   ```
   *Expected outcome:* All 68 tests must pass.

2. **Verify Live Discovery**:
   ```bash
   .venv/bin/python3 -m shiina_cli.main scan
   ```
   *Expected outcome:* Lists all detected CLIs, their accounts (e.g. Gmail addresses, provider names), and pool count without throwing exceptions.

3. **Verify Token Integrity in Storage**:
   ```bash
   .venv/bin/python3 -c "
   import json
   with open('/home/janelle/.shiina/auth.json') as f:
       data = json.load(f)
   pool = data.get('credential_pool', {})
   for p, entries in pool.items():
       for e in entries:
           assert e.get('access_token'), f'Missing token in {p}: {e.get(\"label\")}'
   print('All pool credentials have raw tokens intact.')
   "
   ```

---

## 8. Guidelines for Adding Future CLI Tools

If adding another tool (e.g. `cursor`, `aider`, `continue`):
1. **Client Adapter (`agent/<tool>_client.py`)**:
   - Provide non-blocking credential discovery (search env vars, config files in `~/.config` or `~/.local/share`, or CLI binary).
   - If using OAuth, always extract the user email/ID to allow multi-account coexistence.
2. **Persistence Rules (`agent/credential_persistence.py`)**:
   - Add the tool's provider name and sources to `_OWNED_AUTH_PROVIDERS` and `_PERSISTABLE_PROVIDER_SOURCES`.
3. **Singleton Seeding (`agent/credential_pool.py`)**:
   - Add `_seed_<tool>_singleton(seed)` inside `_seed_from_singletons()`.
   - Set `"user_id"` and `"label"` to the account email or distinct identifier.
4. **Scanner Integration (`scan_all_clis()`)**:
   - Add a detection block in `scan_all_clis()` so `shiina scan` automatically reports and syncs it.
