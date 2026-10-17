# AI-INFLUENCED: CI lint fixes applied with Codex; see ai/usage-log.md.
from app.services.clients.client import JsonServiceClient
from app.services.clients.supplier.error import (
    SupplierCategoryFilterError,
    SupplierNotFoundError,
)
from app.services.clients.supplier.schemas import SupplierDetails, SupplierList
from app.services.clients.transport import JsonHttpTransport

SUPPLIER_PAGE_SIZE = 100


class SupplierClient(JsonServiceClient):
    def __init__(self, *, base_url: str, transport: JsonHttpTransport):
        super().__init__(
            service_name="Supplier Service", base_url=base_url.rstrip("/"), transport=transport
        )

    async def get_supplier(self, supplier_id: str):
        return await self._request_model(
            method="GET",
            path=f"/suppliers/{supplier_id}",
            expected_status=200,
            response_model=SupplierDetails,
            endpoint_errors={(404, "not_found"): SupplierNotFoundError},
        )

    async def get_supplier_ids_by_categories(self, categories: list[str]) -> list[str]:
        supplier_ids: list[str] = []
        page = 1

        # Supplier results are paginated, so collect IDs from every matching page.
        while True:
            supplier_page = await self._request_model(
                method="GET",
                path="/suppliers",
                expected_status=200,
                response_model=SupplierList,
                endpoint_errors={(422, "validation_error"): SupplierCategoryFilterError},
                params=[
                    *(("category", category) for category in categories),
                    ("page", page),
                    ("page_size", SUPPLIER_PAGE_SIZE),
                    ("sort", "name"),
                    ("order", "asc"),
                ],
            )
            supplier_ids.extend(item.id for item in supplier_page.items)

            if not supplier_page.items or page * supplier_page.page_size >= supplier_page.total:
                break
            page += 1

        return list(dict.fromkeys(supplier_ids))
