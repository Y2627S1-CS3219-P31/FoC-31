from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services import notification

client = TestClient(app)


def _register_verified(monkeypatch, email: str, display_name: str) -> str:
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        notification,
        "send_otp_email",
        lambda to_email, code: captured.update(code=code),
    )
    response = client.post(
        "/users/register",
        json={
            "email": email,
            "password": "correct-horse1",
            "display_name": display_name,
        },
    )
    assert response.status_code == 201
    user_id = response.json()["id"]
    verify = client.post(
        "/users/otp/verify", json={"email": email, "code": captured["code"]}
    )
    assert verify.status_code == 200
    return user_id


def test_admin_create_list_suspend_and_unsuspend(monkeypatch):
    actor_id = _register_verified(monkeypatch, "actor@u.nus.edu", "Actor")
    target_id = _register_verified(monkeypatch, "target@u.nus.edu", "Target")
    headers = {"X-User-Id": actor_id, "X-User-Role": "admin"}

    created = client.post(
        "/users/admin",
        headers=headers,
        json={
            "email": "new-admin@u.nus.edu",
            "password": "admin-password1",
            "display_name": "New Admin",
        },
    )
    assert created.status_code == 201
    assert created.json()["role"] == "admin"
    assert created.json()["email_verified"] is True

    listed = client.get("/users/admin?limit=100", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 3

    suspended = client.post(f"/users/admin/{target_id}/suspend", headers=headers)
    assert suspended.status_code == 200
    assert suspended.json()["is_suspended"] is True

    unsuspended = client.post(f"/users/admin/{target_id}/unsuspend", headers=headers)
    assert unsuspended.status_code == 200
    assert unsuspended.json()["is_suspended"] is False


def test_admin_routes_reject_client_role(monkeypatch):
    actor_id = _register_verified(monkeypatch, "client@u.nus.edu", "Client")
    response = client.get(
        "/users/admin",
        headers={"X-User-Id": actor_id, "X-User-Role": "client"},
    )
    assert response.status_code == 403
