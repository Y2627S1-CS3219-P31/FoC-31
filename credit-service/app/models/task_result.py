# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._util import _utcnow


class TaskResultKind(str, enum.Enum):
    RELEASE = "release"
    AMEND = "amend"


class TaskResultOutcome(str, enum.Enum):
    RELEASED = "released"
    RELEASE_FAILED = "release_failed"
    AMENDED = "amended"
    AMEND_REJECTED = "amend_rejected"


class CreditTaskResult(Base):
    """Outcome of one Order Service task (`task_id`), used for idempotency.

    Order Service retries events and correlates the reply by `task_id`. Storing
    the outcome lets a repeated delivery re-publish *the same* reply instead of
    re-executing the credit operation, so a duplicate or stale task can never
    apply a second release/amendment.
    """

    __tablename__ = "credit_task_results"

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    reservation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    requester_id: Mapped[str] = mapped_column(String(36), nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=_utcnow, onupdate=_utcnow
    )
