# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Correlation values for structured logs.

A single dict-backed ``ContextVar`` keeps HTTP requests and RabbitMQ message
handling isolated: asyncio copies the context per task, so a consumer task
never sees another message's ``order_id``.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

_LOG_CONTEXT: ContextVar[dict[str, str] | None] = ContextVar("log_context", default=None)


def bind(**values: str | None) -> Token:
    """Merge non-empty ``values`` into the current log context."""
    merged = {**(_LOG_CONTEXT.get() or {}), **{k: v for k, v in values.items() if v}}
    return _LOG_CONTEXT.set(merged)


def reset(token: Token) -> None:
    _LOG_CONTEXT.reset(token)


def current() -> dict[str, str]:
    return dict(_LOG_CONTEXT.get() or {})
