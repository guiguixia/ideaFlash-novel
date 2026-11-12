#!/usr/bin/env python3
"""与业务隔离的小说角色 RAG 实验。

构建命令只读取本地 source_segments；向量索引写入本目录 output，
不会写入业务数据库，也不会改变任何私聊/副本调用链路。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = Path.home() / "Library/Application Support/剧本刷/novel.db"
OUTPUT = Path(__file__).resolve().parent / "output"
DEFAULT_INDEX = OUTPUT / "doupo-50.jsonl"


def chunks(text: str, size: int, overlap: int):
    step = size - overlap
    if step <= 0:
        raise ValueError("chunk-size 必须大于 overlap")
    return [text[offset : offset + size].strip() for offset in range(0, len(text), step) if text[offset : offset + size].strip()]


def source_chunks(db_path: Path, work_title: str, chapter_limit: int, size: int, overlap: int):
    database = sqlite3.connect(db_path)
    database.row_factory = sqlite3.Row
    work = database.execute(
        "SELECT id, title FROM works WHERE title = ? ORDER BY created_at DESC LIMIT 1", (work_title,)
    ).fetchone()
    if not work:
        raise RuntimeError(f"未找到作品《{work_title}》：{db_path}")
    rows = database.execute(
        "SELECT sequence, title, content FROM source_segments WHERE work_id = ? AND sequence <= ? ORDER BY sequence",
        (work["id"], chapter_limit),
    ).fetchall()
    if not rows:
        raise RuntimeError(f"《{work_title}》没有前 {chapter_limit} 章来源资料")
    result = []
    for row in rows:
        for index, text in enumerate(chunks(row["content"], size, overlap)):
            result.append(
                {
                    "chapter": row["sequence"],
                    "chapterTitle": row["title"],
                    "chunk": index,
                    "text": text,
                }
            )
    return result


def embedding_config():
    base_url = os.getenv("RAG_EMBEDDING_BASE_URL", "").rstrip("/")
    api_key = os.getenv("RAG_EMBEDDING_API_KEY", "")
    model = os.getenv("RAG_EMBEDDING_MODEL", "")
    if not all((base_url, api_key, model)):
        raise RuntimeError("请设置 RAG_EMBEDDING_BASE_URL、RAG_EMBEDDING_API_KEY 和 RAG_EMBEDDING_MODEL")
    return base_url, api_key, model


def embed(texts: list[str]):
    base_url, api_key, model = embedding_config()
    with httpx.Client(timeout=90, trust_env=False) as client:
        response = client.post(
            f"{base_url}/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "input": texts, "encoding_format": "float"},
        )
    response.raise_for_status()
    data = response.json().get("data", [])
    vectors = [item.get("embedding") for item in sorted(data, key=lambda item: item.get("index", 0))]
    if len(vectors) != len(texts) or any(not isinstance(vector, list) for vector in vectors):
        raise RuntimeError("Embedding API 返回的向量数量或格式不正确")
    return vectors


def build(args):
    rows = source_chunks(Path(args.db), args.work_title, args.chapters, args.chunk_size, args.overlap)
    OUTPUT.mkdir(exist_ok=True)
    meta = {
        "type": "meta",
        "workTitle": args.work_title,
        "chapterLimit": args.chapters,
        "chunkSize": args.chunk_size,
        "overlap": args.overlap,
    }
    with Path(args.index).open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for start in range(0, len(rows), args.batch_size):
            batch = rows[start : start + args.batch_size]
            for row, vector in zip(batch, embed([item["text"] for item in batch])):
                handle.write(json.dumps({**row, "embedding": vector}, ensure_ascii=False) + "\n")
            print(f"已建立 {min(start + len(batch), len(rows))}/{len(rows)} 个片段")
    print(f"完成：{args.index}")


def inspect(args):
    rows = source_chunks(Path(args.db), args.work_title, args.chapters, args.chunk_size, args.overlap)
    print(f"作品：《{args.work_title}》")
    print(f"资料范围：前 {args.chapters} 章")
    print(f"切片数量：{len(rows)}")
    print(f"待向量化字符数：{sum(len(row['text']) for row in rows)}")
    for row in rows[:3]:
        print(f"\n第{row['chapter']}章《{row['chapterTitle']}》· 片段{row['chunk']}\n{row['text'][:120]}…")


def cosine(left: list[float], right: list[float]):
    numerator = sum(a * b for a, b in zip(left, right))
    denominator = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return numerator / denominator if denominator else 0.0


def search(args):
    lines = [json.loads(line) for line in Path(args.index).read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [line for line in lines if line.get("type") != "meta"]
    if not rows:
        raise RuntimeError("索引为空，请先运行 build")
    query_vector = embed([args.query])[0]
    ranked = sorted(((cosine(query_vector, row["embedding"]), row) for row in rows), reverse=True, key=lambda item: item[0])[: args.top_k]
    for score, row in ranked:
        print(f"\n[{score:.4f}] 第{row['chapter']}章《{row['chapterTitle']}》· 片段{row['chunk']}")
        print(row["text"])


def parser():
    command = argparse.ArgumentParser(description="斗破苍穹前 50 章语义 RAG 实验（不接入业务代码）")
    command.add_argument("--db", default=str(DEFAULT_DB), help="桌面端 novel.db 路径")
    command.add_argument("--work-title", default="斗破苍穹")
    sub = command.add_subparsers(required=True)
    build_parser = sub.add_parser("build", help="读取来源资料并生成本地向量索引")
    build_parser.add_argument("--chapters", type=int, default=50)
    build_parser.add_argument("--chunk-size", type=int, default=500)
    build_parser.add_argument("--overlap", type=int, default=50)
    build_parser.add_argument("--batch-size", type=int, default=16)
    build_parser.add_argument("--index", default=str(DEFAULT_INDEX))
    build_parser.set_defaults(run=build)
    inspect_parser = sub.add_parser("inspect", help="检查资料范围与切片数量，不调用 Embedding API")
    inspect_parser.add_argument("--chapters", type=int, default=50)
    inspect_parser.add_argument("--chunk-size", type=int, default=500)
    inspect_parser.add_argument("--overlap", type=int, default=50)
    inspect_parser.set_defaults(run=inspect)
    search_parser = sub.add_parser("search", help="检索并打印最相关的原文片段")
    search_parser.add_argument("query")
    search_parser.add_argument("--top-k", type=int, default=5)
    search_parser.add_argument("--index", default=str(DEFAULT_INDEX))
    search_parser.set_defaults(run=search)
    return command


if __name__ == "__main__":
    args = parser().parse_args()
    args.run(args)
