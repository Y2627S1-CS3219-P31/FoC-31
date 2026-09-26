# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._util import _new_id, _utcnow


class TransactionKind(str, enum.Enum):
    """Credit F5: kinds recorded in a user's history."""

    ALLOCATION = "allocation"
    RESERVATION = "reservation"
    AMENDMENT = "amendment"
    TRANSFER = "transfer"
    RELEASE = "release"


class CreditTransaction(Base):
    """One entry of a user's credit history (Credit F5.1).

    `user_id` is the account whose balance changed; `counterparty_user_id` is
    the other associated user, when one exists (Credit F5.1.2). `amount` is
    signed: positive = income, negative = outflow (Credit F5.2).
    """

    __tablename__ = "credit_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    counterparty_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reservation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=_utcnow, index=True
    )
