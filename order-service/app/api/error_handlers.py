# AI-INFLUENCED: Centralized API exception mappings generated with Codex.
from __future__ import annotations

import logging
from dataclasses import dataclass
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from foc_shared.errors import ErrorEnvelope
from starlette.exceptions import HTTPException as StarletteHTTPException

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

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ErrorMapping:
    status_code: int
    code: str
    message: str
    expose_exception_message: bool = False


ERROR_MAPPINGS: dict[type[Exception], ErrorMapping] = {
    OrderNotFoundError: ErrorMapping(
        HTTPStatus.NOT_FOUND,
        "order_not_found",
        "The specified order was not found.",
        expose_exception_message=True,
    ),
    OrderAccessDeniedError: ErrorMapping(
        HTTPStatus.FORBIDDEN,
        "order_access_denied",
        "You do not have permission to access this order.",
        expose_exception_message=True,
    ),
    OrderStateConflictError: ErrorMapping(
        HTTPStatus.CONFLICT,
        "invalid_order_state",
        "The requested action is not valid for the order's current state.",
        expose_exception_message=True,
    ),
    SupplierNotFoundError: ErrorMapping(
        HTTPStatus.NOT_FOUND,
        "supplier_not_found",
        "The specified supplier was not found.",
        expose_exception_message=True,
    ),
    SupplierInactiveError: ErrorMapping(
        HTTPStatus.CONFLICT,
        "supplier_inactive",
        "The specified supplier is inactive.",
    ),
    CreditAccountNotFoundError: ErrorMapping(
        HTTPStatus.NOT_FOUND,
        "credit_account_not_found",
        "The requester does not have a credit account.",
        expose_exception_message=True,
    ),
    InsufficientCreditsError: ErrorMapping(
        HTTPStatus.CONFLICT,
        "insufficient_credits",
        "The requester does not have enough credits.",
        expose_exception_message=True,
    ),
    ReservationConflictError: ErrorMapping(
        HTTPStatus.CONFLICT,
        "reservation_conflict",
        "A conflicting credit reservation already exists.",
        expose_exception_message=True,
    ),
    ReservationNotFoundError: ErrorMapping(
        HTTPStatus.BAD_GATEWAY,
        "credit_reservation_not_found",
        "The order's credit reservation could not be found.",
    ),
    ReservationForbiddenError: ErrorMapping(
        HTTPStatus.BAD_GATEWAY,
        "credit_reservation_access_denied",
        "Credit Service rejected access to the order's reservation.",
    ),
    SupplierServiceUnavailableError: ErrorMapping(
        HTTPStatus.SERVICE_UNAVAILABLE,
        "dependency_unavailable",
        "Order processing is temporarily unavailable.",
    ),
    CreditServiceUnavailableError: ErrorMapping(
        HTTPStatus.SERVICE_UNAVAILABLE,
        "dependency_unavailable",
        "Order processing is temporarily unavailable.",
    ),
    RemoteServiceUnavailableError: ErrorMapping(
        HTTPStatus.SERVICE_UNAVAILABLE,
        "dependency_unavailable",
        "Order processing is temporarily unavailable.",
    ),
    SupplierServiceContractError: ErrorMapping(
        HTTPStatus.BAD_GATEWAY,
        "dependency_invalid_response",
        "A required service returned an invalid response.",
    ),
    RemoteServiceContractError: ErrorMapping(
        HTTPStatus.BAD_GATEWAY,
        "dependency_invalid_response",
        "A required service returned an invalid response.",
    ),
    UnexpectedSupplierResponseError: ErrorMapping(
        HTTPStatus.BAD_GATEWAY,
        "dependency_unexpected_response",
        "A required service returned an unexpected response.",
    ),
    UnexpectedRemoteResponseError: ErrorMapping(
        HTTPStatus.BAD_GATEWAY,
        "dependency_unexpected_response",
        "A required service returned an unexpected response.",
    ),
}


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    envelope = ErrorEnvelope(code=code, message=message)
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
    )


async def _handle_mapped_error(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    # Select the correct error mapping based on the exc
    mapping = ERROR_MAPPINGS[type(exc)]

    if mapping.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        context = {"error_type": type(exc).__name__}
        for field in ("service_name", "status_code", "code"):
            value = getattr(exc, field, None)
            if value is not None:
                context[f"remote_{field}"] = value
        logger.error(
            "Order API dependency failure",
            extra=context,
            exc_info=(type(exc), exc, exc.__traceback__),
        )

    message = mapping.message
    if mapping.expose_exception_message and str(exc).strip():
        message = str(exc).strip()

    return _error_response(mapping.status_code, mapping.code, message)


async def _handle_request_validation_error(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    logger.info(
        "Order API request validation failed",
        extra={"validation_errors": exc.errors()},
    )
    return _error_response(
        HTTPStatus.UNPROCESSABLE_ENTITY,
        "validation_error",
        "The request contains invalid data.",
    )


async def _handle_response_validation_error(
    _request: Request,
    exc: ResponseValidationError,
) -> JSONResponse:
    logger.error(
        "Order API produced an invalid response",
        extra={"validation_errors": exc.errors()},
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return _error_response(
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "internal_error",
        "An unexpected error occurred.",
    )


async def _handle_order_persistence_error(
    _request: Request,
    exc: OrderPersistenceError,
) -> JSONResponse:
    logger.error(
        "Order database insertion failed",
        extra={"order_id": exc.order_id},
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return _error_response(
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "order_persistence_failed",
        "The order could not be created because database insertion failed.",
    )


async def _handle_order_retrieval_error(
    _request: Request,
    exc: OrderRetrievalError,
) -> JSONResponse:
    logger.error(
        "Order database retrieval failed",
        extra={"order_id": exc.order_id},
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return _error_response(
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "order_retrieval_failed",
        "Order data could not be retrieved because the database query failed.",
    )


async def _handle_order_deletion_error(
    _request: Request,
    exc: OrderDeletionError,
) -> JSONResponse:
    logger.error(
        "Order database deletion failed",
        extra={"order_id": exc.order_id},
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return _error_response(
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "order_deletion_failed",
        "The order could not be deleted because the database operation failed.",
    )


async def _handle_http_exception(
    _request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    if isinstance(exc.detail, str):
        message = exc.detail
    else:
        try:
            message = HTTPStatus(exc.status_code).phrase
        except ValueError:
            message = "The request could not be completed."

    code = "not_found" if exc.status_code == HTTPStatus.NOT_FOUND else "http_error"
    return _error_response(exc.status_code, code, message)


async def _handle_unexpected_error(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.error(
        "Unhandled Order Service error",
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return _error_response(
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "internal_error",
        "An unexpected error occurred.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all Order API exception-to-response mappings."""

    for exception_type in ERROR_MAPPINGS:
        app.add_exception_handler(exception_type, _handle_mapped_error)

    app.add_exception_handler(OrderPersistenceError, _handle_order_persistence_error)
    app.add_exception_handler(OrderRetrievalError, _handle_order_retrieval_error)
    app.add_exception_handler(OrderDeletionError, _handle_order_deletion_error)
    app.add_exception_handler(RequestValidationError, _handle_request_validation_error)
    app.add_exception_handler(ResponseValidationError, _handle_response_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected_error)
