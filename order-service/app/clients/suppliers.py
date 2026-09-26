# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import httpx


class SupplierClientError(Exception):
    pass


class SupplierNotFoundError(SupplierClientError):
    def __init__(self, supplier_id: str) -> None:
        self.supplier_id = supplier_id
        super().__init__(f"Supplier '{supplier_id}' was not found.")


class SupplierServiceUnavailableError(SupplierClientError):
    pass


@dataclass(frozen=True)
class SupplierRecord:
    id: str
    active: bool


class SupplierClient:
    def __init__(self, http_client: httpx.AsyncClient, base_url: str) -> None:
        self._http_client = http_client
        self._base_url = base_url.rstrip("/")

    async def get_supplier(self, supplier_id: str) -> SupplierRecord:
        encoded_supplier_id = quote(supplier_id, safe="")
        try:
            response = await self._http_client.get(
                f"{self._base_url}/suppliers/{encoded_supplier_id}"
            )
        except httpx.RequestError as error:
            raise SupplierServiceUnavailableError(
                "Supplier Service could not be reached."
            ) from error

        if response.status_code == 404:
            raise SupplierNotFoundError(supplier_id)
        if not response.is_success:
            raise SupplierServiceUnavailableError(
                f"Supplier Service returned status {response.status_code}."
            )

        try:
            payload = response.json()
            returned_id = payload["id"]
            active = payload["active"]
        except (KeyError, TypeError, ValueError) as error:
            raise SupplierServiceUnavailableError(
                "Supplier Service returned an invalid response."
            ) from error

        if not isinstance(returned_id, str) or not isinstance(active, bool):
            raise SupplierServiceUnavailableError("Supplier Service returned an invalid response.")
        return SupplierRecord(id=returned_id, active=active)
