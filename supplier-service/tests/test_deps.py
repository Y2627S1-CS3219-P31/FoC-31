from __future__ import annotations

import pytest

from app.api.deps import require_admin
from app.errors import ForbiddenError, UnauthorizedError


def test_require_admin_allows_admin():
    # returns the user id, does not raise
    assert require_admin(x_user_id="u1", x_user_role="admin") == "u1"


def test_require_admin_rejects_client():
    with pytest.raises(ForbiddenError):
        require_admin(x_user_id="u1", x_user_role="client")


def test_require_admin_rejects_missing_role():
    with pytest.raises(UnauthorizedError):
        require_admin(x_user_id="u1", x_user_role=None)


def test_require_admin_rejects_missing_user():
    with pytest.raises(UnauthorizedError):
        require_admin(x_user_id=None, x_user_role="admin")
