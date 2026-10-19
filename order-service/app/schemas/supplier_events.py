# AI-INFLUENCED: Validate Supplier-owned deactivation facts with Codex.
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

SUPPLIER_EVENTS_EXCHANGE = "foc.supplier.events"


class SupplierDeactivatedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["SupplierDeactivated"] = "SupplierDeactivated"
    event_id: str
    supplier_id: str
    timestamp: datetime
