# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.api.routes import health
from app.auth import is_public
from app.routing import resolve_upstream, resolve_upstream_path
from foc_shared.auth import HEADER_USER_ID, HEADER_USER_ROLE

app = FastAPI(title="FoC API Gateway", version="0.1.0")
app.include_router(health.router)
_STRIP_REQUEST_HEADERS = {
    "host",
    "content-length",
    HEADER_USER_ID.lower(),
    HEADER_USER_ROLE.lower(),
}


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(path: str, request: Request) -> Response:
    full_path = f"/api/{path}"
    upstream = resolve_upstream(full_path)
    if upstream is None:
        return JSONResponse(
            status_code=404, content={"code": "not_found", "message": "No route for this path."}
        )
    injected: dict[str, str] = {}
    if not is_public(full_path):
        pass
    fwd_headers = {
        k: v for k, v in request.headers.items() if k.lower() not in _STRIP_REQUEST_HEADERS
    }
    fwd_headers.update(injected)
    body = await request.body()
    async with httpx.AsyncClient(base_url=upstream, timeout=10.0) as client:
        upstream_resp = await client.request(
            method=request.method,
            url=resolve_upstream_path(full_path),
            headers=fwd_headers,
            params=request.query_params,
            content=body,
        )
    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers={
            k: v
            for k, v in upstream_resp.headers.items()
            if k.lower() not in {"content-length", "transfer-encoding", "connection"}
        },
        media_type=upstream_resp.headers.get("content-type"),
    )
