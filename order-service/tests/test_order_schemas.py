# AI-INFLUENCED: Sprint 1 Order Service schema tests generated with Codex.
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.orders import OrderCreate


def _valid_payload() -> dict[str, object]:
    return {
        "name": "Collect lunch",
        "details": "One vegetarian rice bowl",
        "reward": 5,
        "deadline": datetime.now(UTC) + timedelta(hours=2),
        "supplier_id": "sup_001",
        "pickup_location": "The Deck",
        "delivery_location": "COM3",
    }


@pytest.mark.parametrize(
    "field",
    ["name", "details", "supplier_id", "pickup_location", "delivery_location"],
)
def test_order_create_rejects_blank_required_strings(field: str) -> None:
    payload = _valid_payload()
    payload[field] = "   "

    with pytest.raises(ValidationError):
        OrderCreate.model_validate(payload)


def test_order_create_rejects_past_deadline() -> None:
    payload = _valid_payload()
    payload["deadline"] = datetime.now(UTC) - timedelta(seconds=1)

    with pytest.raises(ValidationError):
        OrderCreate.model_validate(payload)


def test_order_create_rejects_deadline_without_timezone() -> None:
    payload = _valid_payload()
    payload["deadline"] = datetime.now()

    with pytest.raises(ValidationError):
        OrderCreate.model_validate(payload)

