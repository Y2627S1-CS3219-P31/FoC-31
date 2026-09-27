# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._util import _new_id, _utcnow


class ReservationStatus(str, enum.Enum):
    """Credit F2.2.1: exactly these three statuses."""

    RESERVED = "reserved"
    TRANSFERRED = "transferred"
    RELEASED = "released"


class CreditReservation(Base):
    """A pending hold on a requester's credits for one order.

    One reservation per order (unique order_id), which also makes repeated
    order-completion handling idempotent (Credit F3.2.1).
    """

    __tablename__ = "credit_reservations"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_credit_reservations_order_id"),
        CheckConstraint("amount > 0", name="ck_credit_reservations_amount_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("credit_accounts.user_id"), nullable=False, index=True
    )
    order_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ReservationStatus.RESERVED.value,
        server_default=ReservationStatus.RESERVED.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=_utcnow, onupdate=_utcnow
    )
