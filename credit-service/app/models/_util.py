# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

import uuid
from datetime import UTC, datetime


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    """UTC now, stored naive (consistent with DateTime(timezone=False))."""
    return datetime.now(UTC).replace(tzinfo=None)
