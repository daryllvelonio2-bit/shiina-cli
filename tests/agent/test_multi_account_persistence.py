"""Unit tests verifying multi-account credential persistence and non-destructive reload."""

import json
import pytest
from pathlib import Path

from agent.credential_pool import (
    AUTH_TYPE_API_KEY,
    AUTH_TYPE_OAUTH,
    PooledCredential,
    load_pool,
)
from shiina_cli.auth import read_credential_pool, write_credential_pool


def test_two_accounts_same_provider_persist_and_retain_tokens(tmp_path, monkeypatch):
    """When two or more accounts are added for a provider, all accounts and their secrets persist."""
    shiina_home = tmp_path / "shiina"
    shiina_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SHIINA_HOME", str(shiina_home))
    # Prevent host environment's live external tokens from auto-injecting into tmp pool
    monkeypatch.setattr("agent.credential_pool._seed_antigravity_singleton", lambda s: None)
    monkeypatch.setattr("agent.credential_pool._seed_freebuff_singleton", lambda s: None)
    monkeypatch.setattr("agent.credential_pool._seed_kiro_singleton", lambda s: None)
    monkeypatch.setattr("agent.credential_pool._seed_opencode_singleton", lambda s: None)

    for provider in ("openai-codex", "anthropic", "minimax-oauth", "antigravity", "opencode-cli", "kiro"):
        pool = load_pool(provider)

        # Add Account 1
        acct1 = PooledCredential(
            provider=provider,
            id=f"{provider}-acct1",
            label="Work Account",
            auth_type=AUTH_TYPE_OAUTH,
            priority=0,
            source="oauth",
            access_token=f"token-work-{provider}",
            refresh_token=f"refresh-work-{provider}",
        )
        pool.add_entry(acct1)

        # Add Account 2
        acct2 = PooledCredential(
            provider=provider,
            id=f"{provider}-acct2",
            label="Personal Account",
            auth_type=AUTH_TYPE_OAUTH,
            priority=1,
            source="oauth",
            access_token=f"token-personal-{provider}",
            refresh_token=f"refresh-personal-{provider}",
        )
        pool.add_entry(acct2)

        # Verify on-disk auth.json contains both accounts with tokens intact
        auth_data = json.loads((shiina_home / "auth.json").read_text())
        pool_data = auth_data["credential_pool"][provider]
        assert len(pool_data) == 2
        assert any(e["id"] == f"{provider}-acct1" and e["access_token"] == f"token-work-{provider}" for e in pool_data)
        assert any(e["id"] == f"{provider}-acct2" and e["access_token"] == f"token-personal-{provider}" for e in pool_data)

        # Reload pool from disk and verify both accounts remain intact
        reloaded_pool = load_pool(provider)
        entries = reloaded_pool.entries()
        assert len(entries) == 2
        assert entries[0].id == f"{provider}-acct1"
        assert entries[0].access_token == f"token-work-{provider}"
        assert entries[0].refresh_token == f"refresh-work-{provider}"
        assert entries[1].id == f"{provider}-acct2"
        assert entries[1].access_token == f"token-personal-{provider}"
        assert entries[1].refresh_token == f"refresh-personal-{provider}"


def test_singleton_seeding_does_not_destroy_independent_accounts(tmp_path, monkeypatch):
    """Singleton re-auth updates the matching account while keeping other accounts intact."""
    shiina_home = tmp_path / "shiina"
    shiina_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SHIINA_HOME", str(shiina_home))

    # Pre-populate auth.json with singleton for Account A and manual Account B
    (shiina_home / "auth.json").write_text(json.dumps({
        "version": 1,
        "providers": {
            "openai-codex": {
                "tokens": {"access_token": "token-A-v1", "refresh_token": "refresh-A-v1"},
                "last_refresh": "2026-01-01T00:00:00Z",
                "label": "Account A",
            }
        },
        "credential_pool": {
            "openai-codex": [
                {
                    "id": "acct-a",
                    "label": "Account A",
                    "source": "device_code",
                    "auth_type": "oauth",
                    "priority": 0,
                    "access_token": "token-A-v1",
                    "refresh_token": "refresh-A-v1",
                },
                {
                    "id": "acct-b",
                    "label": "Account B",
                    "source": "device_code",
                    "auth_type": "oauth",
                    "priority": 1,
                    "access_token": "token-B",
                    "refresh_token": "refresh-B",
                }
            ]
        }
    }))

    # Reload pool: both accounts should be present
    pool = load_pool("openai-codex")
    assert len(pool.entries()) == 2
    assert {e.id for e in pool.entries()} == {"acct-a", "acct-b"}

    # Update singleton with fresh token for Account A (e.g. re-login)
    auth_data = json.loads((shiina_home / "auth.json").read_text())
    auth_data["providers"]["openai-codex"]["tokens"]["access_token"] = "token-A-v2"
    (shiina_home / "auth.json").write_text(json.dumps(auth_data))

    # Reload pool again: Account A updated, Account B untouched
    pool2 = load_pool("openai-codex")
    entries2 = {e.id: e for e in pool2.entries()}
    assert len(entries2) == 2
    assert entries2["acct-a"].access_token == "token-A-v2"
    assert entries2["acct-b"].access_token == "token-B"


def test_remove_one_account_keeps_other_accounts(tmp_path, monkeypatch):
    """Removing one account only drops that account and retains remaining accounts."""
    shiina_home = tmp_path / "shiina"
    shiina_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SHIINA_HOME", str(shiina_home))
    monkeypatch.setattr("agent.credential_pool._seed_antigravity_singleton", lambda s: None)

    pool = load_pool("antigravity")
    pool.add_entry(PooledCredential(
        provider="antigravity",
        id="agy-1",
        label="Account 1",
        auth_type=AUTH_TYPE_OAUTH,
        priority=0,
        source="oauth",
        access_token="agy-tok-1",
    ))
    pool.add_entry(PooledCredential(
        provider="antigravity",
        id="agy-2",
        label="Account 2",
        auth_type=AUTH_TYPE_OAUTH,
        priority=1,
        source="oauth",
        access_token="agy-tok-2",
    ))

    assert len(pool.entries()) == 2

    # User explicitly removes Account 1 (index 1)
    removed = pool.remove_index(1)
    assert removed.id == "agy-1"

    # Verify Account 2 remains in memory and on disk
    assert len(pool.entries()) == 1
    assert pool.entries()[0].id == "agy-2"
    assert pool.entries()[0].access_token == "agy-tok-2"

    reloaded = load_pool("antigravity")
    assert len(reloaded.entries()) == 1
    assert reloaded.entries()[0].id == "agy-2"
    assert reloaded.entries()[0].access_token == "agy-tok-2"


def test_dynamic_seeding_coexists_with_manually_added_accounts(tmp_path, monkeypatch):
    """Dynamic discovery (e.g. CLI auth) coexists cleanly with user-added accounts."""
    shiina_home = tmp_path / "shiina"
    shiina_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SHIINA_HOME", str(shiina_home))

    # Mock dynamic discovery returning a live CLI account
    def mock_seed_antigravity(seed):
        seed.upsert("oauth", {
            "auth_type": AUTH_TYPE_OAUTH,
            "access_token": "live-cli-token",
            "label": "Google Antigravity OAuth (agy)",
        })

    monkeypatch.setattr("agent.credential_pool._seed_antigravity_singleton", mock_seed_antigravity)

    pool = load_pool("antigravity")
    assert len(pool.entries()) == 1
    assert pool.entries()[0].access_token == "live-cli-token"

    # Now user adds a second account
    pool.add_entry(PooledCredential(
        provider="antigravity",
        id="secondary-account",
        label="Secondary Account",
        auth_type=AUTH_TYPE_OAUTH,
        priority=1,
        source="oauth",
        access_token="second-token-secret",
    ))

    assert len(pool.entries()) == 2

    # Reload pool: both CLI and user account persist with tokens intact
    reloaded = load_pool("antigravity")
    assert len(reloaded.entries()) == 2
    tokens = {e.access_token for e in reloaded.entries()}
    assert tokens == {"live-cli-token", "second-token-secret"}
