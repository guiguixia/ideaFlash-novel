"""Novel 正史与生产运行的最小模型。"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def new_id() -> str:
    return uuid.uuid4().hex


class Novel(Base):
    __tablename__ = "novels"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    platform_user_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(160))
    genre: Mapped[str] = mapped_column(String(120), default="")
    target_platform: Mapped[str] = mapped_column(String(80), default="")
    genre_tag: Mapped[str] = mapped_column(String(40), default="")
    target_words: Mapped[int] = mapped_column(Integer, default=0)
    source_mode: Mapped[str] = mapped_column(String(16), default="writing", index=True)
    script_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    core_promise: Mapped[str] = mapped_column(Text, default="")
    protagonist_agency: Mapped[str] = mapped_column(Text, default="")
    book_setup: Mapped[dict] = mapped_column(JSON, default=dict)
    full_outline: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="drafting")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    plot_units: Mapped[list["PlotUnit"]] = relationship(back_populates="novel", cascade="all, delete-orphan")
    chapters: Mapped[list["Chapter"]] = relationship(back_populates="novel", cascade="all, delete-orphan")
    runs: Mapped[list["GenerationRun"]] = relationship(back_populates="novel", cascade="all, delete-orphan")


class PlotUnit(Base):
    __tablename__ = "plot_units"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(160), default="第一阶段：开局与立足")
    promise: Mapped[str] = mapped_column(Text, default="")
    protagonist_goal: Mapped[str] = mapped_column(Text, default="")
    obstacle: Mapped[str] = mapped_column(Text, default="")
    payoff: Mapped[str] = mapped_column(Text, default="")
    forbidden_reveals: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="planned")

    novel: Mapped[Novel] = relationship(back_populates="plot_units")


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id"), index=True)
    plot_unit_id: Mapped[str | None] = mapped_column(ForeignKey("plot_units.id"), nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    source_segment_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    title: Mapped[str] = mapped_column(String(160), default="")
    outline: Mapped[str] = mapped_column(Text, default="")
    blueprint: Mapped[dict] = mapped_column(JSON, default=dict)
    context_pack: Mapped[dict] = mapped_column(JSON, default=dict)
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="planned")
    canon_changes: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    novel: Mapped[Novel] = relationship(back_populates="chapters")


class ExperienceSnapshot(Base):
    """用户选择的连续章节体验副本；首期以 JSON 保存结构化快照，便于回退。"""
    __tablename__ = "experience_snapshots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    start_source_segment: Mapped[int] = mapped_column(Integer, default=1, index=True)
    end_source_segment: Mapped[int] = mapped_column(Integer, default=1, index=True)
    status: Mapped[str] = mapped_column(String(32), default="ready", index=True)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    token_usage: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ExperienceSession(Base):
    """副本中的临时角色体验会话，不写入小说正史。"""
    __tablename__ = "experience_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id"), index=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("experience_snapshots.id"), index=True)
    character_id: Mapped[str | None] = mapped_column(ForeignKey("characters.id"), nullable=True, index=True)
    selected_character_name: Mapped[str] = mapped_column(String(120), default="")
    role_mode: Mapped[str] = mapped_column(String(24), default="original")
    perspective: Mapped[str] = mapped_column(String(16), default="third")
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    turn: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    history: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ExperienceCharacterBackfill(Base):
    """副本人物历史回溯状态与结果，避免重复调用模型。"""
    __tablename__ = "experience_character_backfills"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id"), index=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("experience_snapshots.id"), index=True)
    character_name: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    trace_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class GenerationRun(Base):
    __tablename__ = "generation_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id"), index=True)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id"), index=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(40), default="chapter_generation")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    model: Mapped[str] = mapped_column(String(160), default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    raw_response: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    novel: Mapped[Novel] = relationship(back_populates="runs")


class ChapterRevisionSnapshot(Base):
    """Immutable canon snapshot created before a chapter is replaced or restored."""
    __tablename__ = "chapter_revision_snapshots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id"), index=True)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id"), index=True)
    title: Mapped[str] = mapped_column(String(160), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(String(32), default="revision")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportRun(Base):
    __tablename__ = "import_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id"), index=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    stage: Mapped[str] = mapped_column(String(64), default="queued")
    processed_chapters: Mapped[int] = mapped_column(Integer, default=0)
    total_chapters: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Foreshadow(Base):
    __tablename__ = "foreshadows"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="未命名线索")
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    source_run_id: Mapped[str | None] = mapped_column(ForeignKey("import_runs.id"), nullable=True)
    # 首次出现章节用于默认阅读顺序；sort_order 仅在用户手动调整时覆盖该顺序。
    appearance_chapter: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    planned_chapter: Mapped[int] = mapped_column(Integer, default=0)
    importance: Mapped[str] = mapped_column(String(16), default="medium")
    related_character_names: Mapped[list] = mapped_column(JSON, default=list)
    resolution_chapter: Mapped[int] = mapped_column(Integer, default=0)
    resolution_method: Mapped[str] = mapped_column(String(32), default="")
    resolution_effect: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    role: Mapped[str] = mapped_column(String(64), default="supporting")
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    identity: Mapped[str] = mapped_column(Text, default="")
    traits: Mapped[str] = mapped_column(Text, default="")
    motivation: Mapped[str] = mapped_column(Text, default="")
    goal: Mapped[str] = mapped_column(Text, default="")
    voice: Mapped[str] = mapped_column(Text, default="")
    current_state: Mapped[str] = mapped_column(Text, default="")
    public_image: Mapped[str] = mapped_column(Text, default="")
    first_appearance_chapter: Mapped[int] = mapped_column(Integer, default=0)
    change_log: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CharacterRelationship(Base):
    __tablename__ = "character_relationships"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id"), index=True)
    from_character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), index=True)
    to_character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(64), default="")
    sentiment: Mapped[str] = mapped_column(String(32), default="neutral")
    current_state: Mapped[str] = mapped_column(Text, default="")
    source_event_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    started_chapter: Mapped[int] = mapped_column(Integer, default=0)
    changed_chapter: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CharacterMemoryEvent(Base):
    """带原文证据的人物原子状态事件。"""
    __tablename__ = "character_memory_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id"), index=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), index=True)
    source_chapter_id: Mapped[str | None] = mapped_column(ForeignKey("chapters.id"), nullable=True, index=True)
    related_character_id: Mapped[str | None] = mapped_column(ForeignKey("characters.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    memory_key: Mapped[str] = mapped_column(String(160), default="", index=True)
    value: Mapped[str] = mapped_column(Text, default="")
    valid_from_source_segment: Mapped[int] = mapped_column(Integer, default=0, index=True)
    valid_to_source_segment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote: Mapped[str] = mapped_column(Text, default="")
    evidence_status: Mapped[str] = mapped_column(String(32), default="insufficient_evidence", index=True)
    knowledge_scope: Mapped[str] = mapped_column(String(32), default="objective_canon")
    evidence_level: Mapped[str] = mapped_column(String(32), default="inferred_text")
    source: Mapped[str] = mapped_column(String(32), default="llm")
    review_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    confidence: Mapped[float | None] = mapped_column()
    superseded_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    replaces_event_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    replacement_event_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CharacterMemoryEventVersion(Base):
    __tablename__ = "character_memory_event_versions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(String(32), index=True)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id"), index=True)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    action: Mapped[str] = mapped_column(String(32), default="edit")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CharacterMemoryPackage(Base):
    """将多条原始人物事件编译成一条可确认的原子记忆，源事件始终保留。"""
    __tablename__ = "character_memory_packages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id"), index=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("import_runs.id"), nullable=True, index=True)
    accepted_event_id: Mapped[str | None] = mapped_column(ForeignKey("character_memory_events.id"), nullable=True)
    canonical_type: Mapped[str] = mapped_column(String(32), index=True)
    memory_key: Mapped[str] = mapped_column(String(160), default="", index=True)
    canonical_value: Mapped[str] = mapped_column(Text, default="")
    disposition: Mapped[str] = mapped_column(String(32), default="core_memory", index=True)
    knowledge_scope: Mapped[str] = mapped_column(String(32), default="character_known")
    valid_from_source_segment: Mapped[int] = mapped_column(Integer, default=0, index=True)
    valid_to_source_segment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(16), default="normal")
    rationale: Mapped[str] = mapped_column(Text, default="")
    source_event_ids: Mapped[list] = mapped_column(JSON, default=list)
    evidence_summaries: Mapped[list] = mapped_column(JSON, default=list)
    conflicts: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CharacterCandidate(Base):
    __tablename__ = "character_candidates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    discovered_by: Mapped[str] = mapped_column(String(32), default="local_dialogue_scan")
    mention_segment_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    character_id: Mapped[str | None] = mapped_column(ForeignKey("characters.id"), nullable=True)
    canonical_name: Mapped[str] = mapped_column(String(120), default="")
    cleaning_action: Mapped[str] = mapped_column(String(32), default="unprocessed", index=True)
    cleaning_confidence: Mapped[float] = mapped_column(Float, default=0)
    cleaning_reason: Mapped[str] = mapped_column(Text, default="")
    mention_sources: Mapped[list] = mapped_column(JSON, default=list)
    evidence_snippets: Mapped[list] = mapped_column(JSON, default=list)
    proposed_memory_events: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CanonChangeProposal(Base):
    __tablename__ = "canon_change_proposals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id"), index=True)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
