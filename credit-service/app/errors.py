# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Error hierarchy + FastAPI exception handlers.

Every error response uses the shared envelope ({code, message}) from
foc_shared.errors.ErrorEnvelope, including validation errors and unhandled
exceptions (consistent with supplier-service).
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.observability import metrics
from foc_shared.errors import ErrorEnvelope


class ServiceError(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(ServiceError):
    status_code = 404
    code = "not_found"


class ConflictError(ServiceError):
    status_code = 409
    code = "conflict"


class ForbiddenError(ServiceError):
    status_code = 403
    code = "forbidden"


class UnauthorizedError(ServiceError):
    status_code = 401
    code = "unauthorized"


class InsufficientCreditsError(ServiceError):
    """Credit F2.1.3: reservation/amendment rejected for lack of funds."""

    status_code = 409
    code = "insufficient_credits"


def _envelope(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorEnvelope(code=code, message=message).model_dump(),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Handlers record the business ``code`` as a metric label.

    The middleware already counts status codes and latency, so this is the only
    place that knows the enum-like ``code`` (``insufficient_credits`` etc.):
    no response body has to be parsed to tell a 409 for missing funds from a
    409 for a duplicate order.
    """

    @app.exception_handler(ServiceError)
    async def _service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
        metrics.record_error_code(metrics.route_template(request.scope), exc.code)
        return _envelope(exc.code, exc.message, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        detail = first.get("msg", "Invalid request.")
        message = f"{loc}: {detail}" if loc else detail
        metrics.record_error_code(metrics.route_template(request.scope), "validation_error")
        return _envelope("validation_error", message, 422)

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        # Catch-all: never leak internal details outside the error envelope.
        metrics.record_error_code(metrics.route_template(request.scope), "internal_error")
        return _envelope("internal_error", "An unexpected error occurred.", 500)
