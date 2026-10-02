# Process-registry startup prewarm.

"""Warm the process-registry import off the user's critical path.

The first status-bar paint otherwise blocks ~0.6-1s on the
``tools.process_registry`` import chain (its module-level ``ProcessRegistry()``
runs the async-delegation recovery DB scan; ~78 cold module imports). Mirrors
``prewarm_picker_cache_async``: daemon thread, once-per-process guard, fully
exception-isolated. The import lock makes a later foreground import block on
the remaining work rather than redo it.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# Process-level guard: the prewarm thread is spawned at most once per process,
# otherwise a long-lived process would leak one OS thread per trigger.
_prewarm_done = threading.Event()


def prewarm_process_registry_async() -> Optional[threading.Thread]:
    """Pre-import ``tools.process_registry`` (and run its delegation recovery) in a daemon thread.

    Fire-and-forget, at most once per process, fully exception-isolated.
    Returns the thread (for tests) or None if already warmed.
    """
    if _prewarm_done.is_set():
        return None
    _prewarm_done.set()

    def _warm() -> None:
        try:
            import tools.process_registry  # noqa: F401  (runs ProcessRegistry() + recovery)
        except Exception:
            logger.debug("process-registry prewarm failed", exc_info=True)

    t = threading.Thread(target=_warm, daemon=True, name="process-registry-prewarm")
    t.start()
    return t
