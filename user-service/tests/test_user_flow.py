from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services import notification

client = TestClient(app)

NUS_EMAIL = "alice@u.nus.edu"
PASSWORD = "correct-horse-battery1"


def _register(monkeypatch, email=NUS_EMAIL, password=PASSWORD, display_name="Alice"):
    captured: dict[str, str] = {}

    def _capture(to_email: str, code: str) -> None:
        captured["code"] = code

    monkeypatch.setattr(notification, "send_otp_email", _capture)
    resp = client.post(
        "/users/register",
        json={"email": email, "password": password, "display_name": display_name},
    )
    return resp, captured.get("code")


def test_register_success(monkeypatch):
    resp, code = _register(monkeypatch)
    assert resp.status_code == 201
    assert resp.json()["email"] == NUS_EMAIL
    assert code is not None and len(code) == 6


def test_register_rejects_non_nus_email(monkeypatch):
    resp, _ = _register(monkeypatch, email="alice@gmail.com")
    assert resp.status_code == 422


def test_register_rejects_short_password(monkeypatch):
    resp, _ = _register(monkeypatch, password="short")
    assert resp.status_code == 422


def test_login_before_verification_is_forbidden(monkeypatch):
    _register(monkeypatch)
    resp = client.post("/users/login", json={"email": NUS_EMAIL, "password": PASSWORD})
    assert resp.status_code == 403


def test_verify_with_wrong_code_returns_400(monkeypatch):
    _register(monkeypatch)
    resp = client.post("/users/otp/verify", json={"email": NUS_EMAIL, "code": "000000"})
    assert resp.status_code == 400


def test_otp_wrong_attempts_are_limited(monkeypatch):
    _register(monkeypatch)

    for _ in range(settings.otp_max_attempts - 1):
        response = client.post(
            "/users/otp/verify",
            json={"email": NUS_EMAIL, "code": "000000"},
        )
        assert response.status_code == 400

    locked = client.post(
        "/users/otp/verify",
        json={"email": NUS_EMAIL, "code": "000000"},
    )
    assert locked.status_code == 400
    assert "too many attempts" in locked.json()["detail"]


def test_full_register_verify_login_flow(monkeypatch):
    reg_resp, code = _register(monkeypatch)
    assert reg_resp.status_code == 201

    verify_resp = client.post("/users/otp/verify", json={"email": NUS_EMAIL, "code": code})
    assert verify_resp.status_code == 200

    login_resp = client.post("/users/login", json={"email": NUS_EMAIL, "password": PASSWORD})
    assert login_resp.status_code == 200
    body = login_resp.json()
    assert body["token_type"] == "bearer"
    assert "access_token" in body


def test_login_wrong_password_returns_401(monkeypatch):
    _register(monkeypatch)
    resp = client.post("/users/login", json={"email": NUS_EMAIL, "password": "wrong-password"})
    assert resp.status_code == 401


def test_reregister_unverified_email_issues_new_otp_instead_of_409(monkeypatch):
    first_resp, first_code = _register(monkeypatch)
    assert first_resp.status_code == 201

    monkeypatch.setattr(settings, "otp_resend_cooldown_seconds", 0)
    second_resp, second_code = _register(
        monkeypatch, password="a-different-password1", display_name="Alice B."
    )
    assert second_resp.status_code == 201
    assert second_resp.json()["id"] == first_resp.json()["id"]  # same account, not a new one
    assert second_code != first_code

    # The old code no longer works — only the latest issued code verifies.
    stale_resp = client.post("/users/otp/verify", json={"email": NUS_EMAIL, "code": first_code})
    assert stale_resp.status_code == 400

    fresh_resp = client.post("/users/otp/verify", json={"email": NUS_EMAIL, "code": second_code})
    assert fresh_resp.status_code == 200

    # The refreshed password from the second register() call is the one that works now.
    login_resp = client.post(
        "/users/login", json={"email": NUS_EMAIL, "password": "a-different-password1"}
    )
    assert login_resp.status_code == 200


def test_reregister_already_verified_email_still_conflicts(monkeypatch):
    reg_resp, code = _register(monkeypatch)
    client.post("/users/otp/verify", json={"email": NUS_EMAIL, "code": code})

    resp, _ = _register(monkeypatch)
    assert resp.status_code == 409


def test_resend_otp_for_unverified_account(monkeypatch):
    _, first_code = _register(monkeypatch)

    # The production cooldown is enabled; disable it for this unit test so
    # the test does not wait for a wall-clock interval.
    monkeypatch.setattr(settings, "otp_resend_cooldown_seconds", 0)

    captured: dict[str, str] = {}
    monkeypatch.setattr(
        notification, "send_otp_email", lambda email, code: captured.update(code=code)
    )
    resend_resp = client.post("/users/otp/resend", json={"email": NUS_EMAIL})
    assert resend_resp.status_code == 200
    new_code = captured["code"]
    assert new_code != first_code

    verify_resp = client.post("/users/otp/verify", json={"email": NUS_EMAIL, "code": new_code})
    assert verify_resp.status_code == 200


def test_resend_otp_unknown_email_returns_generic_success(monkeypatch):
    resp = client.post("/users/otp/resend", json={"email": "nobody@u.nus.edu"})
    assert resp.status_code == 200
    assert resp.json()["message"] == "Verification code sent. Check your email."


def test_resend_otp_already_verified_returns_generic_success(monkeypatch):
    reg_resp, code = _register(monkeypatch)
    client.post("/users/otp/verify", json={"email": NUS_EMAIL, "code": code})

    resp = client.post("/users/otp/resend", json={"email": NUS_EMAIL})
    assert resp.status_code == 200
    assert resp.json()["message"] == "Verification code sent. Check your email."


def test_profile_requires_identity_header(monkeypatch):
    resp = client.get("/users/me")
    assert resp.status_code == 401


def test_profile_round_trip(monkeypatch):
    reg_resp, code = _register(monkeypatch)
    user_id = reg_resp.json()["id"]
    client.post("/users/otp/verify", json={"email": NUS_EMAIL, "code": code})

    resp = client.get("/users/me", headers={"X-User-Id": user_id})
    assert resp.status_code == 200
    assert resp.json()["email"] == NUS_EMAIL

    update_resp = client.patch(
        "/users/me",
        json={"contact_number": "91234567"},
        headers={"X-User-Id": user_id},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["contact_number"] == "91234567"
