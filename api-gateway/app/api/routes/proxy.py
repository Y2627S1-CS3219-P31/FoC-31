from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.services.exceptions import (
    InvalidTokenError,
    MissingBearerTokenError,
    RouteNotFoundError,
    UpstreamServiceError,
)
from app.services.gateway import GatewayService

router = APIRouter()
gateway = GatewayService()


@router.api_route(
    "/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]
)
async def proxy(path: str, request: Request) -> Response:
    full_path = f"/api/{path}"

    try:
        upstream = gateway.resolve(full_path)
    except RouteNotFoundError:
        return JSONResponse(
            status_code=404,
            content={"code": "not_found", "message": "No route for this path."},
        )

    try:
        injected_headers = await gateway.authorize(full_path, request)
    except MissingBearerTokenError:
        return JSONResponse(
            status_code=401,
            content={"code": "unauthorized", "message": "Missing bearer token."},
        )
    except InvalidTokenError:
        return JSONResponse(
            status_code=401,
            content={"code": "unauthorized", "message": "Invalid or expired token."},
        )

    try:
        return await gateway.forward(
            upstream=upstream,
            full_path=full_path,
            request=request,
            injected_headers=injected_headers,
        )
    except UpstreamServiceError:
        return JSONResponse(
            status_code=502,
            content={"code": "bad_gateway", "message": "Upstream service unavailable."},
        )
