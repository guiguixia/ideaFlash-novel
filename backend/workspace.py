"""Novel 的工作区工件：数据库是正史，文件用于审计、导出与检索。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def novel_workspace(platform_user_id: str, novel_id: str) -> Path:
    data_dir = Path(os.getenv("NOVEL_DATA_DIR") or Path(__file__).resolve().parents[1] / "data")
    return data_dir / "workspaces" / platform_user_id / "novel" / novel_id


def write_artifact(platform_user_id: str, novel_id: str, relative_path: str, payload: Any) -> Path:
    path = novel_workspace(platform_user_id, novel_id) / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def read_artifact(platform_user_id: str, novel_id: str, relative_path: str) -> Any:
    path = novel_workspace(platform_user_id, novel_id) / relative_path
    return json.loads(path.read_text(encoding="utf-8"))


def write_blob(platform_user_id: str, novel_id: str, relative_path: str, payload: bytes) -> Path:
    path = novel_workspace(platform_user_id, novel_id) / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path
