-- Novel backend schema 变更记录
-- 用途：手动备查、PostgreSQL 生产环境执行、新库初始化参考。
--
-- SQLite 开发环境无需手动执行本文件：
--   服务启动时 database.py 中的 ensure_*() 函数会自动完成所有 ALTER TABLE，
--   新表由 Base.metadata.create_all() 在首次启动时自动建立。
--
-- PostgreSQL 生产环境执行方式：
--   psql -d <your_db> -f Novel/backend/migrations.sql
--   所有语句均带 IF NOT EXISTS / 列存在检查，可重复执行。
--
-- 追加规范：每段以注释标注 [分支] 日期 说明，不删除历史段。

-- ============================================================
-- [main 基线] 初始建表 — 服务首次启动由 create_all() 自动完成
-- ============================================================

CREATE TABLE IF NOT EXISTS novels (
    id                 VARCHAR(32)  PRIMARY KEY,
    platform_user_id   VARCHAR(64)  NOT NULL,
    title              VARCHAR(160) NOT NULL,
    genre              VARCHAR(120) NOT NULL DEFAULT '',
    target_platform    VARCHAR(80)  NOT NULL DEFAULT '',
    target_words       INTEGER      NOT NULL DEFAULT 0,
    core_promise       TEXT         NOT NULL DEFAULT '',
    protagonist_agency TEXT         NOT NULL DEFAULT '',
    status             VARCHAR(32)  NOT NULL DEFAULT 'drafting',
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_novels_platform_user_id ON novels (platform_user_id);

CREATE TABLE IF NOT EXISTS plot_units (
    id               VARCHAR(32)  PRIMARY KEY,
    novel_id         VARCHAR(32)  NOT NULL REFERENCES novels(id),
    sequence         INTEGER      NOT NULL DEFAULT 1,
    title            VARCHAR(160) NOT NULL DEFAULT '第一阶段：开局与立足',
    promise          TEXT         NOT NULL DEFAULT '',
    protagonist_goal TEXT         NOT NULL DEFAULT '',
    obstacle         TEXT         NOT NULL DEFAULT '',
    payoff           TEXT         NOT NULL DEFAULT '',
    forbidden_reveals TEXT        NOT NULL DEFAULT '',
    status           VARCHAR(32)  NOT NULL DEFAULT 'planned'
);
CREATE INDEX IF NOT EXISTS ix_plot_units_novel_id ON plot_units (novel_id);

CREATE TABLE IF NOT EXISTS chapters (
    id            VARCHAR(32)  PRIMARY KEY,
    novel_id      VARCHAR(32)  NOT NULL REFERENCES novels(id),
    plot_unit_id  VARCHAR(32)  DEFAULT NULL REFERENCES plot_units(id),
    sequence      INTEGER      NOT NULL DEFAULT 1,
    title         VARCHAR(160) NOT NULL DEFAULT '',
    outline       TEXT         NOT NULL DEFAULT '',
    context_pack  JSON         NOT NULL DEFAULT '{}',
    body          TEXT         NOT NULL DEFAULT '',
    status        VARCHAR(32)  NOT NULL DEFAULT 'planned',
    canon_changes JSON         NOT NULL DEFAULT '[]',
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_chapters_novel_id ON chapters (novel_id);

CREATE TABLE IF NOT EXISTS generation_runs (
    id           VARCHAR(32)  PRIMARY KEY,
    novel_id     VARCHAR(32)  NOT NULL REFERENCES novels(id),
    chapter_id   VARCHAR(32)  NOT NULL REFERENCES chapters(id),
    trace_id     VARCHAR(64)  NOT NULL,
    kind         VARCHAR(40)  NOT NULL DEFAULT 'chapter_generation',
    status       VARCHAR(32)  NOT NULL DEFAULT 'queued',
    model        VARCHAR(160) NOT NULL DEFAULT '',
    prompt       TEXT         NOT NULL DEFAULT '',
    raw_response TEXT         NOT NULL DEFAULT '',
    error        TEXT         NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ,
    finished_at  TIMESTAMPTZ  DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS ix_generation_runs_novel_id   ON generation_runs (novel_id);
CREATE INDEX IF NOT EXISTS ix_generation_runs_chapter_id ON generation_runs (chapter_id);
CREATE INDEX IF NOT EXISTS ix_generation_runs_trace_id   ON generation_runs (trace_id);

CREATE TABLE IF NOT EXISTS chapter_revision_snapshots (
    id         VARCHAR(32)  PRIMARY KEY,
    novel_id   VARCHAR(32)  NOT NULL REFERENCES novels(id),
    chapter_id VARCHAR(32)  NOT NULL REFERENCES chapters(id),
    title      VARCHAR(160) NOT NULL DEFAULT '',
    body       TEXT         NOT NULL DEFAULT '',
    word_count INTEGER      NOT NULL DEFAULT 0,
    reason     VARCHAR(32)  NOT NULL DEFAULT 'revision',
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_chapter_revision_snapshots_novel_id   ON chapter_revision_snapshots (novel_id);
CREATE INDEX IF NOT EXISTS ix_chapter_revision_snapshots_chapter_id ON chapter_revision_snapshots (chapter_id);

CREATE TABLE IF NOT EXISTS import_runs (
    id                 VARCHAR(32)  PRIMARY KEY,
    novel_id           VARCHAR(32)  NOT NULL REFERENCES novels(id),
    trace_id           VARCHAR(64)  NOT NULL,
    status             VARCHAR(32)  NOT NULL DEFAULT 'queued',
    stage              VARCHAR(64)  NOT NULL DEFAULT 'queued',
    processed_chapters INTEGER      NOT NULL DEFAULT 0,
    total_chapters     INTEGER      NOT NULL DEFAULT 0,
    result             JSON         NOT NULL DEFAULT '{}',
    error              TEXT         NOT NULL DEFAULT '',
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ,
    finished_at        TIMESTAMPTZ  DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS ix_import_runs_novel_id  ON import_runs (novel_id);
CREATE INDEX IF NOT EXISTS ix_import_runs_trace_id  ON import_runs (trace_id);

CREATE TABLE IF NOT EXISTS foreshadows (
    id                     VARCHAR(32)  PRIMARY KEY,
    novel_id               VARCHAR(32)  NOT NULL REFERENCES novels(id),
    title                  VARCHAR(200) NOT NULL DEFAULT '未命名线索',
    content                TEXT         NOT NULL DEFAULT '',
    status                 VARCHAR(32)  NOT NULL DEFAULT 'active',
    source_run_id          VARCHAR(32)  DEFAULT NULL REFERENCES import_runs(id),
    appearance_chapter     INTEGER      NOT NULL DEFAULT 0,
    sort_order             INTEGER      NOT NULL DEFAULT 0,
    planned_chapter        INTEGER      NOT NULL DEFAULT 0,
    importance             VARCHAR(16)  NOT NULL DEFAULT 'medium',
    related_character_names JSON        NOT NULL DEFAULT '[]',
    resolution_chapter     INTEGER      NOT NULL DEFAULT 0,
    resolution_method      VARCHAR(32)  NOT NULL DEFAULT '',
    resolution_effect      TEXT         NOT NULL DEFAULT '',
    created_at             TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_foreshadows_novel_id   ON foreshadows (novel_id);
CREATE INDEX IF NOT EXISTS ix_foreshadows_status     ON foreshadows (status);
CREATE INDEX IF NOT EXISTS ix_foreshadows_sort_order ON foreshadows (sort_order);

CREATE TABLE IF NOT EXISTS characters (
    id                    VARCHAR(32)  PRIMARY KEY,
    novel_id              VARCHAR(32)  NOT NULL REFERENCES novels(id),
    name                  VARCHAR(120) NOT NULL,
    role                  VARCHAR(64)  NOT NULL DEFAULT 'supporting',
    status                VARCHAR(32)  NOT NULL DEFAULT 'active',
    identity              TEXT         NOT NULL DEFAULT '',
    traits                TEXT         NOT NULL DEFAULT '',
    motivation            TEXT         NOT NULL DEFAULT '',
    goal                  TEXT         NOT NULL DEFAULT '',
    voice                 TEXT         NOT NULL DEFAULT '',
    current_state         TEXT         NOT NULL DEFAULT '',
    public_image          TEXT         NOT NULL DEFAULT '',
    first_appearance_chapter INTEGER   NOT NULL DEFAULT 0,
    change_log            JSON         NOT NULL DEFAULT '[]',
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_characters_novel_id ON characters (novel_id);
CREATE INDEX IF NOT EXISTS ix_characters_name     ON characters (name);
CREATE INDEX IF NOT EXISTS ix_characters_status   ON characters (status);

CREATE TABLE IF NOT EXISTS character_relationships (
    id               VARCHAR(32)  PRIMARY KEY,
    novel_id         VARCHAR(32)  NOT NULL REFERENCES novels(id),
    from_character_id VARCHAR(32) NOT NULL REFERENCES characters(id),
    to_character_id  VARCHAR(32)  NOT NULL REFERENCES characters(id),
    relation_type    VARCHAR(64)  NOT NULL DEFAULT '',
    sentiment        VARCHAR(32)  NOT NULL DEFAULT 'neutral',
    current_state    TEXT         NOT NULL DEFAULT '',
    started_chapter  INTEGER      NOT NULL DEFAULT 0,
    changed_chapter  INTEGER      NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_character_relationships_novel_id          ON character_relationships (novel_id);
CREATE INDEX IF NOT EXISTS ix_character_relationships_from_character_id ON character_relationships (from_character_id);
CREATE INDEX IF NOT EXISTS ix_character_relationships_to_character_id   ON character_relationships (to_character_id);

CREATE TABLE IF NOT EXISTS canon_change_proposals (
    id         VARCHAR(32)  PRIMARY KEY,
    novel_id   VARCHAR(32)  NOT NULL REFERENCES novels(id),
    chapter_id VARCHAR(32)  NOT NULL REFERENCES chapters(id),
    kind       VARCHAR(32)  NOT NULL,
    payload    JSON         NOT NULL DEFAULT '{}',
    status     VARCHAR(32)  NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ  DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS ix_canon_change_proposals_novel_id   ON canon_change_proposals (novel_id);
CREATE INDEX IF NOT EXISTS ix_canon_change_proposals_chapter_id ON canon_change_proposals (chapter_id);
CREATE INDEX IF NOT EXISTS ix_canon_change_proposals_kind       ON canon_change_proposals (kind);
CREATE INDEX IF NOT EXISTS ix_canon_change_proposals_status     ON canon_change_proposals (status);


-- ============================================================
-- [novel_dev] 2026-09-07 剧本导入与人物记忆链路
-- SQLite 开发环境：database.py ensure_*() 启动时自动补齐，无需手动执行。
-- PostgreSQL 生产环境：手动执行以下语句。
-- ============================================================

-- novels：书架分流 + 剧本模式字段
ALTER TABLE novels ADD COLUMN IF NOT EXISTS genre_tag        VARCHAR(40)  NOT NULL DEFAULT '';
ALTER TABLE novels ADD COLUMN IF NOT EXISTS source_mode      VARCHAR(16)  NOT NULL DEFAULT 'writing';
ALTER TABLE novels ADD COLUMN IF NOT EXISTS script_published BOOLEAN      NOT NULL DEFAULT FALSE;
ALTER TABLE novels ADD COLUMN IF NOT EXISTS book_setup       JSON         NOT NULL DEFAULT '{}';
ALTER TABLE novels ADD COLUMN IF NOT EXISTS full_outline     JSON         NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS ix_novels_source_mode      ON novels (source_mode);
CREATE INDEX IF NOT EXISTS ix_novels_script_published ON novels (script_published);

-- chapters：原文物理段时间锚点 + 蓝图字段
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS source_segment_order INTEGER NOT NULL DEFAULT 0;
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS blueprint            JSON    NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS ix_chapters_source_segment_order ON chapters (source_segment_order);

-- characters：别名列表
ALTER TABLE characters ADD COLUMN IF NOT EXISTS aliases JSON NOT NULL DEFAULT '[]';

-- character_relationships：关联来源事件
ALTER TABLE character_relationships ADD COLUMN IF NOT EXISTS source_event_id VARCHAR(32) DEFAULT NULL;

CREATE INDEX IF NOT EXISTS ix_character_relationships_source_event_id ON character_relationships (source_event_id);

-- 新表：人物原子记忆事件（带原文证据）
CREATE TABLE IF NOT EXISTS character_memory_events (
    id                        VARCHAR(32)  PRIMARY KEY,
    novel_id                  VARCHAR(32)  NOT NULL REFERENCES novels(id),
    character_id              VARCHAR(32)  NOT NULL REFERENCES characters(id),
    source_chapter_id         VARCHAR(32)  DEFAULT NULL REFERENCES chapters(id),
    related_character_id      VARCHAR(32)  DEFAULT NULL REFERENCES characters(id),
    event_type                VARCHAR(32)  NOT NULL,
    memory_key                VARCHAR(160) NOT NULL DEFAULT '',
    value                     TEXT         NOT NULL DEFAULT '',
    valid_from_source_segment INTEGER      NOT NULL DEFAULT 0,
    valid_to_source_segment   INTEGER      DEFAULT NULL,
    quote                     TEXT         NOT NULL DEFAULT '',
    evidence_status           VARCHAR(32)  NOT NULL DEFAULT 'insufficient_evidence',
    knowledge_scope           VARCHAR(32)  NOT NULL DEFAULT 'objective_canon',
    evidence_level            VARCHAR(32)  NOT NULL DEFAULT 'inferred_text',
    source                    VARCHAR(32)  NOT NULL DEFAULT 'llm',
    review_status             VARCHAR(32)  NOT NULL DEFAULT 'pending',
    confidence                FLOAT        DEFAULT NULL,
    superseded_by             VARCHAR(32)  DEFAULT NULL,
    replaces_event_id         VARCHAR(32)  DEFAULT NULL,
    replacement_event_ids     JSON         NOT NULL DEFAULT '[]',
    created_at                TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_character_memory_events_novel_id             ON character_memory_events (novel_id);
CREATE INDEX IF NOT EXISTS ix_character_memory_events_character_id         ON character_memory_events (character_id);
CREATE INDEX IF NOT EXISTS ix_character_memory_events_source_chapter_id    ON character_memory_events (source_chapter_id);
CREATE INDEX IF NOT EXISTS ix_character_memory_events_related_character_id ON character_memory_events (related_character_id);
CREATE INDEX IF NOT EXISTS ix_character_memory_events_event_type           ON character_memory_events (event_type);
CREATE INDEX IF NOT EXISTS ix_character_memory_events_memory_key           ON character_memory_events (memory_key);
CREATE INDEX IF NOT EXISTS ix_character_memory_events_valid_from           ON character_memory_events (valid_from_source_segment);
CREATE INDEX IF NOT EXISTS ix_character_memory_events_evidence_status      ON character_memory_events (evidence_status);
CREATE INDEX IF NOT EXISTS ix_character_memory_events_review_status        ON character_memory_events (review_status);
CREATE INDEX IF NOT EXISTS ix_character_memory_events_replaces_event_id    ON character_memory_events (replaces_event_id);

-- 新表：人物记忆事件历史版本快照
CREATE TABLE IF NOT EXISTS character_memory_event_versions (
    id         VARCHAR(32)  PRIMARY KEY,
    event_id   VARCHAR(32)  NOT NULL,
    novel_id   VARCHAR(32)  NOT NULL REFERENCES novels(id),
    snapshot   JSON         NOT NULL DEFAULT '{}',
    action     VARCHAR(32)  NOT NULL DEFAULT 'edit',
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_character_memory_event_versions_event_id ON character_memory_event_versions (event_id);
CREATE INDEX IF NOT EXISTS ix_character_memory_event_versions_novel_id ON character_memory_event_versions (novel_id);

-- 新表：编译后的待确认记忆包（多条原始事件 -> 一条可决策的记忆）
CREATE TABLE IF NOT EXISTS character_memory_packages (
    id                        VARCHAR(32)  PRIMARY KEY,
    novel_id                  VARCHAR(32)  NOT NULL REFERENCES novels(id),
    character_id              VARCHAR(32)  NOT NULL REFERENCES characters(id),
    run_id                    VARCHAR(32)  DEFAULT NULL REFERENCES import_runs(id),
    accepted_event_id         VARCHAR(32)  DEFAULT NULL REFERENCES character_memory_events(id),
    canonical_type            VARCHAR(32)  NOT NULL,
    memory_key                VARCHAR(160) NOT NULL DEFAULT '',
    canonical_value           TEXT         NOT NULL DEFAULT '',
    disposition               VARCHAR(32)  NOT NULL DEFAULT 'core_memory',
    knowledge_scope           VARCHAR(32)  NOT NULL DEFAULT 'character_known',
    valid_from_source_segment INTEGER      NOT NULL DEFAULT 0,
    valid_to_source_segment   INTEGER      DEFAULT NULL,
    confidence                FLOAT        DEFAULT NULL,
    risk_level                VARCHAR(16)  NOT NULL DEFAULT 'normal',
    rationale                 TEXT         NOT NULL DEFAULT '',
    source_event_ids          JSON         NOT NULL DEFAULT '[]',
    evidence_summaries        JSON         NOT NULL DEFAULT '[]',
    conflicts                 JSON         NOT NULL DEFAULT '[]',
    status                    VARCHAR(32)  NOT NULL DEFAULT 'pending',
    created_at                TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ  NOT NULL DEFAULT now(),
    decided_at                TIMESTAMPTZ  DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS ix_character_memory_packages_novel_id              ON character_memory_packages (novel_id);
CREATE INDEX IF NOT EXISTS ix_character_memory_packages_character_id          ON character_memory_packages (character_id);
CREATE INDEX IF NOT EXISTS ix_character_memory_packages_run_id                ON character_memory_packages (run_id);
CREATE INDEX IF NOT EXISTS ix_character_memory_packages_canonical_type        ON character_memory_packages (canonical_type);
CREATE INDEX IF NOT EXISTS ix_character_memory_packages_memory_key            ON character_memory_packages (memory_key);
CREATE INDEX IF NOT EXISTS ix_character_memory_packages_valid_from            ON character_memory_packages (valid_from_source_segment);
CREATE INDEX IF NOT EXISTS ix_character_memory_packages_disposition           ON character_memory_packages (disposition);
CREATE INDEX IF NOT EXISTS ix_character_memory_packages_status                ON character_memory_packages (status);

-- 新表：人物候选（历史人物候选，清洗前暂存）
CREATE TABLE IF NOT EXISTS character_candidates (
    id                     VARCHAR(32)  PRIMARY KEY,
    novel_id               VARCHAR(32)  NOT NULL REFERENCES novels(id),
    name                   VARCHAR(120) NOT NULL,
    discovered_by          VARCHAR(32)  NOT NULL DEFAULT 'local_dialogue_scan',
    mention_segment_count  INTEGER      NOT NULL DEFAULT 0,
    status                 VARCHAR(32)  NOT NULL DEFAULT 'pending',
    character_id           VARCHAR(32)  DEFAULT NULL REFERENCES characters(id),
    canonical_name         VARCHAR(120) NOT NULL DEFAULT '',
    cleaning_action        VARCHAR(32)  NOT NULL DEFAULT 'unprocessed',
    cleaning_confidence    FLOAT        NOT NULL DEFAULT 0,
    cleaning_reason        TEXT         NOT NULL DEFAULT '',
    mention_sources        JSON         NOT NULL DEFAULT '[]',
    evidence_snippets      JSON         NOT NULL DEFAULT '[]',
    proposed_memory_events JSON         NOT NULL DEFAULT '[]',
    created_at             TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_character_candidates_novel_id        ON character_candidates (novel_id);
CREATE INDEX IF NOT EXISTS ix_character_candidates_name            ON character_candidates (name);
CREATE INDEX IF NOT EXISTS ix_character_candidates_status          ON character_candidates (status);
CREATE INDEX IF NOT EXISTS ix_character_candidates_cleaning_action ON character_candidates (cleaning_action);
