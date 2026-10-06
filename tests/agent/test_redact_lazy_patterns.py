"""Lazy regex compilation in ``agent.redact`` must not change what gets redacted.

``agent.redact`` is on every ``shiina`` start's import path (``shiina_logging`` installs the
redacting formatter); its ~30 module-level ``re.compile`` calls cost ~80 ms of it. Only the
compilation is deferred — pattern sources, flags and match order are untouched.
"""

import subprocess
import sys
import textwrap

from agent import redact


def test_nothing_is_compiled_at_import():
    code = textwrap.dedent(
        """
        import agent.redact as r
        eager = [n for n, v in vars(r).items()
                 if isinstance(v, r._LazyPattern) and v._compiled is not None]
        assert not eager, eager
        """
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr


def test_patterns_redact_after_lazy_compilation():
    out = redact.redact_sensitive_text("OPENAI_API_KEY=sk-abcdefghijklmnop1234")
    assert "sk-abcdefghijklmnop1234" not in out
    out = redact.redact_sensitive_text(
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abcdefghijklmnop.qrstuvwxyz"
    )
    assert "abcdefghijklmnop" not in out, out
    assert out.startswith("Authorization: Bearer ")
    # Compiled on first use, then reused.
    assert redact._ENV_ASSIGN_RE._compiled is not None
