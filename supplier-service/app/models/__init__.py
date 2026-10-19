# AI-INFLUENCED: Register the Supplier Service outbox model with Codex.
from app.models.supplier import Supplier
from app.models.supplier_event_outbox import SupplierEventOutbox

__all__ = ["Supplier", "SupplierEventOutbox"]
