# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Broker/consumer connection state, shared with ``GET /health/ready``.

Kept in its own module so the readiness route does not import the consumer (and
its RabbitMQ dependencies) just to read a boolean.
"""

from __future__ import annotations

import time

_state: dict[str, object] = {"connected": False, "error": None, "changed_at": None}


def set_broker_state(connected: bool, error: str | None = None) -> None:
    _state["connected"] = connected
    _state["error"] = error
    _state["changed_at"] = time.time()


def broker_state() -> dict[str, object]:
    return dict(_state)
