from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth import authenticate_admin, get_current_user  # noqa: E402


def test_local_admin_login_and_token_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVEL_ADMIN_USERNAME", "admin-test")
    monkeypatch.setenv("NOVEL_ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("NOVEL_JWT_SECRET", "test-secret")
    import auth

    auth.ADMIN_USERNAME = os.environ["NOVEL_ADMIN_USERNAME"]
    auth.ADMIN_PASSWORD = os.environ["NOVEL_ADMIN_PASSWORD"]
    auth.JWT_SECRET = os.environ["NOVEL_JWT_SECRET"]
    data = authenticate_admin("admin-test", "secret")
    assert data["token_type"] == "bearer"
    assert data["user"]["id"] == "local-admin"

    user = __import__("asyncio").run(get_current_user(data["access_token"]))
    assert user.platform_user_id == "local-admin"
    assert user.username == "admin-test"


def test_local_admin_login_rejects_wrong_password() -> None:
    import auth

    with pytest.raises(HTTPException) as error:
        auth.authenticate_admin(auth.ADMIN_USERNAME, "wrong-password")
    assert error.value.status_code == 401
