# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Log-correlation context shim (implementation lives in ``foc_shared``)."""

from __future__ import annotations

from foc_shared.observability import bind, current, reset

__all__ = ["bind", "current", "reset"]
