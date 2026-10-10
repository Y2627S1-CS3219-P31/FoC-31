from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_register_rejects_unknown_fields():
    response = client.post(
        "/users/register",
        json={
            "email": "alice@u.nus.edu",
            "password": "correct-horse1",
            "display_name": "Alice",
            "unexpected": "reject me",
        },
    )
    assert response.status_code == 422


def test_register_validates_name_and_singapore_contact_number():
    response = client.post(
        "/users/register",
        json={
            "email": "alice@u.nus.edu",
            "password": "correct-horse1",
            "display_name": "A" * 51,
            "contact_number": "12345678",
        },
    )
    assert response.status_code == 422


def test_profile_update_rejects_unknown_fields_and_invalid_values():
    response = client.patch(
        "/users/me",
        headers={"X-User-Id": "user-1"},
        json={
            "display_name": "A" * 51,
            "contact_number": "12345678",
            "unexpected": "reject me",
        },
    )
    assert response.status_code == 422
