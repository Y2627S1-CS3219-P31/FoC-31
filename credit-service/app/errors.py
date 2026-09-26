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
    @app.exception_handler(ServiceError)
    async def _service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
        return _envelope(exc.code, exc.message, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        detail = first.get("msg", "Invalid request.")
        message = f"{loc}: {detail}" if loc else detail
        return _envelope("validation_error", message, 422)

    @app.exception_handler(Exception)
    async def _unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
        # Catch-all: never leak internal details outside the error envelope.
        return _envelope("internal_error", "An unexpected error occurred.", 500)
