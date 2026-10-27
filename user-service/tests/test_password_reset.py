from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services import notification, otp
from app.services.exceptions import NotificationDeliveryError

client = TestClient(app)

EMAIL = "bob@u.nus.edu"
OLD_PASSWORD = "old-password1"
NEW_PASSWORD = "new-password2"
GENERIC_FORGOT = "If an account exists for that email, a reset code has been sent."
GENERIC_RESET_ERROR = "invalid or expired reset code"


@pytest.fixture
def mailbox(monkeypatch):
    """Capture every OTP email by kind instead of sending it."""
    sent: dict[str, list[tuple[str, str]]] = {"verification": [], "reset": []}
    monkeypatch.setattr(
        notification, "send_otp_email", lambda to, code: sent["verification"].append((to, code))
    )
    monkeypatch.setattr(
        notification,
        "send_password_reset_email",
        lambda to, code: sent["reset"].append((to, code)),
    )
    return sent


@pytest.fixture
def no_cooldown(monkeypatch):
    monkeypatch.setattr(settings, "otp_resend_cooldown_seconds", 0)


def _verified_user(mailbox, email=EMAIL, password=OLD_PASSWORD):
    resp = client.post(
        "/users/register",
        json={"email": email, "password": password, "display_name": "Bob"},
    )
    assert resp.status_code == 201
    code = mailbox["verification"][-1][1]
    assert client.post("/users/otp/verify", json={"email": email, "code": code}).status_code == 200


def _forgot(email=EMAIL):
    return client.post("/users/password/forgot", json={"email": email})


def _reset(code, *, email=EMAIL, new_password=NEW_PASSWORD):
    return client.post(
        "/users/password/reset",
        json={"email": email, "code": code, "new_password": new_password},
    )


def _login(password, email=EMAIL):
    return client.post("/users/login", json={"email": email, "password": password})


# ── happy path ───────────────────────────────────────────────────────────────


def test_full_forgot_reset_login_flow(mailbox):
    _verified_user(mailbox)

    resp = _forgot()
    assert resp.status_code == 200
    assert resp.json()["message"] == GENERIC_FORGOT
    assert len(mailbox["reset"]) == 1
    to, code = mailbox["reset"][0]
    assert to == EMAIL and len(code) == 6

    assert _reset(code).status_code == 200
    assert _login(NEW_PASSWORD).status_code == 200
    assert _login(OLD_PASSWORD).status_code == 401


def test_reset_email_uses_reset_template_not_verification(mailbox):
    _verified_user(mailbox)
    verification_emails = len(mailbox["verification"])
    _forgot()
    assert len(mailbox["reset"]) == 1
    assert len(mailbox["verification"]) == verification_emails


def test_email_is_normalised(mailbox):
    _verified_user(mailbox)
    assert _forgot("  BOB@U.NUS.EDU ").status_code == 200
    code = mailbox["reset"][0][1]
    assert _reset(code, email="Bob@U.nus.edu").status_code == 200
    assert _login(NEW_PASSWORD).status_code == 200


# ── no account enumeration ───────────────────────────────────────────────────


def test_unknown_email_gets_same_response_and_no_email(mailbox):
    resp = _forgot("nobody@u.nus.edu")
    assert resp.status_code == 200
    assert resp.json()["message"] == GENERIC_FORGOT
    assert mailbox["reset"] == []


def test_unverified_account_gets_no_reset_code(mailbox):
    client.post(
        "/users/register",
        json={"email": EMAIL, "password": OLD_PASSWORD, "display_name": "Bob"},
    )
    resp = _forgot()
    assert resp.status_code == 200
    assert mailbox["reset"] == []


def test_delivery_failure_still_returns_generic_200(mailbox, monkeypatch):
    _verified_user(mailbox)

    def _boom(to, code):
        raise NotificationDeliveryError("smtp down")

    monkeypatch.setattr(notification, "send_password_reset_email", _boom)
    resp = _forgot()
    assert resp.status_code == 200
    assert resp.json()["message"] == GENERIC_FORGOT


def test_reset_errors_are_uniform(mailbox):
    """Unknown email, no code requested, and a wrong code all look the same."""
    _verified_user(mailbox)

    unknown = _reset("123456", email="nobody@u.nus.edu")
    no_code_requested = _reset("123456")
    _forgot()
    wrong_code = _reset("000000" if mailbox["reset"][0][1] != "000000" else "111111")

    for resp in (unknown, no_code_requested, wrong_code):
        assert resp.status_code == 400
        assert resp.json()["detail"] == GENERIC_RESET_ERROR


# ── code rules ───────────────────────────────────────────────────────────────


def test_code_is_single_use(mailbox):
    _verified_user(mailbox)
    _forgot()
    code = mailbox["reset"][0][1]
    assert _reset(code).status_code == 200
    again = _reset(code, new_password="another-password3")
    assert again.status_code == 400
    assert _login(NEW_PASSWORD).status_code == 200


def test_wrong_attempts_lock_the_code(mailbox):
    _verified_user(mailbox)
    _forgot()
    code = mailbox["reset"][0][1]
    wrong = "000000" if code != "000000" else "111111"

    for _ in range(settings.otp_max_attempts):
        assert _reset(wrong).status_code == 400

    # Even the right code no longer works once the attempt limit is reached.
    assert _reset(code).status_code == 400
    assert _login(OLD_PASSWORD).status_code == 200


def test_expired_code_is_rejected(mailbox, monkeypatch):
    _verified_user(mailbox)
    monkeypatch.setattr(otp, "OTP_TTL", timedelta(seconds=-1))
    _forgot()
    code = mailbox["reset"][0][1]
    assert _reset(code).status_code == 400
    assert _login(OLD_PASSWORD).status_code == 200


def test_cooldown_silently_skips_second_email(mailbox, monkeypatch):
    monkeypatch.setattr(settings, "otp_resend_cooldown_seconds", 60)
    _verified_user(mailbox)
    first = _forgot()
    second = _forgot()
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert len(mailbox["reset"]) == 1


def test_only_latest_code_works_and_reset_burns_older_codes(mailbox, no_cooldown):
    _verified_user(mailbox)
    _forgot()
    _forgot()
    older, latest = mailbox["reset"][0][1], mailbox["reset"][1][1]
    if older != latest:
        assert _reset(older).status_code == 400
    assert _reset(latest).status_code == 200
    assert _reset(older, new_password="another-password3").status_code == 400


def test_verification_code_cannot_reset_password(mailbox):
    """An unverified account's email-verification code cannot be used as a reset code."""
    client.post(
        "/users/register",
        json={"email": EMAIL, "password": OLD_PASSWORD, "display_name": "Bob"},
    )
    verification_code = mailbox["verification"][-1][1]
    assert _reset(verification_code).status_code == 400


# ── validation ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad_password", ["short1", "lettersonly", "12345678"])
def test_weak_new_password_is_rejected(mailbox, bad_password):
    _verified_user(mailbox)
    _forgot()
    code = mailbox["reset"][0][1]
    assert _reset(code, new_password=bad_password).status_code == 422
    # The code was not consumed by the rejected request.
    assert _reset(code).status_code == 200


@pytest.mark.parametrize("bad_code", ["12345", "1234567", "abcdef"])
def test_malformed_code_is_rejected(bad_code):
    assert _reset(bad_code).status_code == 422


def test_suspended_user_can_reset_but_still_cannot_log_in(mailbox):
    """Resetting a password must not bypass a suspension."""
    admin_headers = {"X-User-Id": "some-admin-id", "X-User-Role": "admin"}

    _verified_user(mailbox)
    users = client.get("/users/admin", headers=admin_headers).json()["items"]
    bob_id = next(u["id"] for u in users if u["email"] == EMAIL)
    suspended = client.post(f"/users/admin/{bob_id}/suspend", headers=admin_headers)
    assert suspended.status_code == 200

    _forgot()
    code = mailbox["reset"][0][1]
    assert _reset(code).status_code == 200
    assert _login(NEW_PASSWORD).status_code == 403
