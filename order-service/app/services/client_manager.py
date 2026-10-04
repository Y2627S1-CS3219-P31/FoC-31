import httpx
import os

from app.services.clients.supplier.client import SupplierClient
from app.services.clients.credit.client import CreditClient
from app.services.clients.transport import JsonHttpTransport

supplier_base_url = os.environ["SUPPLIER_SERVICE_URL"]
credit_base_url = os.environ["CREDIT_SERVICE_URL"]

_http_client: httpx.AsyncClient | None = None
_supplier_client: SupplierClient | None = None
_credit_client: CreditClient | None = None

def _start_remote_clients():
    global _http_client, _supplier_client, _credit_client

    _http_client = httpx.AsyncClient(
        timeout=2.5
    )

    transport = JsonHttpTransport(_http_client)

    _supplier_client = SupplierClient(
        base_url=f"{supplier_base_url}",
        transport=transport
    )

    _credit_client = CreditClient(
        base_url=f"{credit_base_url}",
        transport=transport
    )

async def close_remote_clients():
    global _http_client, _supplier_client, _credit_client
    
    if _http_client is not None:
        await _http_client.aclose()
    _http_client = None
    _supplier_client = None
    _credit_client = None

def get_supplier_client():
    if _supplier_client is None:
        raise RuntimeError("Remote clients have not been started.")
    return _supplier_client

def get_credit_client():
    if _credit_client is None:
         raise RuntimeError("Remote clients have not been started.")
    return _credit_client
