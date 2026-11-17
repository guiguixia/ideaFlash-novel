#!/usr/bin/env python3
"""独立的角色全书记忆实验服务；仅读取桌面端 SQLite，不导入业务代码。"""

from __future__ import annotations

import json
import math
import os
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx


ROOT = Path(__file__).resolve().parent
DEFAULT_DB = Path.home() / "Library/Application Support/剧本刷/novel.db"


def database_path() -> Path:
    url = os.getenv("NOVEL_DATABASE_URL", "")
    return Path(url.removeprefix("sqlite:///")) if url.startswith("sqlite:///") else DEFAULT_DB


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(database_path())
    db.row_factory = sqlite3.Row
    return db


def cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    denominator = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return numerator / denominator if denominator else 0.0


def post_json(url: str, headers: dict, payload: dict) -> dict:
    with httpx.Client(timeout=90, trust_env=False) as client:
        response = client.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()


def config(db: sqlite3.Connection) -> sqlite3.Row:
    row = db.execute("SELECT * FROM llm_configs WHERE id = 1").fetchone()
    if not row or not row["api_key"]:
        raise RuntimeError("桌面端尚未配置对话模型")
    if not all((row["embedding_base_url"], row["embedding_api_key"], row["embedding_model"])):
        raise RuntimeError("桌面端尚未配置 Embedding 服务")
    return row


def embedding(model_config: sqlite3.Row, text: str) -> list[float]:
    base = model_config["embedding_base_url"].rstrip("/")
    response = post_json(
        f"{base}/embeddings",
        {"Authorization": f"Bearer {model_config['embedding_api_key']}"},
        {"model": model_config["embedding_model"], "input": text, "encoding_format": "float"},
    )
    data = response.get("data") or []
    if not data or not isinstance(data[0].get("embedding"), list):
        raise RuntimeError("Embedding 服务未返回有效向量")
    return data[0]["embedding"]


def works() -> list[dict]:
    with connect() as db:
        rows = db.execute(
            "SELECT w.id, w.title, w.work_type, w.rag_status, w.rag_processed, w.rag_total, w.rag_error, COUNT(s.id) AS segments "
            "FROM works w LEFT JOIN source_segments s ON s.work_id = w.id "
            "GROUP BY w.id ORDER BY w.updated_at DESC"
        ).fetchall()
    return [{"id": row["id"], "title": row["title"], "workType": row["work_type"], "sourceSegmentCount": row["segments"], "ragIndex": {"status": row["rag_status"], "processed": row["rag_processed"], "total": row["rag_total"], "error": row["rag_error"]}} for row in rows]


def chapters(work_id: str) -> list[dict]:
    with connect() as db:
        rows = db.execute("SELECT sequence, title FROM source_segments WHERE work_id = ? ORDER BY sequence", (work_id,)).fetchall()
    return [{"sequence": row["sequence"], "title": row["title"]} for row in rows]


def recent_context(history: object) -> str:
    """仅保留最近问答用于指代消解，不将其视为小说事实。"""
    if not isinstance(history, list): return "（无）"
    rows = []
    for item in history[-8:]:
        if not isinstance(item, dict): continue
        role, content = str(item.get("role") or ""), str(item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content: continue
        rows.append(f"{'用户' if role == 'user' else '角色'}：{content[:1000]}")
    return "\n".join(rows)[-6000:] or "（无）"


def chat(work_id: str, chapter_sequence: int, role_name: str, message: str, history: object = None) -> dict:
    context = recent_context(history)
    rag_query = f"角色：{role_name}\n上下文：\n{context}\n本轮问题：{message}"
    with connect() as db:
        work = db.execute("SELECT id, title, work_type, rag_status FROM works WHERE id = ?", (work_id,)).fetchone()
        if not work: raise RuntimeError("作品不存在")
        if work["work_type"] == "original_story": raise RuntimeError("原创故事没有可检索的章节原文")
        if work["rag_status"] != "ready": raise RuntimeError("请先在桌面端构建完成该作品的角色知识库")
        chapter = db.execute("SELECT title FROM source_segments WHERE work_id = ? AND sequence = ?", (work_id, chapter_sequence)).fetchone()
        if not chapter: raise RuntimeError("所选章节不存在")
        model_config = config(db)
        vector = embedding(model_config, rag_query)
        rows = db.execute(
            "SELECT source_segment_order, source_title, content, embedding FROM rag_source_chunks WHERE work_id = ? AND source_segment_order <= ?",
            (work_id, chapter_sequence),
        ).fetchall()
        ranked = []
        for row in rows:
            try: score = cosine(vector, json.loads(row["embedding"]))
            except (TypeError, ValueError): continue
            bonus = 0.04 if role_name in row["content"] else 0
            ranked.append((score + bonus, row))
    evidence = [{"chapter": row["source_segment_order"], "title": row["source_title"], "content": row["content"][:500], "score": round(score, 4)} for score, row in sorted(ranked, reverse=True, key=lambda item: item[0])[:5]]
    if not evidence: raise RuntimeError("该章节范围内没有可用的知识库片段")
    evidence_text = "\n".join(f"- 第 {item['chapter']} 章《{item['title']}》：{item['content']}" for item in evidence)
    prompt = f'''你现在扮演小说《{work["title"]}》中的角色「{role_name}》。

当前时间点为第 {chapter_sequence} 章《{chapter["title"]}》。只能依据下方原文记忆证据回复；不能使用后续章节、模型常识或自行补写的剧情。证据不足时请以角色口吻坦诚说明不知道。不要剧透，也不要把用户提问当作已经发生的事。

角色：{role_name}

上下文（只用于理解“他”“后来”等指代、语气和未完话题；不得把其中内容当作小说事实）：
{context}

本轮问题：
{message}

RAG 原文证据（唯一可用于确认小说事实的来源）：
{evidence_text}

请用符合角色身份的自然中文简洁回复。'''
    base = model_config["base_url"].rstrip("/")
    response = post_json(
        f"{base}/chat/completions",
        {"Authorization": f"Bearer {model_config['api_key']}"},
        {"model": model_config["model"], "messages": [{"role": "user", "content": prompt}], "temperature": 0.55},
    )
    reply = (((response.get("choices") or [{}])[0].get("message") or {}).get("content") or "（模型未返回内容）").strip()
    return {"reply": reply, "model": model_config["model"], "evidence": evidence}


class Handler(BaseHTTPRequestHandler):
    def respond(self, code: int, data=None, msg="ok"):
        payload = json.dumps({"code": 0 if code < 400 else code, "data": data, "msg": msg}, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/works": return self.respond(200, works())
            if path.startswith("/api/works/") and path.endswith("/chapters"):
                return self.respond(200, chapters(path.split("/")[3]))
            relative = (ROOT / path.lstrip("/")).resolve()
            if relative == ROOT: relative = ROOT / "index.html"
            if ROOT not in relative.parents or not relative.is_file(): return self.respond(404, msg="页面不存在")
            body = relative.read_bytes(); mime = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}.get(relative.suffix, "application/octet-stream")
            self.send_response(200); self.send_header("Content-Type", mime); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        except Exception as exc: self.respond(500, msg=str(exc))

    def do_POST(self):
        if urlparse(self.path).path != "/api/chat": return self.respond(404, msg="接口不存在")
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            result = chat(str(body["work_id"]), int(body["chapter_sequence"]), str(body["role_name"]).strip(), str(body["message"]).strip(), body.get("history"))
            return self.respond(200, result)
        except Exception as exc: return self.respond(400, msg=str(exc))

    def log_message(self, *_args): pass


if __name__ == "__main__":
    host, port = "127.0.0.1", int(os.getenv("ROLE_MEMORY_EXPERIMENT_PORT", "8765"))
    print(f"角色全书记忆实验：http://{host}:{port}")
    print(f"仅读取数据库：{database_path()}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
