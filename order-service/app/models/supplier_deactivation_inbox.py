# AI-INFLUENCED: Remember completed supplier deactivation deliveries with Codex.
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SupplierDeactivationInbox(Base):
    __tablename__ = "supplier_deactivation_inbox"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
