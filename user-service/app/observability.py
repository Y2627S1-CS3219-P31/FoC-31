# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""User-service observability handle (shared implementation in ``foc_shared``)."""

from __future__ import annotations

from foc_shared.observability import Observability

OBS = Observability("user-service", prefix="user")
