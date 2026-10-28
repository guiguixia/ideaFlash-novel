from __future__ import annotations

from dataclasses import dataclass

LOCAL_USER_ID = "local-admin"


@dataclass(frozen=True)
class CurrentUser:
    # 保留字段名以兼容现有数据库表；值永远是本地用户 ID，不再来自外部平台。
    platform_user_id: str
    email: str = ""
    username: str = "local-admin"


async def get_current_user() -> CurrentUser:
    return CurrentUser(platform_user_id=LOCAL_USER_ID)
