from __future__ import annotations

from pydantic import BaseModel


class ErrorEnvelope(BaseModel):
    code: str
    message: str
