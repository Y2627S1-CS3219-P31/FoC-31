# AI-INFLUENCED: Durable credit-release workflows implemented with Codex.
from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

PENDING = "pending"
COMPLETED = "completed"
FAILED = "failed"


class ReleaseAction(str, Enum):
    DELETE = "delete"
    CANCEL = "cancel"
    EXPIRE = "expire"


class OrderReleaseTask(Base):
    """Order Service's local state for a pending terminal action."""

    __tablename__ = "order_release_tasks"
    __table_args__ = (
        CheckConstraint(
            "action IN ('delete', 'cancel', 'expire')",
            name="ck_order_release_tasks_action",
        ),
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_order_release_tasks_status",
        ),
        Index(
            "uq_order_release_tasks_pending_order",
            "order_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
        Index(
            "uq_order_release_tasks_pending_reservation",
            "reservation_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    order_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    reservation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    requester_id: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=PENDING)
    reason: Mapped[str | None] = mapped_column(String(255))
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
