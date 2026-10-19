from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.observability import OBS as _OBS
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


def _envelope(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorEnvelope(code=code, message=message).model_dump(),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Handlers emit the shared error envelope and count the business ``code``."""

    @app.exception_handler(ServiceError)
    async def _service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
        _OBS.record_error_code(_OBS.route_template(request.scope), exc.code)
        return _envelope(exc.code, exc.message, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        detail = first.get("msg", "Invalid request.")
        message = f"{loc}: {detail}" if loc else detail
        _OBS.record_error_code(_OBS.route_template(request.scope), "validation_error")
        return _envelope("validation_error", message, 422)

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        # Catch-all: no response ever falls outside the error envelope. The raw
        # exception detail is deliberately not leaked to the client.
        _OBS.record_error_code(_OBS.route_template(request.scope), "internal_error")
        return _envelope("internal_error", "An unexpected error occurred.", 500)
