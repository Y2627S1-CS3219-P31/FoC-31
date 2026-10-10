# AI-INFLUENCED: Sprint 1 order persistence fields implemented with Codex.
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Integer,
    String,
    func,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.services.lifecycle import OrderStatus


class OrderTable(Base):
    __tablename__ = "orders"

    __table_args__ = (
        CheckConstraint(
            "reward > 0",
            name="ck_orders_reward_positive",
        ),
        CheckConstraint(
            "char_length(btrim(name)) > 0",
            name="ck_orders_name_not_blank",
        ),
        CheckConstraint(
            "char_length(btrim(details)) > 0",
            name="ck_orders_details_not_blank",
        ),
        CheckConstraint(
            "char_length(btrim(supplier_id)) > 0",
            name="ck_orders_supplier_id_not_blank",
        ),
        CheckConstraint(
            "char_length(btrim(pickup_location)) > 0",
            name="ck_orders_pickup_location_not_blank",
        ),
        CheckConstraint(
            "char_length(btrim(delivery_location)) > 0",
            name="ck_orders_delivery_location_not_blank",
        ),
        CheckConstraint(
            "char_length(btrim(reservation_id)) > 0",
            name="ck_orders_reservation_id_not_blank",
        ),
    )

    order_id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[str] = mapped_column(String(255), nullable=False)
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

    courier_id: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        index=True,
    )

    requester_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
    )

    reservation_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        index=True,
    )

    pickup_location: Mapped[str] = mapped_column(String(255), nullable=False)
    delivery_location: Mapped[str] = mapped_column(String(255), nullable=False)

    status: Mapped[OrderStatus] = mapped_column(
        SqlEnum(OrderStatus, name="order_status"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
