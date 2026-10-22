from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth import authenticate_admin, get_current_user  # noqa: E402


def test_local_admin_login_and_token_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVEL_JWT_SECRET", "test-secret")
    import auth

    auth.JWT_SECRET = "test-secret"
    data = authenticate_admin("ideaFlash", "ideaFlash")
    assert data["token_type"] == "bearer"
    assert data["user"]["id"] == "local-admin"

    user = __import__("asyncio").run(get_current_user(data["access_token"]))
    assert user.platform_user_id == "local-admin"
    assert user.username == "ideaFlash"


def test_local_admin_login_rejects_wrong_password() -> None:
    import auth

    with pytest.raises(HTTPException) as error:
        auth.authenticate_admin(auth.ADMIN_USERNAME, "wrong-password")
    assert error.value.status_code == 401
