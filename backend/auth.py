from __future__ import annotations

import hmac
import os
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from trace import logger

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
LOCAL_USER_ID = "local-admin"
ADMIN_USERNAME = os.getenv("NOVEL_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("NOVEL_ADMIN_PASSWORD", "change-me")
JWT_SECRET = os.getenv("NOVEL_JWT_SECRET") or os.getenv("JWT_SECRET") or "dev-secret-change-in-production"


@dataclass(frozen=True)
class CurrentUser:
    # 保留字段名以兼容现有数据库表；值永远是本地用户 ID，不再来自外部平台。
    platform_user_id: str
    email: str = ""
    username: str = ADMIN_USERNAME


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="登录状态无效或已过期")


def authenticate_admin(username: str, password: str) -> dict:
    if not hmac.compare_digest((username or "").strip(), ADMIN_USERNAME) or not hmac.compare_digest(password or "", ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = jwt.encode(
        {"sub": LOCAL_USER_ID, "username": ADMIN_USERNAME, "email": "", "type": "novel-local"},
        JWT_SECRET,
        algorithm="HS256",
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": LOCAL_USER_ID, "username": ADMIN_USERNAME, "email": ""},
    }


async def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except JWTError as exc:
        logger.warning("local Novel JWT verification failed: %s", exc)
        raise _unauthorized() from exc
    if payload.get("type") != "novel-local" or payload.get("sub") != LOCAL_USER_ID:
        raise _unauthorized()
    return CurrentUser(
        platform_user_id=LOCAL_USER_ID,
        email=str(payload.get("email") or ""),
        username=str(payload.get("username") or ADMIN_USERNAME),
    )
