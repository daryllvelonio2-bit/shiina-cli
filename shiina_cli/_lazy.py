"""Lazy import helpers — no dependencies, usable at module load time everywhere."""

import importlib
from typing import Any, Callable, Optional


def _lazy_shim(module: str, name: str, alias: Optional[str] = None) -> Callable[..., Any]:
    """Import ``module.name`` on first call; keeps heavy imports off startup."""

    def shim(*args, **kwargs):
        return getattr(importlib.import_module(module), name)(*args, **kwargs)

    shim.__name__ = shim.__qualname__ = alias or name
    return shim
