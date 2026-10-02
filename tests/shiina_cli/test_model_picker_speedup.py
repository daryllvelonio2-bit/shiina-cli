"""Tests for the /model picker speedup and the ``/models refresh`` word form.

The picker open must never block on force-refreshing every expired provider
catalog (the background prefetch + SWR stale-serve own that); a missing disk
entry is served by the curated fallback while a prefetch for the key is in
flight; and the pool-usability probe is memoized briefly so one open does not
re-run load_pool's seeding chain ~6x per provider. Bare ``refresh`` is the
word-only form of ``--refresh`` (not a model name).
"""

from __future__ import annotations

import time

from shiina_cli.model_switch import parse_model_switch_args
from shiina_cli import model_switch_providers
from shiina_cli.models import (
    _PROVIDER_MODELS_CACHE_TTL,
    _cache_entry,
    _credential_fingerprint,
    _load_provider_models_cache,
    cached_provider_model_ids,
    update_provider_cache_entry,
)


# ── /model refresh — the bare word form ──────────────────────────────

def test_bare_refresh_word_means_force_refresh():
    """``/model refresh`` parses as --refresh, not a model named 'refresh'."""
    req = parse_model_switch_args("refresh")
    assert req.target == ""
    assert req.force_refresh is True


def test_refresh_word_with_provider_keeps_provider():
    """``refresh --provider mistral`` still names the provider (the word form alone is the
    refresh; with a provider it targets that provider's catalog — the flag form asks to wait)."""
    req = parse_model_switch_args("refresh --provider mistral")
    assert req.explicit_provider == "mistral"
    assert req.target == "refresh"


def test_a_model_named_refresh_is_still_addressable():
    """``refresh --provider x`` with a target... a model literally named refresh is
    addressed with --refresh alongside; the word form alone never blocks it."""
    req = parse_model_switch_args("vendor/refresh")
    assert req.target == "vendor/refresh"
    assert req.force_refresh is False


# ── SWR + prefetch: the open never blocks on expired catalogs ────────

def test_expired_entry_is_served_stale_not_refetched():
    """An expired same-credentials entry is served immediately (SWR), not via a live fetch."""
    slug = "swr-test-provider"
    update_provider_cache_entry(slug, ["m1", "m2"])
    cache = _load_provider_models_cache()
    # Backdate the entry past the TTL but inside the 7d SWR window.
    entry = cache.get(slug)
    assert isinstance(entry, dict) and entry.get("models")
    stale = _cache_entry(_credential_fingerprint(slug), entry["models"],
                         at=time.time() - (_PROVIDER_MODELS_CACHE_TTL + 60))
    cache[slug] = stale
    t0 = time.perf_counter()
    models = cached_provider_model_ids(slug)
    elapsed = time.perf_counter() - t0
    assert models == ["m1", "m2"], f"stale entry must be served, got {models}"
    assert elapsed < 1.0, f"stale serve must be instant, took {elapsed:.2f}s"


def test_missing_entry_serves_curated_fallback_while_prefetch_inflight():
    """While a prefetch for a missing key is in flight, the caller gets [] (curated
    fallback upstream) instead of blocking on the same live fetch."""
    slug = "prefetch-inflight-test-provider"
    from shiina_cli.models import _swr_refresh_inflight, _swr_refresh_lock
    with _swr_refresh_lock:
        _swr_refresh_inflight.add(slug)
    try:
        t0 = time.perf_counter()
        models = cached_provider_model_ids(slug)
        elapsed = time.perf_counter() - t0
        assert models == []
        assert elapsed < 0.5, f"inflight serve must be fast, took {elapsed:.2f}s"
    finally:
        with _swr_refresh_lock:
            _swr_refresh_inflight.discard(slug)


# ── the usability-probe memo ─────────────────────────────────────────

def test_pool_usable_memo_collapses_repeat_probes():
    """Repeat probes within the TTL hit the memo (load_pool called once per provider)."""
    model_switch_providers._pool_usable_memo.clear()
    calls = []
    real_load = None
    try:
        import agent.credential_pool as cp
        real_load = cp.load_pool

        def _counting_load(provider):
            calls.append(provider)
            return real_load(provider)

        cp.load_pool = _counting_load
        model_switch_providers._credential_pool_is_usable("swr-test-provider")
        model_switch_providers._credential_pool_is_usable("swr-test-provider")
        model_switch_providers._credential_pool_is_usable("swr-test-provider")
        assert calls.count("swr-test-provider") == 1, (
            f"memo must collapse repeat probes, got {calls.count('swr-test-provider')} load_pool calls"
        )
    finally:
        if real_load is not None:
            import agent.credential_pool as cp
            cp.load_pool = real_load
        model_switch_providers._pool_usable_memo.clear()
