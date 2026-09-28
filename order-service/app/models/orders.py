# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("reward > 0", name="ck_orders_reward_positive"),
        Index("ix_orders_available", "status", "courier_id", "deadline"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    reward: Mapped[int] = mapped_column(Integer, nullable=False)
    deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    supplier_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
    )
    requester_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    courier_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    pickup_location: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_location: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="OPEN",
        server_default="OPEN",
    )
