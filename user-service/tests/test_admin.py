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


def test_admin_list_search_and_status_filter(monkeypatch):
    actor_id = _register_verified(monkeypatch, "actor@u.nus.edu", "Ada Actor")
    target_id = _register_verified(monkeypatch, "target@u.nus.edu", "Tom Target")
    headers = {"X-User-Id": actor_id, "X-User-Role": "admin"}

    # search by name matches across the whole dataset (not just a page)
    by_name = client.get("/users/admin?q=Tom", headers=headers).json()
    assert by_name["total"] == 1
    assert by_name["items"][0]["id"] == target_id

    # search by email fragment
    by_email = client.get("/users/admin?q=actor@", headers=headers).json()
    assert by_email["total"] == 1
    assert by_email["items"][0]["id"] == actor_id

    # status filter reflects suspension state
    client.post(f"/users/admin/{target_id}/suspend", headers=headers)
    suspended = client.get("/users/admin?status=suspended", headers=headers).json()
    assert suspended["total"] == 1
    assert suspended["items"][0]["id"] == target_id

    active = client.get("/users/admin?status=active", headers=headers).json()
    assert all(not u["is_suspended"] for u in active["items"])
    assert target_id not in [u["id"] for u in active["items"]]


def test_admin_invalid_status_rejected(monkeypatch):
    actor_id = _register_verified(monkeypatch, "actor@u.nus.edu", "Actor")
    headers = {"X-User-Id": actor_id, "X-User-Role": "admin"}
    resp = client.get("/users/admin?status=bogus", headers=headers)
    assert resp.status_code == 422


def _make_admin(headers: dict, email: str, display_name: str) -> str:
    """Create a real admin account (DB role=admin) and return its id."""
    created = client.post(
        "/users/admin",
        headers=headers,
        json={
            "email": email,
            "password": "admin-password1",
            "display_name": display_name,
        },
    )
    assert created.status_code == 201
    return created.json()["id"]


def test_promote_and_demote_role(monkeypatch):
    actor_id = _register_verified(monkeypatch, "actor@u.nus.edu", "Actor")
    headers = {"X-User-Id": actor_id, "X-User-Role": "admin"}
    # actor must be a real admin in the DB so it isn't the "last admin" when we
    # demote the target below.
    admin_id = _make_admin(headers, "root@u.nus.edu", "Root Admin")
    target_id = _register_verified(monkeypatch, "target@u.nus.edu", "Target")
    admin_headers = {"X-User-Id": admin_id, "X-User-Role": "admin"}

    # promote client -> admin
    promoted = client.patch(
        f"/users/admin/{target_id}/role", headers=admin_headers, json={"role": "admin"}
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"

    # demote back to client (allowed: root admin still exists)
    demoted = client.patch(
        f"/users/admin/{target_id}/role", headers=admin_headers, json={"role": "client"}
    )
    assert demoted.status_code == 200
    assert demoted.json()["role"] == "client"


def test_role_self_demotion_blocked(monkeypatch):
    # bootstrap a real admin, then have that admin create a second admin who
    # attempts to demote themselves.
    seed_id = _register_verified(monkeypatch, "seed@u.nus.edu", "Seed")
    seed_headers = {"X-User-Id": seed_id, "X-User-Role": "admin"}
    self_admin_id = _make_admin(seed_headers, "self@u.nus.edu", "Self Admin")
    # a second real admin exists (self_admin below is created by seed which is
    # only an admin by header); make seed a real admin too so the last-admin
    # guard is not what trips.
    root_id = _make_admin(seed_headers, "root@u.nus.edu", "Root")
    root_headers = {"X-User-Id": root_id, "X-User-Role": "admin"}
    # ensure two real admins besides self: root + self_admin
    self_headers = {"X-User-Id": self_admin_id, "X-User-Role": "admin"}
    _ = root_headers

    resp = client.patch(
        f"/users/admin/{self_admin_id}/role", headers=self_headers, json={"role": "client"}
    )
    assert resp.status_code == 400
    assert "themselves" in resp.json()["detail"]


def test_last_admin_cannot_be_demoted(monkeypatch):
    seed_id = _register_verified(monkeypatch, "seed@u.nus.edu", "Seed")
    seed_headers = {"X-User-Id": seed_id, "X-User-Role": "admin"}
    # exactly one real admin in the DB
    only_admin_id = _make_admin(seed_headers, "only@u.nus.edu", "Only Admin")

    # another admin (by header) tries to demote the sole real admin
    resp = client.patch(
        f"/users/admin/{only_admin_id}/role",
        headers=seed_headers,
        json={"role": "client"},
    )
    assert resp.status_code == 400
    assert "last administrator" in resp.json()["detail"]


def test_role_update_missing_user_404(monkeypatch):
    actor_id = _register_verified(monkeypatch, "actor@u.nus.edu", "Actor")
    headers = {"X-User-Id": actor_id, "X-User-Role": "admin"}
    resp = client.patch(
        "/users/admin/does-not-exist/role", headers=headers, json={"role": "admin"}
    )
    assert resp.status_code == 404


def test_role_update_requires_admin(monkeypatch):
    actor_id = _register_verified(monkeypatch, "client@u.nus.edu", "Client")
    resp = client.patch(
        f"/users/admin/{actor_id}/role",
        headers={"X-User-Id": actor_id, "X-User-Role": "client"},
        json={"role": "admin"},
    )
    assert resp.status_code == 403
