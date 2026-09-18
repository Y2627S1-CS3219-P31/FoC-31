from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_unknown_route_returns_404():
    resp = client.request("GET", "/api/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"
