# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._util import _utcnow


class CreditAccount(Base):
    """One credit account per registered user (Credit F1).

    Invariants enforced at the database level (Credit N1.1.1):
    neither balance may ever be negative.
    """

    __tablename__ = "credit_accounts"
    __table_args__ = (
        CheckConstraint("available_balance >= 0", name="ck_credit_accounts_available_non_negative"),
        CheckConstraint("reserved_balance >= 0", name="ck_credit_accounts_reserved_non_negative"),
    )

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    available_balance: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    reserved_balance: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=_utcnow, onupdate=_utcnow
    )
