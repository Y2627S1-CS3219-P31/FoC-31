from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.errors import register_exception_handlers


def _app_that_raises() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> dict:
        raise RuntimeError("unexpected failure")

    return app


def test_unhandled_exception_returns_error_envelope():
    app = _app_that_raises()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 500
    body = resp.json()
    assert body["code"] == "internal_error"
    assert "message" in body
    # must never leak the raw exception text
    assert "unexpected failure" not in body["message"]
