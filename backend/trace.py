from __future__ import annotations

import contextvars
import logging
import os
import uuid
from pathlib import Path

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("novel_trace_id", default="")


def trace_id() -> str:
    return trace_id_var.get() or uuid.uuid4().hex


class TraceFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = trace_id()
        return True


def configure_logging() -> logging.Logger:
    formatter = logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | trace=%(trace_id)s | %(message)s")
    data_dir = os.getenv("NOVEL_DATA_DIR", "").strip()
    log_dir = Path(data_dir) / "logs" if data_dir else Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers = [logging.StreamHandler(), logging.FileHandler(log_dir / "novel.log", encoding="utf-8")]
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(TraceFilter())
    root = logging.getLogger()
    if not root.handlers:
        for handler in handlers:
            root.addHandler(handler)
    root.setLevel(logging.INFO)
    return logging.getLogger("novel")


logger = configure_logging()


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
        token = trace_id_var.set(request_trace_id)
        request.state.trace_id = request_trace_id
        try:
            response = await call_next(request)
        finally:
            trace_id_var.reset(token)
        response.headers["X-Trace-Id"] = request_trace_id
        return response
