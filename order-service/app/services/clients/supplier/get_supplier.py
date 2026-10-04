# AI-INFLUENCED: CI lint fixes applied with Codex; see ai/usage-log.md.
from app.services.client_manager import get_supplier_client
from app.services.clients.supplier.schemas import SupplierDetails


async def get_supplier(supplier_id: str) -> SupplierDetails:
    return await get_supplier_client().get_supplier(supplier_id)
