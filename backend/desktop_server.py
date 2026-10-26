"""Electron 打包后的本地 API 服务入口。"""
from __future__ import annotations

import os

import uvicorn
from main import app


def main() -> None:
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.getenv("NOVEL_API_PORT", "8004")),
        log_level=os.getenv("NOVEL_LOG_LEVEL", "warning"),
    )


if __name__ == "__main__":
    main()
