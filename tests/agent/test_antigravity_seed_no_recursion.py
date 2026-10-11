"""Invariant: seeding a singleton provider must not re-enter load_pool.

``_seed_antigravity_singleton`` used to construct ``GoogleOAuthTokenManager``; the
manager's ``_load_active_pool_tokens`` called ``load_pool("antigravity")`` again,
which re-seeded, which constructed another manager — ~110 nested levels per
``load_pool`` (2.7s per picker build, 141 manager constructions, 424 auth-store
deepcopies). Seeding now reads the caller's auth-store snapshot directly.
"""

import pytest

from agent import credential_pool as cp


class _FakeSeed:
    def __init__(self):
        self.provider = "antigravity"
        self.entries = []
        self.active_sources = set()

    def is_suppressed(self, provider, source):
        return False

    def upsert(self, source, payload):
        self.active_sources.add(source)
        self.entries.append({"source": source, **payload})
        return True


def test_antigravity_seed_does_not_reenter_load_pool(monkeypatch):
    entered = {"load_pool": 0, "manager": 0}
    real_manager = cp.__dict__.get("GoogleOAuthTokenManager")

    import agent.antigravity_client as ac

    real_init = ac.GoogleOAuthTokenManager.__init__

    def counting_init(self, *a, **k):
        entered["manager"] += 1
        return real_init(self, *a, **k)

    monkeypatch.setattr(ac.GoogleOAuthTokenManager, "__init__", counting_init)

    real_load = cp.load_pool

    def counting_load(provider):
        entered["load_pool"] += 1
        return real_load(provider)

    monkeypatch.setattr(cp, "load_pool", counting_load)

    store = {"providers": {"antigravity": {
        "access_token": "tok", "refresh_token": "ref",
        "label": "someone@example.com"}}}
    seed = _FakeSeed()

    cp._seed_antigravity_singleton(seed, store)

    # The contract: seeding reads the snapshot it was handed. Zero pool re-entry,
    # zero manager constructions (the token was present and unexpired).
    assert entered["load_pool"] == 0
    assert entered["manager"] == 0
    assert seed.entries and seed.entries[0]["access_token"] == "tok"
    assert seed.entries[0]["refresh_token"] == "ref"


def test_antigravity_seed_empty_store_seeds_nothing():
    seed = _FakeSeed()
    cp._seed_antigravity_singleton(seed, {"providers": {}})
    assert seed.entries == []
