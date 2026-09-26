from __future__ import annotations

import httpx
from fastapi import Request, Response

from app.services.auth import authenticate, build_trusted_headers, is_public
from app.services.exceptions import (
    InvalidTokenError,
    MissingBearerTokenError,
    RouteNotFoundError,
    UpstreamServiceError,
)
from app.services.routing import resolve_upstream
from foc_shared.auth import HEADER_USER_ID, HEADER_USER_ROLE

_STRIP_REQUEST_HEADERS = {
    "host",
    "content-length",
    "authorization",
    "connection",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    HEADER_USER_ID.lower(),
    HEADER_USER_ROLE.lower(),
}
_STRIP_RESPONSE_HEADERS = {"content-length", "transfer-encoding", "connection"}


class GatewayService:
    def resolve(self, full_path: str) -> str:
        upstream = resolve_upstream(full_path)
        if upstream is None:
            raise RouteNotFoundError(full_path)
        return upstream

    async def authorize(self, full_path: str, request: Request) -> dict[str, str]:
        if is_public(full_path):
            return {}

        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise MissingBearerTokenError()

        identity = await authenticate(token)
        if identity is None:
            raise InvalidTokenError()

        user_id, role = identity
        return build_trusted_headers(user_id, role)

    async def forward(
        self,
        *,
        upstream: str,
        full_path: str,
        request: Request,
        injected_headers: dict[str, str],
    ) -> Response:
        fwd_headers = {
            k: v for k, v in request.headers.items() if k.lower() not in _STRIP_REQUEST_HEADERS
        }
        fwd_headers.update(injected_headers)
        body = await request.body()

        backend_path = full_path[4:] if full_path.startswith("/api/") else full_path
        if not backend_path:
            backend_path = "/"

        try:
            async with httpx.AsyncClient(base_url=upstream, timeout=10.0) as client:
                upstream_resp = await client.request(
                    method=request.method,
                    url=backend_path,
                    headers=fwd_headers,
                    params=request.query_params,
                    content=body,
                )
        except httpx.RequestError as exc:
            raise UpstreamServiceError(str(exc)) from exc

        return Response(
            content=upstream_resp.content,
            status_code=upstream_resp.status_code,
            headers={
                k: v
                for k, v in upstream_resp.headers.items()
                if k.lower() not in _STRIP_RESPONSE_HEADERS
            },
            media_type=upstream_resp.headers.get("content-type"),
        )
