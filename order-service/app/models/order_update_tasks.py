# AI-INFLUENCED: Durable pending order updates implemented with Codex.
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

PENDING = "pending"
COMPLETED = "completed"
REJECTED = "rejected"


class OrderUpdateTask(Base):
    """Order Service's local state for a pending proposed update."""

    __tablename__ = "order_update_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'completed', 'rejected')",
            name="ck_order_update_tasks_status",
        ),
        Index(
            "uq_order_update_tasks_pending_order",
            "order_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    order_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    requester_id: Mapped[str] = mapped_column(String, nullable=False)
    reservation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    proposed_order: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=PENDING)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rejection_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
