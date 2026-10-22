from __future__ import annotations

import builtins
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponseDTO(BaseModel, Generic[T]):
    code: int = 0
    data: T | None = None
    msg: str = "ok"
    traceId: str


class ApiListResponseDTO(BaseModel, Generic[T]):
    code: int = 0
    list: builtins.list[T] = Field(default_factory=builtins.list)
    msg: str = "ok"
    traceId: str
    pagination: dict[str, Any] | None = None
