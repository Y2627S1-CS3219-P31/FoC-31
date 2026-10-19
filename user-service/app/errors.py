# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
"""Shared error envelope + exception handlers for user-service.

Historically this service raised bare ``HTTPException(detail=...)``, so its
errors came back as ``{"detail": "..."}`` while the gateway and the other
services answer ``{"code", "message"}``. This module aligns the wire format and
records the business ``code`` for the observability layer (the handlers are the
only place that knows both the status and the message).

Codes are derived in two steps: an exact/prefix match on the message when the
cause is known (``otp_locked``, ``email_already_registered``, ...), otherwise a
bucket for the HTTP status. That keeps the contract stable while giving the
metrics real dimensions.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.observability import OBS
from foc_shared.errors import ErrorEnvelope

_STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    503: "service_unavailable",
}

# Longest/most specific prefixes first: the first match wins.
_MESSAGE_CODES: tuple[tuple[str, str], ...] = (
    ("email already registered", "email_already_registered"),
    ("please wait before requesting another code", "otp_rate_limited"),
    ("verification email could not be sent", "email_delivery_failed"),
    ("authentication is not configured", "authentication_unavailable"),
    ("account suspended", "account_suspended"),
    ("email not verified", "email_not_verified"),
    ("invalid email or password", "invalid_credentials"),
    ("cannot demote the last administrator", "last_admin_guard"),
    ("an administrator cannot", "admin_guard"),
    ("administrator accounts cannot be suspended here", "admin_guard"),
    ("administrator role required", "forbidden"),
    ("user not found", "not_found"),
    ("missing gateway identity headers", "unauthorized"),
    ("missing identity header", "unauthorized"),
    ("incorrect code", "invalid_otp"),
    ("code expired", "otp_expired"),
    ("too many attempts", "otp_locked"),
    ("no active code", "otp_not_found"),
    ("code already used", "otp_already_used"),
    ("no account with that email", "invalid_otp"),
)


def _code_for(status_code: int, message: str) -> str:
    for prefix, code in _MESSAGE_CODES:
        if message.startswith(prefix):
            return code
    return _STATUS_CODES.get(status_code, "http_error")


def _envelope(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorEnvelope(code=code, message=message).model_dump(),
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        code = _code_for(exc.status_code, message)
        OBS.record_error_code(OBS.route_template(request.scope), code)
        return _envelope(code, message, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        detail = first.get("msg", "Invalid request.")
        message = f"{loc}: {detail}" if loc else detail
        OBS.record_error_code(OBS.route_template(request.scope), "validation_error")
        return _envelope("validation_error", message, 422)

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        # Never leak internal details to the client.
        OBS.record_error_code(OBS.route_template(request.scope), "internal_error")
        return _envelope("internal_error", "An unexpected error occurred.", 500)
