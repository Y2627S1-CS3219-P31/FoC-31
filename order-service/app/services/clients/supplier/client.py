# AI-INFLUENCED: CI lint fixes applied with Codex; see ai/usage-log.md.
from app.services.clients.client import JsonServiceClient
from app.services.clients.supplier.error import SupplierNotFoundError
from app.services.clients.supplier.schemas import SupplierDetails
from app.services.clients.transport import JsonHttpTransport


class SupplierClient(JsonServiceClient):
    def __init__(
        self,
        *,
        base_url: str,
        transport: JsonHttpTransport
    ):
        super().__init__(
            service_name="Supplier Service",
            base_url=base_url.rstrip("/"),
            transport=transport
        )

    async def get_supplier(self, supplier_id: str):
        return await self._request_model(
            method="GET",
            path=f"/suppliers/{supplier_id}",
            expected_status=200,
            response_model=SupplierDetails,
            endpoint_errors={
                (404, "not_found"): SupplierNotFoundError
            },
        )
