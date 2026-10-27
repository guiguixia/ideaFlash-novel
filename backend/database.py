from __future__ import annotations
import json, os
from pathlib import Path
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker
DATABASE_URL=os.getenv("NOVEL_DATABASE_URL") or f"sqlite:///{Path(__file__).resolve().parent/'novel.db'}"
class Base(DeclarativeBase): pass
engine=create_engine(DATABASE_URL,connect_args={"check_same_thread":False} if DATABASE_URL.startswith("sqlite") else {},json_serializer=lambda v:json.dumps(v,ensure_ascii=False))
SessionLocal=sessionmaker(bind=engine,autoflush=False)
@event.listens_for(engine,"connect")
def foreign_keys(conn,_):
    if DATABASE_URL.startswith("sqlite"): conn.execute("PRAGMA foreign_keys=ON")
def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()
LEGACY={"novels","plot_units","chapters","generation_runs","chapter_revision_snapshots","import_runs","foreshadows","characters","character_relationships","character_memory_events","character_memory_event_versions","character_memory_packages","character_candidates","canon_change_proposals","experience_snapshots","experience_character_backfills","market_scan_runs","market_scan_items","market_insight_links","market_reference_works"}
def reset_legacy_schema():
    inspector=inspect(engine);tables=set(inspector.get_table_names())
    stale=tables & LEGACY
    # 旧小说工作台已使用 experience_sessions 表名；新会话表增加了 work_id，
    # 因此需要按列结构识别并重建，不能把同名表误认为新表。
    if "experience_sessions" in tables:
        columns={column["name"] for column in inspector.get_columns("experience_sessions")}
        if "work_id" not in columns:
            stale.add("experience_sessions")
    if not stale:return
    with engine.begin() as c:
        if DATABASE_URL.startswith("sqlite"):c.exec_driver_sql("PRAGMA foreign_keys=OFF")
        for table in stale:c.exec_driver_sql(f'DROP TABLE IF EXISTS "{table}"')
        if DATABASE_URL.startswith("sqlite"):c.exec_driver_sql("PRAGMA foreign_keys=ON")

def run_schema_migrations():
    """记录数据库基线；后续桌面版结构变更在此按版本追加迁移。"""
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE IF NOT EXISTS app_schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        exists=connection.exec_driver_sql("SELECT 1 FROM app_schema_migrations WHERE version = 1").first()
        if not exists:
            connection.exec_driver_sql("INSERT INTO app_schema_migrations (version, applied_at) VALUES (1, CURRENT_TIMESTAMP)")
        extraction_cache=connection.exec_driver_sql("SELECT 1 FROM app_schema_migrations WHERE version = 2").first()
        if not extraction_cache:
            columns={column["name"] for column in inspect(engine).get_columns("source_segments")}
            if "experience_extraction" not in columns:
                connection.exec_driver_sql("ALTER TABLE source_segments ADD COLUMN experience_extraction JSON")
            connection.exec_driver_sql("INSERT INTO app_schema_migrations (version, applied_at) VALUES (2, CURRENT_TIMESTAMP)")
