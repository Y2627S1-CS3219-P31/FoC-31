# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

from fastapi import Request

from app.clients.credits import CreditClient
from app.clients.suppliers import SupplierClient


def get_supplier_client(request: Request) -> SupplierClient:
    return request.app.state.supplier_client


def get_credit_client(request: Request) -> CreditClient:
    return request.app.state.credit_client
