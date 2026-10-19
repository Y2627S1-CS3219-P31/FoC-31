# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Supplier-service observability handle (shared implementation in ``foc_shared``)."""

from __future__ import annotations

from foc_shared.observability import Observability

OBS = Observability("supplier-service", prefix="supplier")
