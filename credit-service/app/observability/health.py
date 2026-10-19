# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Broker/consumer state shim (implementation lives in ``foc_shared``)."""

from __future__ import annotations

from foc_shared.observability import broker_state, set_broker_state

__all__ = ["broker_state", "set_broker_state"]
