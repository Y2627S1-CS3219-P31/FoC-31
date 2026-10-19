# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Structured logging for credit-service.

Only the ``app`` logger tree is reconfigured: uvicorn keeps its own handlers,
so startup/access lines stay unchanged and nothing is logged twice. The format
carries the correlation values from :mod:`app.observability.context`
(``request_id``, ``user_id``, ``order_id``, ``task_id``), which is what makes
"metrics show a spike -> grep the log for that request id" possible.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from app.config import settings
from app.observability import context

# Extra ``logger.info(..., extra={...})`` keys promoted to the JSON payload.
_PROMOTED_EXTRA_KEYS = (
    "order_id",
    "task_id",
    "user_id",
    "queue",
    "routing_key",
    "event_type",
    "outcome",
    "code",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(context.current())
        for key in _PROMOTED_EXTRA_KEYS:
            value = record.__dict__.get(key)
            if value:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(UTC).strftime("%H:%M:%S")
        extra = " ".join(f"{k}={v}" for k, v in context.current().items())
        line = f"{ts} {record.levelname:<7} {record.name}: {record.getMessage()}"
        if extra:
            line = f"{line} [{extra}]"
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


def configure_logging() -> None:
    """Attach one handler to the ``app`` logger (idempotent)."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger = logging.getLogger("app")
    logger.setLevel(level)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter() if settings.log_json else TextFormatter())
    logger.addHandler(handler)
    # The root logger never sees ``app.*`` records, so uvicorn's own output is
    # left exactly as configured by its server settings.
    logger.propagate = False
