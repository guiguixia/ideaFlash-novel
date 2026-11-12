"""微信 iLink 单机器人通道。

SDK 是可选依赖：未安装时，本地工作台仍可正常运行，只在用户主动连接微信时提示安装。
凭证只保存在 NOVEL_DATA_DIR/wechat/ 下，不进入数据库或仓库。
"""
from __future__ import annotations

import asyncio
import base64
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from trace import logger

try:
    from wechatbot import WeChatBot
    SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - 由用户是否安装可选依赖决定
    WeChatBot = None  # type: ignore[assignment,misc]
    SDK_AVAILABLE = False


MessageHandler = Callable[[str, str], Awaitable[str]]


def qr_data_url(content: str) -> str:
    """将 SDK 返回的二维码内容转为浏览器可展示 data URL。"""
    raw = (content or "").strip()
    if raw.startswith("data:image"):
        return raw
    if re.fullmatch(r"[A-Za-z0-9+/=\s]+", raw) and len(raw) > 200:
        try:
            base64.b64decode(raw, validate=True)
            return f"data:image/png;base64,{''.join(raw.split())}"
        except Exception:
            pass
    try:
        import qrcode
        image = qrcode.make(raw)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:
        logger.warning("WECHAT_QR_RENDER_FAILED", exc_info=True)
        return ""


@dataclass
class WeChatStatus:
    status: str = "idle"  # idle|pending|scanned|connected|expired|error
    qr_data_url: str = ""
    error: str = ""
    has_credentials: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "qrDataUrl": self.qr_data_url, "error": self.error, "hasCredentials": self.has_credentials, "sdkAvailable": SDK_AVAILABLE}


@dataclass
class WeChatRuntime:
    bot: Any = None
    task: asyncio.Task | None = None
    status: WeChatStatus = field(default_factory=WeChatStatus)


class WeChatChannel:
    def __init__(self, data_dir: Path, handler: MessageHandler):
        self.credential_path = data_dir / "wechat" / "credentials.json"
        self.handler = handler
        self.runtime = WeChatRuntime()
        self.lock = asyncio.Lock()

    def state(self) -> dict[str, Any]:
        self.runtime.status.has_credentials = self.credential_path.is_file()
        return self.runtime.status.to_dict()

    async def connect(self, *, force_login: bool = False) -> dict[str, Any]:
        if not SDK_AVAILABLE:
            self.runtime.status = WeChatStatus(status="error", error="未安装 wechatbot-sdk，请执行 pip install -r backend/requirements.txt")
            return self.state()
        async with self.lock:
            alive = self.runtime.task is not None and not self.runtime.task.done()
            if alive and not force_login:
                return self.state()
            if force_login:
                await self.disconnect()
            self.credential_path.parent.mkdir(parents=True, exist_ok=True)
            status = WeChatStatus(status="pending", has_credentials=self.credential_path.is_file())
            bot = WeChatBot(
                cred_path=str(self.credential_path),
                on_qr_url=self._on_qr,
                on_scanned=self._on_scanned,
                on_expired=self._on_expired,
                on_error=self._on_error,
            )
            self.runtime = WeChatRuntime(bot=bot, status=status)

            @bot.on_message
            async def on_message(message: Any) -> None:
                user_id = str(getattr(message, "sender_id", "") or getattr(message, "user_id", "") or "").strip()
                content = str(getattr(message, "text", "") or "").strip()
                if not user_id or not content:
                    return
                try:
                    reply = await self.handler(user_id, content)
                    if reply:
                        await bot.reply(message, reply)
                except Exception:
                    logger.exception("WECHAT_MESSAGE_HANDLE_FAILED user_id=%s", user_id)
                    await bot.reply(message, "处理消息时出现问题，请稍后重试。")

            async def run() -> None:
                try:
                    # SDK 的 run() 是给命令行脚本准备的同步包装，内部会调用
                    # asyncio.run()；FastAPI 已经运行在事件循环中，必须直接使用
                    # login/start 两个原生协程，否则会触发嵌套事件循环错误。
                    await bot.login()
                    self.runtime.status.status = "connected"
                    self.runtime.status.qr_data_url = ""
                    self.runtime.status.error = ""
                    await bot.start()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._on_error(exc)

            self.runtime.task = asyncio.create_task(run(), name="novel-wechat-ilink")
        return self.state()

    async def disconnect(self) -> None:
        runtime = self.runtime
        self.runtime = WeChatRuntime(status=WeChatStatus(status="idle", has_credentials=self.credential_path.is_file()))
        if runtime.task and not runtime.task.done():
            runtime.task.cancel()
            try:
                await runtime.task
            except (asyncio.CancelledError, Exception):
                pass
        bot = runtime.bot
        if bot is not None:
            stop = getattr(bot, "stop", None)
            if callable(stop):
                try:
                    stop()
                except Exception:
                    logger.debug("WECHAT_STOP_FAILED", exc_info=True)
            close = getattr(bot, "close", None)
            if callable(close):
                try:
                    result = close()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    logger.debug("WECHAT_CLOSE_FAILED", exc_info=True)

    def _on_qr(self, content: str) -> None:
        self.runtime.status.status = "pending"
        self.runtime.status.qr_data_url = qr_data_url(content)
        self.runtime.status.error = ""

    def _on_scanned(self) -> None:
        self.runtime.status.status = "scanned"

    def _on_expired(self) -> None:
        self.runtime.status.status = "expired"
        self.runtime.status.error = "二维码已过期，请重新连接"

    def _on_error(self, error: Any) -> None:
        self.runtime.status.status = "error"
        self.runtime.status.error = str(error)
        logger.warning("WECHAT_CHANNEL_ERROR error=%s", error)
