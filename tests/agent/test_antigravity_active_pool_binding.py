"""Regression test: the default Antigravity token manager resolves the ACTIVE pooled account.

The SecretService/secret-tool scan finds whichever account's tokens the Antigravity IDE
last wrote — with a multi-account pool that is frequently NOT the active one, so chat
turns used one account while the status bar and /usage reported the other. The pool's
active entry (priority-0 / `shiina auth use` selection) must win when it carries
credentials, and the manager must FOLLOW a mid-session `shiina auth use` switch.

Harness: the REAL ``_load_initial_tokens`` chain runs; only its external steps are
patched out (env unset, scanners unplugged, no auth.json on a temp home) so the
pool-active step's ORDER is what the tests catch.
"""

from __future__ import annotations

from agent.antigravity_client import GoogleOAuthTokenManager


class _Entry:
    def __init__(self, id, access_token, refresh_token=None, priority=0, label=""):
        self.id = id
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.priority = priority
        self.label = label
        self.expires_at = None
        self.expires_at_ms = None


class _Pool:
    def __init__(self, entries):
        self._entries = entries

    def has_credentials(self):
        return bool(self._entries)

    def peek(self):
        return sorted(self._entries, key=lambda e: e.priority)[0] if self._entries else None


def _unplug_external_steps(monkeypatch, tmp_path):
    """Env unset + SecretService/secret-tool/keychain/keyring/auth.json steps unplugged:
    the chain reaches ONLY the pool-active step (and a no-op tail)."""
    import os as _os
    for var in ("ANTIGRAVITY_ACCESS_TOKEN", "AGY_ACCESS_TOKEN", "GEMINI_ACCESS_TOKEN",
                "GOOGLE_ACCESS_TOKEN"):
        monkeypatch.setenv(var, "")
        monkeypatch.delenv(var, raising=False)
    # secretstorage: absent in this venv (ImportError path) — leave it.
    # secret-tool subprocess: make it fail fast.
    monkeypatch.setattr("agent.antigravity_client.shutil.which", lambda name: None)
    # auth.json: point the home at an empty temp dir.
    monkeypatch.setattr(
        "shiina_constants.get_shiina_home", lambda: tmp_path, raising=False)
    # keyring: absent in this venv (ImportError path) — leave it.


def test_default_manager_prefers_active_pool_entry_over_secret_service(monkeypatch, tmp_path):
    """The pool's active entry (priority 0) wins over the SecretService scan's token."""
    pool = _Pool([
        _Entry("0ef8ff", "active-pool-token", "ref-active", priority=0, label="daryllvelonio@gmail.com"),
        _Entry("82276f", "secret-service-token", "ref-other", priority=1, label="daryllvelonio9@gmail.com"),
    ])
    monkeypatch.setattr("agent.credential_pool.load_pool", lambda provider: pool)
    _unplug_external_steps(monkeypatch, tmp_path)

    mgr = GoogleOAuthTokenManager()
    assert mgr._access_token == "active-pool-token", (
        f"default manager must load the ACTIVE pooled account's token, got {mgr._access_token!r}"
    )
    assert mgr._email == "daryllvelonio@gmail.com"


def test_default_manager_follows_auth_use_switch(monkeypatch, tmp_path):
    """A mid-session `shiina auth use` (priority flip) is picked up by a fresh manager."""
    entries = [
        _Entry("0ef8ff", "tok-one", priority=0, label="one@gmail.com"),
        _Entry("82276f", "tok-two", priority=1, label="two@gmail.com"),
    ]
    pool = _Pool(entries)
    monkeypatch.setattr("agent.credential_pool.load_pool", lambda provider: pool)
    _unplug_external_steps(monkeypatch, tmp_path)

    mgr = GoogleOAuthTokenManager()
    assert mgr._access_token == "tok-one"

    entries[0].priority, entries[1].priority = 1, 0  # `shiina auth use` #2
    mgr2 = GoogleOAuthTokenManager()
    assert mgr2._access_token == "tok-two", "a fresh manager must follow the new active entry"


def test_default_manager_falls_back_without_pool(monkeypatch, tmp_path):
    """No pool / no credentials: the SecretService token still answers (fail-over intact)."""
    monkeypatch.setattr("agent.credential_pool.load_pool", lambda provider: _Pool([]))
    _unplug_external_steps(monkeypatch, tmp_path)
    # Give the auth.json fallback a payload so the chain lands somewhere deterministic.
    (tmp_path / "auth.json").write_text(
        '{"providers": {"antigravity": {"access_token": "secret-service-token"}}}')
    monkeypatch.setattr(
        "shiina_constants.get_shiina_home", lambda: tmp_path, raising=False)

    mgr = GoogleOAuthTokenManager()
    assert mgr._access_token == "secret-service-token"
