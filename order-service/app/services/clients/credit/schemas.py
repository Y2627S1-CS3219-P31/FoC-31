# AI-INFLUENCED: CI lint fixes applied with Codex; see ai/usage-log.md.
from datetime import datetime

from pydantic import BaseModel


class ReservationDetails(BaseModel):
    id: str
    user_id: str
    order_id: str
    amount: int
    status: str
    created_at: datetime
    updated_at: datetime
