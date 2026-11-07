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
        role_chat_memory=connection.exec_driver_sql("SELECT 1 FROM app_schema_migrations WHERE version = 3").first()
        if not role_chat_memory:
            columns={column["name"] for column in inspect(engine).get_columns("role_chat_sessions")}
            if "memory_summary" not in columns:
                connection.exec_driver_sql("ALTER TABLE role_chat_sessions ADD COLUMN memory_summary TEXT NOT NULL DEFAULT ''")
            if "summary_cursor" not in columns:
                connection.exec_driver_sql("ALTER TABLE role_chat_sessions ADD COLUMN summary_cursor INTEGER NOT NULL DEFAULT 0")
            connection.exec_driver_sql("INSERT INTO app_schema_migrations (version, applied_at) VALUES (3, CURRENT_TIMESTAMP)")
        role_card_emotions=connection.exec_driver_sql("SELECT 1 FROM app_schema_migrations WHERE version = 4").first()
        if not role_card_emotions:
            columns={column["name"] for column in inspect(engine).get_columns("experience_role_cards")}
            if "emotion_images" not in columns:
                connection.exec_driver_sql("ALTER TABLE experience_role_cards ADD COLUMN emotion_images JSON NOT NULL DEFAULT '{}'")
            if "special_emotion_label" not in columns:
                connection.exec_driver_sql("ALTER TABLE experience_role_cards ADD COLUMN special_emotion_label VARCHAR(40) NOT NULL DEFAULT '特殊状态'")
            connection.exec_driver_sql("INSERT INTO app_schema_migrations (version, applied_at) VALUES (4, CURRENT_TIMESTAMP)")
        custom_role_emotions=connection.exec_driver_sql("SELECT 1 FROM app_schema_migrations WHERE version = 5").first()
        if not custom_role_emotions:
            columns={column["name"] for column in inspect(engine).get_columns("experience_role_cards")}
            if "custom_emotions" not in columns:
                connection.exec_driver_sql("ALTER TABLE experience_role_cards ADD COLUMN custom_emotions JSON NOT NULL DEFAULT '[]'")
            rows=connection.exec_driver_sql("SELECT id, emotion_images, special_emotion_label, custom_emotions FROM experience_role_cards").mappings()
            for row in rows:
                images=json.loads(row["emotion_images"] or "{}") if isinstance(row["emotion_images"],str) else (row["emotion_images"] or {})
                custom=json.loads(row["custom_emotions"] or "[]") if isinstance(row["custom_emotions"],str) else (row["custom_emotions"] or [])
                legacy_path=images.pop("special","")
                if legacy_path and not custom:
                    custom.append({"id":"custom_legacy","name":row["special_emotion_label"] or "特殊状态","description":"","image_path":legacy_path})
                connection.exec_driver_sql("UPDATE experience_role_cards SET emotion_images = ?, custom_emotions = ? WHERE id = ?",(json.dumps(images,ensure_ascii=False),json.dumps(custom,ensure_ascii=False),row["id"]))
            connection.exec_driver_sql("INSERT INTO app_schema_migrations (version, applied_at) VALUES (5, CURRENT_TIMESTAMP)")
        role_dialogue_examples=connection.exec_driver_sql("SELECT 1 FROM app_schema_migrations WHERE version = 6").first()
        if not role_dialogue_examples:
            columns={column["name"] for column in inspect(engine).get_columns("experience_role_cards")}
            if "dialogue_examples" not in columns:
                connection.exec_driver_sql("ALTER TABLE experience_role_cards ADD COLUMN dialogue_examples JSON NOT NULL DEFAULT '[]'")
            connection.exec_driver_sql("INSERT INTO app_schema_migrations (version, applied_at) VALUES (6, CURRENT_TIMESTAMP)")
        embedding_config=connection.exec_driver_sql("SELECT 1 FROM app_schema_migrations WHERE version = 7").first()
        if not embedding_config:
            columns={column["name"] for column in inspect(engine).get_columns("llm_configs")}
            if "embedding_base_url" not in columns:
                connection.exec_driver_sql("ALTER TABLE llm_configs ADD COLUMN embedding_base_url VARCHAR(500) NOT NULL DEFAULT ''")
            if "embedding_api_key" not in columns:
                connection.exec_driver_sql("ALTER TABLE llm_configs ADD COLUMN embedding_api_key TEXT NOT NULL DEFAULT ''")
            if "embedding_model" not in columns:
                connection.exec_driver_sql("ALTER TABLE llm_configs ADD COLUMN embedding_model VARCHAR(160) NOT NULL DEFAULT ''")
            connection.exec_driver_sql("INSERT INTO app_schema_migrations (version, applied_at) VALUES (7, CURRENT_TIMESTAMP)")
        rag_index=connection.exec_driver_sql("SELECT 1 FROM app_schema_migrations WHERE version = 8").first()
        if not rag_index:
            columns={column["name"] for column in inspect(engine).get_columns("works")}
            for name,definition in {"rag_status":"VARCHAR(32) NOT NULL DEFAULT 'not_built'","rag_processed":"INTEGER NOT NULL DEFAULT 0","rag_total":"INTEGER NOT NULL DEFAULT 0","rag_error":"TEXT NOT NULL DEFAULT ''"}.items():
                if name not in columns:connection.exec_driver_sql(f"ALTER TABLE works ADD COLUMN {name} {definition}")
            connection.exec_driver_sql("INSERT INTO app_schema_migrations (version, applied_at) VALUES (8, CURRENT_TIMESTAMP)")
        emotion_descriptions=connection.exec_driver_sql("SELECT 1 FROM app_schema_migrations WHERE version = 9").first()
        if not emotion_descriptions:
            columns={column["name"] for column in inspect(engine).get_columns("experience_role_cards")}
            if "emotion_descriptions" not in columns:
                connection.exec_driver_sql("ALTER TABLE experience_role_cards ADD COLUMN emotion_descriptions JSON NOT NULL DEFAULT '{}'")
            connection.exec_driver_sql("INSERT INTO app_schema_migrations (version, applied_at) VALUES (9, CURRENT_TIMESTAMP)")
