"""Novel 的独立正史数据库。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_default_path = Path(__file__).resolve().parent / "novel.db"
DATABASE_URL = os.getenv("NOVEL_DATABASE_URL") or f"sqlite:///{_default_path}"


def _json_dumps(value: object) -> str:
    """保留中文 JSON 字符，方便直接在 SQLite 客户端查看。"""
    return json.dumps(value, ensure_ascii=False)


class Base(DeclarativeBase):
    pass


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=not DATABASE_URL.startswith("sqlite"),
    json_serializer=_json_dumps,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@event.listens_for(engine, "connect")
def _enable_foreign_keys(dbapi_conn, _record):
    if DATABASE_URL.startswith("sqlite"):
        dbapi_conn.execute("PRAGMA foreign_keys = ON")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_foreshadow_columns() -> None:
    """为已有 SQLite 数据库补齐伏笔排序列，避免发布时丢失旧数据。"""
    if not DATABASE_URL.startswith("sqlite") or "foreshadows" not in inspect(engine).get_table_names():
        return
    with engine.begin() as conn:
        columns = {column["name"] for column in inspect(conn).get_columns("foreshadows")}
        if "appearance_chapter" not in columns:
            conn.execute(text("ALTER TABLE foreshadows ADD COLUMN appearance_chapter INTEGER NOT NULL DEFAULT 0"))
        if "sort_order" not in columns:
            conn.execute(text("ALTER TABLE foreshadows ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"))
        rows = conn.execute(text("SELECT id, novel_id FROM foreshadows WHERE sort_order = 0 ORDER BY novel_id ASC, created_at ASC, id ASC")).mappings()
        rank_by_novel: dict[str, int] = {}
        for row in rows:
            novel_id = row["novel_id"]
            rank_by_novel[novel_id] = rank_by_novel.get(novel_id, 0) + 1
            conn.execute(text("UPDATE foreshadows SET sort_order = :sort_order WHERE id = :id"), {"sort_order": rank_by_novel[novel_id], "id": row["id"]})


def ensure_novel_columns() -> None:
    """轻量迁移：补齐书架分流字段，并识别既有剧本导入作品。"""
    if "novels" not in inspect(engine).get_table_names():
        return
    with engine.begin() as conn:
        columns = {column["name"] for column in inspect(conn).get_columns("novels")}
        if "genre_tag" not in columns:
            conn.execute(text("ALTER TABLE novels ADD COLUMN genre_tag VARCHAR(40) NOT NULL DEFAULT ''"))
        if "source_mode" not in columns:
            conn.execute(text("ALTER TABLE novels ADD COLUMN source_mode VARCHAR(16) NOT NULL DEFAULT 'writing'"))
        if "script_published" not in columns:
            conn.execute(text("ALTER TABLE novels ADD COLUMN script_published BOOLEAN NOT NULL DEFAULT FALSE"))
        if "full_outline" not in columns:
            conn.execute(text("ALTER TABLE novels ADD COLUMN full_outline JSON NOT NULL DEFAULT '{}'"))
        if "book_setup" not in columns:
            conn.execute(text("ALTER TABLE novels ADD COLUMN book_setup JSON NOT NULL DEFAULT '{}'"))
        if "import_runs" in inspect(conn).get_table_names():
            conn.execute(text("""
                UPDATE novels SET source_mode = 'script'
                WHERE id IN (
                    SELECT DISTINCT novel_id FROM import_runs
                    WHERE CAST(result AS TEXT) LIKE '%\"importMode\": \"script\"%'
                       OR CAST(result AS TEXT) LIKE '%\"importMode\":\"script\"%'
                )
            """))


def ensure_tracking_columns() -> None:
    """轻量 SQLite 迁移：在不引入外部迁移框架的前提下兼容已创建的伏笔表。"""
    if not DATABASE_URL.startswith("sqlite") or "foreshadows" not in inspect(engine).get_table_names():
        return
    definitions = {
        "planned_chapter": "INTEGER NOT NULL DEFAULT 0",
        "importance": "VARCHAR(16) NOT NULL DEFAULT 'medium'",
        "related_character_names": "JSON NOT NULL DEFAULT '[]'",
        "resolution_chapter": "INTEGER NOT NULL DEFAULT 0",
        "resolution_method": "VARCHAR(32) NOT NULL DEFAULT ''",
        "resolution_effect": "TEXT NOT NULL DEFAULT ''",
    }
    with engine.begin() as conn:
        columns = {column["name"] for column in inspect(conn).get_columns("foreshadows")}
        for name, definition in definitions.items():
            if name not in columns:
                conn.execute(text(f"ALTER TABLE foreshadows ADD COLUMN {name} {definition}"))


def ensure_task_run_columns() -> None:
    """为已有 SQLite 数据库补齐任务更新时间列，不影响正在执行或已完成的任务。"""
    if not DATABASE_URL.startswith("sqlite"):
        return
    with engine.begin() as conn:
        tables = set(inspect(conn).get_table_names())
        for table in ("generation_runs", "import_runs"):
            if table not in tables:
                continue
            columns = {column["name"] for column in inspect(conn).get_columns(table)}
            if "updated_at" not in columns:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN updated_at DATETIME"))
                conn.execute(text(f"UPDATE {table} SET updated_at = COALESCE(finished_at, created_at) WHERE updated_at IS NULL"))


def ensure_chapter_columns() -> None:
    """为已有章节补齐原文物理段索引。"""
    if "chapters" not in inspect(engine).get_table_names():
        return
    with engine.begin() as conn:
        columns = {column["name"] for column in inspect(conn).get_columns("chapters")}
        if "source_segment_order" not in columns:
            conn.execute(text("ALTER TABLE chapters ADD COLUMN source_segment_order INTEGER NOT NULL DEFAULT 0"))
        if "blueprint" not in columns:
            conn.execute(text("ALTER TABLE chapters ADD COLUMN blueprint JSON NOT NULL DEFAULT '{}'"))
        # 按每本书的实际章节落库顺序回填缺失值，避免依赖标题中的章节编号。
        novel_ids = [row[0] for row in conn.execute(text("SELECT DISTINCT novel_id FROM chapters"))]
        for novel_id in novel_ids:
            rows = list(conn.execute(text("SELECT id, source_segment_order FROM chapters WHERE novel_id = :novel_id ORDER BY sequence, created_at, id"), {"novel_id": novel_id}))
            next_order = max((int(row[1]) for row in rows if row[1] and int(row[1]) > 0), default=0) + 1
            for row in rows:
                if not row[1] or int(row[1]) <= 0:
                    conn.execute(text("UPDATE chapters SET source_segment_order = :order WHERE id = :id"), {"order": next_order, "id": row[0]})
                    next_order += 1

def ensure_memory_event_columns() -> None:
    if "character_memory_events" not in inspect(engine).get_table_names():
        return
    with engine.begin() as conn:
        columns = {column["name"] for column in inspect(conn).get_columns("character_memory_events")}
        for name, definition in {"knowledge_scope": "VARCHAR(32) NOT NULL DEFAULT 'objective_canon'", "evidence_level": "VARCHAR(32) NOT NULL DEFAULT 'inferred_text'", "source_chapter_id": "VARCHAR(32)", "related_character_id": "VARCHAR(32)", "memory_key": "VARCHAR(160) NOT NULL DEFAULT ''", "superseded_by": "VARCHAR(32)", "replaces_event_id": "VARCHAR(32)", "replacement_event_ids": "JSON NOT NULL DEFAULT '[]'"}.items():
            if name not in columns:
                conn.execute(text(f"ALTER TABLE character_memory_events ADD COLUMN {name} {definition}"))
        if "character_memory_packages" in inspect(conn).get_table_names():
            package_columns = {column["name"] for column in inspect(conn).get_columns("character_memory_packages")}
            if "memory_key" not in package_columns:
                conn.execute(text("ALTER TABLE character_memory_packages ADD COLUMN memory_key VARCHAR(160) NOT NULL DEFAULT ''"))
        if "character_relationships" in inspect(conn).get_table_names():
            relationship_columns = {column["name"] for column in inspect(conn).get_columns("character_relationships")}
            if "source_event_id" not in relationship_columns:
                conn.execute(text("ALTER TABLE character_relationships ADD COLUMN source_event_id VARCHAR(32)"))

def ensure_character_columns() -> None:
    if "characters" not in inspect(engine).get_table_names():
        return
    with engine.begin() as conn:
        columns = {column["name"] for column in inspect(conn).get_columns("characters")}
        if "aliases" not in columns:
            conn.execute(text("ALTER TABLE characters ADD COLUMN aliases JSON NOT NULL DEFAULT '[]'"))


def ensure_character_candidate_columns() -> None:
    """持久化候选人物清洗结果，兼容既有 SQLite/PostgreSQL 数据库。"""
    if "character_candidates" not in inspect(engine).get_table_names():
        return
    definitions = {
        "canonical_name": "VARCHAR(120) NOT NULL DEFAULT ''",
        "cleaning_action": "VARCHAR(32) NOT NULL DEFAULT 'unprocessed'",
        "cleaning_confidence": "FLOAT NOT NULL DEFAULT 0",
        "cleaning_reason": "TEXT NOT NULL DEFAULT ''",
        "mention_sources": "JSON NOT NULL DEFAULT '[]'",
        "evidence_snippets": "JSON NOT NULL DEFAULT '[]'",
        "proposed_memory_events": "JSON NOT NULL DEFAULT '[]'",
    }
    with engine.begin() as conn:
        columns = {column["name"] for column in inspect(conn).get_columns("character_candidates")}
        for name, definition in definitions.items():
            if name not in columns:
                conn.execute(text(f"ALTER TABLE character_candidates ADD COLUMN {name} {definition}"))


def ensure_experience_columns() -> None:
    """兼容已创建的副本表，并移除旧快照中重复保存的正史正文。"""
    if not DATABASE_URL.startswith("sqlite"):
        return
    with engine.begin() as conn:
        tables = set(inspect(conn).get_table_names())
        if "experience_sessions" in tables:
            columns = {column["name"] for column in inspect(conn).get_columns("experience_sessions")}
            for name, definition in {
                "selected_character_name": "VARCHAR(120) NOT NULL DEFAULT ''",
                "role_mode": "VARCHAR(24) NOT NULL DEFAULT 'original'",
            }.items():
                if name not in columns:
                    conn.execute(text(f"ALTER TABLE experience_sessions ADD COLUMN {name} {definition}"))
        if "experience_snapshots" not in tables:
            return
        rows = conn.execute(text("SELECT id, snapshot FROM experience_snapshots WHERE snapshot IS NOT NULL"))
        for row in rows:
            raw_snapshot = row[1]
            if not raw_snapshot:
                continue
            try:
                snapshot = json.loads(raw_snapshot) if isinstance(raw_snapshot, str) else raw_snapshot
            except (TypeError, ValueError):
                continue
            if not isinstance(snapshot, dict) or not isinstance(snapshot.get("chapters"), list):
                continue
            refs = snapshot.get("chapterRefs") if isinstance(snapshot.get("chapterRefs"), list) else []
            existing_ids = {str(item.get("id")) for item in refs if isinstance(item, dict) and item.get("id")}
            for chapter in snapshot.get("chapters") or []:
                if not isinstance(chapter, dict) or not chapter.get("id"):
                    continue
                chapter_id = str(chapter["id"])
                if chapter_id in existing_ids:
                    continue
                refs.append({
                    "id": chapter_id,
                    "sequence": chapter.get("sequence") or 0,
                    "sourceSegmentOrder": chapter.get("sourceSegmentOrder") or chapter.get("sequence") or 0,
                    "title": chapter.get("title") or "",
                })
                existing_ids.add(chapter_id)
            snapshot["chapterRefs"] = refs
            snapshot.pop("chapters", None)
            conn.execute(
                text("UPDATE experience_snapshots SET snapshot = :snapshot WHERE id = :id"),
                {"id": row[0], "snapshot": json.dumps(snapshot, ensure_ascii=False)},
            )
