# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

import httpx

from foc_shared.auth import HEADER_USER_ID


class CreditClientError(Exception):
    pass


class CreditReservationRejectedError(CreditClientError):
    pass


class CreditServiceUnavailableError(CreditClientError):
    pass


def _response_message(response: httpx.Response, fallback: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        return fallback

    if isinstance(payload, dict):
        for key in ("message", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
    return fallback


class CreditClient:
    def __init__(self, http_client: httpx.AsyncClient, base_url: str) -> None:
        self._http_client = http_client
        self._base_url = base_url.rstrip("/")

    async def reserve(self, *, order_id: int, requester_id: str, amount: int) -> None:
        try:
            response = await self._http_client.post(
                f"{self._base_url}/credits/reservations",
                headers={HEADER_USER_ID: requester_id},
                json={"order_id": order_id, "amount": amount},
            )
        except httpx.RequestError as error:
            raise CreditServiceUnavailableError("Credit Service could not be reached.") from error

        if response.status_code in {400, 402, 404, 409, 422}:
            raise CreditReservationRejectedError(
                _response_message(response, "Credits could not be reserved for this order.")
            )
        if not response.is_success:
            raise CreditServiceUnavailableError(
                f"Credit Service returned status {response.status_code}."
            )
