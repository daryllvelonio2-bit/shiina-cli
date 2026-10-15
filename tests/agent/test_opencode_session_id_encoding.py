"""x-opencode-session rides on every OpenCode request, on every transport.

OpenCode's canonical SessionID is ``ses_`` + 12 lowercase-hex + 14 Base62 characters (30 total).
Zen's free tier does not just check that shape — it decodes the 12-hex prefix and rejects
anything that is not OpenCode's own id encoding (``~((ms << 12) | counter)``, truncated to 48
bits) with ``403 FreeTierError``; a plain timestamp, a random hex value and an sha256 slice all
fail it. ``derive_opencode_session_id()`` therefore mints that encoding once per session key and
reuses it, so every transport and turn of a conversation sends one stable, Zen-valid id.
"""

from __future__ import annotations

import asyncio
import re
import time
from types import SimpleNamespace

import pytest

from agent import auxiliary_client as aux
from agent.chat_completion_helpers import build_api_kwargs
from agent.opencode_affinity import derive_opencode_session_id
from run_agent import AIAgent

_MSGS = [{"role": "user", "content": "hi"}]

# Canonical OpenCode SessionID: "ses_" + 12 lowercase-hex + 14 Base62 (30 chars).
_CANONICAL_SESSION_ID_RE = re.compile(r"^ses_[0-9a-f]{12}[0-9A-Za-z]{14}$")

# OpenCode keeps 48 bits of ``ms << 12 | counter``; the low 36 bits of the millisecond
# timestamp survive (inverted) and decode back to the wall clock.
_ID_CEILING = 1 << 48
_MS_WINDOW = 1 << 36
_SESSION_ALIAS_HEADERS = ("x-opencode-session", "x-opencode-session-id", "x-session-affinity", "x-session-id")


def test_session_id_prefix_decodes_to_the_wall_clock():
    """The 12-hex prefix must be OpenCode's clock encoding, not an opaque hash slice.

    This is the invariant the Zen free-tier gate enforces: it decodes the prefix and 403s a
    session id whose value is not one the real client would have generated.
    """
    sid = derive_opencode_session_id("sess-affinity-1")
    assert _CANONICAL_SESSION_ID_RE.match(sid)
    decoded_ms = (_ID_CEILING - 1 - int(sid[4:16], 16)) // 4096
    now_ms = int(time.time() * 1000) % _MS_WINDOW
    assert abs(decoded_ms - now_ms) < 5_000


def test_identity_headers_carry_every_session_alias():
    """OpenCode v2 sends the session id under three extra names; the gate wants them all."""
    from agent.opencode_affinity import opencode_session_headers

    headers = opencode_session_headers("opencode-zen", "https://opencode.ai/zen/v1", "sess-alias-1")
    sid = headers["x-opencode-session"]
    assert _CANONICAL_SESSION_ID_RE.match(sid)
    for name in _SESSION_ALIAS_HEADERS:
        assert headers[name] == sid
    assert headers["User-Agent"].startswith("opencode/")
