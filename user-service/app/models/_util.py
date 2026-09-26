from __future__ import annotations

import uuid
from datetime import UTC, datetime


def _new_id() -> str:
    return str(uuid.uuid4())

def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)