# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

import json

import httpx
import pytest

from app.clients.credits import (
    CreditClient,
    CreditReservationRejectedError,
    CreditServiceUnavailableError,
)
from app.clients.suppliers import SupplierClient, SupplierNotFoundError


async def test_supplier_client_reads_active_status() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/suppliers/sup_001"
        return httpx.Response(200, json={"id": "sup_001", "active": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        supplier = await SupplierClient(http_client, "http://supplier-service:8000").get_supplier(
            "sup_001"
        )

    assert supplier.id == "sup_001"
    assert supplier.active is True


async def test_supplier_client_maps_not_found() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "not_found", "message": "Missing."})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(SupplierNotFoundError):
            await SupplierClient(http_client, "http://supplier-service:8000").get_supplier(
                "missing"
            )


async def test_credit_client_sends_order_and_authenticated_requester() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/credits/reservations"
        assert request.headers["X-User-Id"] == "user-1"
        assert json.loads(request.content) == {"order_id": 7, "amount": 5}
        return httpx.Response(201, json={"status": "reserved"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        await CreditClient(http_client, "http://credit-service:8000").reserve(
            order_id=7,
            requester_id="user-1",
            amount=5,
        )


async def test_credit_client_preserves_rejection_message() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={"code": "insufficient_credits", "message": "Insufficient credits."},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(CreditReservationRejectedError, match="Insufficient credits"):
            await CreditClient(http_client, "http://credit-service:8000").reserve(
                order_id=7,
                requester_id="user-1",
                amount=5,
            )


async def test_credit_client_treats_scaffold_as_unavailable() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(501, json={"detail": "not implemented"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(CreditServiceUnavailableError):
            await CreditClient(http_client, "http://credit-service:8000").reserve(
                order_id=7,
                requester_id="user-1",
                amount=5,
            )
