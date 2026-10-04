# AI-INFLUENCED: Exception-handler tests generated with Codex.
from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api.error_handlers import register_exception_handlers
from app.services.clients.credit.error import (
    CreditAccountNotFoundError,
    CreditServiceUnavailableError,
    InsufficientCreditsError,
    ReservationForbiddenError,
    ReservationConflictError,
    ReservationNotFoundError,
)
from app.services.clients.errors import (
    RemoteServiceContractError,
    RemoteServiceUnavailableError,
    UnexpectedRemoteResponseError,
)
from app.services.clients.supplier.error import (
    SupplierInactiveError,
    SupplierNotFoundError,
    SupplierServiceContractError,
    SupplierServiceUnavailableError,
    UnexpectedSupplierResponseError,
)
from app.services.errors import (
    OrderAccessDeniedError,
    OrderDeletionError,
    OrderNotFoundError,
    OrderPersistenceError,
    OrderRetrievalError,
    OrderStateConflictError,
)


def _app_raising(exception_factory: Callable[[], Exception]) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/raise")
    async def raise_exception() -> None:
        raise exception_factory()

    return app


@pytest.mark.parametrize(
    ("exception_factory", "status_code", "code"),
    [
        (lambda: OrderNotFoundError("order-1"), 404, "order_not_found"),
        (lambda: OrderAccessDeniedError("order-1"), 403, "order_access_denied"),
        (
            lambda: OrderStateConflictError("order-1", "Invalid state."),
            409,
            "invalid_order_state",
        ),
        (lambda: SupplierNotFoundError("Supplier was not found."), 404, "supplier_not_found"),
        (lambda: SupplierInactiveError("sup-1"), 409, "supplier_inactive"),
        (
            lambda: CreditAccountNotFoundError("Credit account was not found."),
            404,
            "credit_account_not_found",
        ),
        (lambda: InsufficientCreditsError("Insufficient credits."), 409, "insufficient_credits"),
        (lambda: ReservationConflictError("Reservation exists."), 409, "reservation_conflict"),
        (
            lambda: ReservationNotFoundError("Reservation was not found."),
            502,
            "credit_reservation_not_found",
        ),
        (
            lambda: ReservationForbiddenError("Reservation access denied."),
            502,
            "credit_reservation_access_denied",
        ),
        (
            lambda: SupplierServiceUnavailableError("Supplier unavailable."),
            503,
            "dependency_unavailable",
        ),
        (
            lambda: CreditServiceUnavailableError("Credit unavailable."),
            503,
            "dependency_unavailable",
        ),
        (
            lambda: RemoteServiceUnavailableError(
                "Supplier timed out.",
                service_name="Supplier Service",
            ),
            503,
            "dependency_unavailable",
        ),
        (
            lambda: SupplierServiceContractError("Invalid Supplier response."),
            502,
            "dependency_invalid_response",
        ),
        (
            lambda: RemoteServiceContractError(
                "Invalid Supplier response.",
                service_name="Supplier Service",
                status_code=200,
            ),
            502,
            "dependency_invalid_response",
        ),
        (
            lambda: UnexpectedSupplierResponseError("Unexpected Supplier response."),
            502,
            "dependency_unexpected_response",
        ),
        (
            lambda: UnexpectedRemoteResponseError(
                "Unexpected Supplier response.",
                service_name="Supplier Service",
                status_code=418,
                code="teapot",
            ),
            502,
            "dependency_unexpected_response",
        ),
    ],
)
def test_known_exception_mapping(
    exception_factory: Callable[[], Exception],
    status_code: int,
    code: str,
) -> None:
    app = _app_raising(exception_factory)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/raise")

    assert response.status_code == status_code
    assert response.json()["code"] == code
    assert isinstance(response.json()["message"], str)


def test_request_validation_uses_error_envelope() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/items/{item_id}")
    async def get_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    with TestClient(app) as client:
        response = client.get("/items/not-an-integer")

    assert response.status_code == 422
    assert response.json() == {
        "code": "validation_error",
        "message": "The request contains invalid data.",
    }


def test_order_persistence_error_identifies_database_failure() -> None:
    app = _app_raising(lambda: OrderPersistenceError("order-1"))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/raise")

    assert response.status_code == 500
    assert response.json() == {
        "code": "order_persistence_failed",
        "message": "The order could not be created because database insertion failed.",
    }


@pytest.mark.parametrize(
    ("exception", "code", "message"),
    [
        (
            OrderRetrievalError("order-1"),
            "order_retrieval_failed",
            "Order data could not be retrieved because the database query failed.",
        ),
        (
            OrderDeletionError("order-1"),
            "order_deletion_failed",
            "The order could not be deleted because the database operation failed.",
        ),
    ],
)
def test_database_error_handlers(
    exception: Exception,
    code: str,
    message: str,
) -> None:
    app = _app_raising(lambda: exception)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/raise")

    assert response.status_code == 500
    assert response.json() == {"code": code, "message": message}


def test_framework_http_error_uses_error_envelope() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    with TestClient(app) as client:
        response = client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {"code": "not_found", "message": "Not Found"}


def test_response_validation_error_is_not_exposed() -> None:
    class Output(BaseModel):
        value: int

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/invalid", response_model=Output)
    async def invalid_response() -> dict[str, str]:
        return {"value": "not-an-integer"}

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/invalid")

    assert response.status_code == 500
    assert response.json() == {
        "code": "internal_error",
        "message": "An unexpected error occurred.",
    }


def test_unexpected_error_is_not_exposed() -> None:
    app = _app_raising(lambda: RuntimeError("sensitive implementation detail"))

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/raise")

    assert response.status_code == 500
    assert response.json() == {
        "code": "internal_error",
        "message": "An unexpected error occurred.",
    }
