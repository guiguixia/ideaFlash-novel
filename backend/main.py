"""Novel MVP API：新建一本书并生成第一章。"""
from __future__ import annotations

import os
import re
import json
import asyncio
import shutil
from threading import Lock
from datetime import datetime, timezone
from fastapi import BackgroundTasks, Body, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import models
from auth import (
    CurrentUser,
    authenticate_admin,
    get_current_user,
)
from database import Base, SessionLocal, engine, ensure_chapter_columns, ensure_character_candidate_columns, ensure_character_columns, ensure_experience_columns, ensure_foreshadow_columns, ensure_memory_event_columns, ensure_novel_columns, ensure_task_run_columns, ensure_tracking_columns, get_db
from dto import ApiListResponseDTO, ApiResponseDTO
from schemas import AssistantPlanRequest, BookSetupUpdateRequest, ChapterAiRevisionRequest, ChapterBlueprintRequest, ChapterGenerateRequest, ChapterRevisionRequest, CharacterMemoryEventCreateRequest, CharacterMergeRequest, CharacterUpdateRequest, DeslopRequest, ExperienceCreateRequest, ExperienceSessionCreateRequest, ExperienceTurnRequest, ForeshadowMoveRequest, ForeshadowUpdateRequest, FullOutlineUpdateRequest, LoginRequest, NovelCreateRequest, PlanningSuggestionRequest, PlotUnitUpdateRequest, ProposalDecisionRequest, RelationshipUpdateRequest, ReviewRequest, ScriptDialogueRequest, ScriptPublicationRequest
from services import CURRENT_MEMORY_TYPES, analyze_character_memory_index, analyze_import_run, build_experience_snapshot, clean_character_candidate_run, close_previous_memory_states, debug_skip_character_modeling_execution, demote_unconfirmed_llm_characters, foreshadow_appearance_chapter, foreshadow_fields, generate_chapter, materialize_canon_change_proposal, materialize_confirmed_candidate_events, materialize_unbound_relationship_events, normalize_import_title, normalize_memory_event_type, prepare_import_run, propose_canon_changes, reindex_chapter_memory, refresh_character_candidates, retrieve_character_dialogue_sources, run_character_modeling_pipeline, run_chapter_revision, run_deslop, run_experience_scene, run_review, run_script_dialogue, split_import_archive, suggest_chapter_blueprints, suggest_novel_setup, suggest_plot_unit, sync_relationship_projection, _build_deslop_prompt, _deslop_level
from trace import TraceMiddleware, logger, trace_id, trace_id_var
from workspace import novel_workspace, write_artifact, write_blob

Base.metadata.create_all(bind=engine)
ensure_foreshadow_columns()
ensure_novel_columns()
ensure_tracking_columns()
ensure_task_run_columns()
ensure_chapter_columns()
ensure_memory_event_columns()
ensure_character_columns()
ensure_character_candidate_columns()
ensure_experience_columns()
URL_PATH = (os.getenv("NOVEL_URL_PATH") or "").rstrip("/")
app = FastAPI(title="Novel API", version="0.1.0", root_path=URL_PATH)
app.add_middleware(TraceMiddleware)
_persistent_tasks: set[asyncio.Task] = set()


def schedule_persistent(coro) -> None:
    task = asyncio.create_task(coro)
    _persistent_tasks.add(task)
    def completed(done: asyncio.Task) -> None:
        _persistent_tasks.discard(done)
        error = None if done.cancelled() else done.exception()
        if error:
            logger.error("persistent task dispatcher failed", exc_info=(type(error), error, error.__traceback__))
    task.add_done_callback(completed)


async def dispatch_import_run(run_id: str) -> None:
    db = SessionLocal()
    try:
        run = db.get(models.ImportRun, run_id)
        if not run or run.status in {"succeeded", "failed", "cancelled"}: return
        if run.status == "cancel_requested":
            run.status, run.stage = "cancelled", "cancelled"; db.commit(); return
        meta = dict(run.result or {})
        run.status = "queued"; db.commit()
        if meta.get("experienceSnapshotId"):
            target = run_experience_snapshot(run.id, str(meta["experienceSnapshotId"]))
        elif meta.get("characterModeling") and not meta.get("memoryIndexCompleted"):
            if debug_skip_character_modeling_execution():
                logger.info(
                    "dispatch skipped character modeling execution for debug run=%s character=%s",
                    run.id,
                    str(meta.get("characterId") or ""),
                )
                return
            target = run_character_modeling_pipeline(run.id, str(meta.get("characterId")))
        elif meta.get("characterId"):
            target = analyze_character_memory_index(run.id, str(meta["characterId"]))
        elif meta.get("chapterId") or run.stage == "chapter_memory_reindex":
            target = reindex_chapter_memory(run.id, str(meta.get("chapterId")))
        elif meta.get("candidateCleaningOnly"):
            target = clean_character_candidate_run(run.id)
        elif meta.get("sourcePath") and run.stage in {"upload_received", "parsing_source", "persisting_chapters", "candidate_indexing", "candidate_cleaning", "character_selection"}:
            target = prepare_import_run(run.id)
        else:
            target = analyze_import_run(run.id)
    finally:
        db.close()
    await target


async def dispatch_generation_run(run_id: str) -> None:
    db = SessionLocal()
    try:
        run = db.get(models.GenerationRun, run_id)
        if not run or run.status in {"succeeded", "failed", "cancelled"}: return
        if run.status == "cancel_requested": run.status = "cancelled"; db.commit(); return
        run.status = "queued"; db.commit()
        chapter = db.get(models.Chapter, run.chapter_id)
        platform = str(((chapter.context_pack or {}).get("reviewTask") or {}).get("platform") or "") if chapter else ""
        kind = run.kind
    finally:
        db.close()
    if kind == "chapter_revision": await run_chapter_revision(run_id)
    elif kind == "deslop": await run_deslop(run_id)
    elif kind == "chapter_review": await run_review(run_id, platform)


async def run_experience_snapshot(run_id: str, snapshot_id: str) -> None:
    db = SessionLocal()
    try:
        run = db.get(models.ImportRun, run_id)
        item = db.get(models.ExperienceSnapshot, snapshot_id) if run else None
        novel = db.get(models.Novel, run.novel_id) if run else None
        if not run or not item or not novel:
            return
        run.status, run.stage, run.error = "running", "experience_snapshot", ""
        item.status, item.error = "running", ""
        db.commit()
        token = trace_id_var.set(run.trace_id)
        try:
            snapshot = await build_experience_snapshot(db, novel, item.start_source_segment, item.end_source_segment, item.title)
            item.snapshot = snapshot
            item.token_usage = snapshot.get("tokenUsage") or {}
            item.status = "ready"
            run.result = {**(run.result or {}), "snapshotStatus": "ready", "tokenUsage": item.token_usage}
            run.processed_chapters = run.total_chapters
            run.status, run.stage, run.finished_at = "succeeded", "completed", datetime.now(timezone.utc)
            db.commit()
        except Exception as exc:
            item.status, item.error = "failed", str(exc)
            run.status, run.stage, run.error, run.finished_at = "failed", "failed", str(exc), datetime.now(timezone.utc)
            db.commit()
        finally:
            trace_id_var.reset(token)
    finally:
        db.close()


def backfill_completed_task_progress(db: Session) -> int:
    """修复旧候选清洗任务已完成但进度仍为 0 的展示数据。"""
    rows = db.query(models.ImportRun).filter(
        models.ImportRun.status == "succeeded",
        models.ImportRun.processed_chapters < models.ImportRun.total_chapters,
    ).all()
    changed = 0
    for run in rows:
        if (run.result or {}).get("candidateCleaningOnly"):
            run.processed_chapters = run.total_chapters
            changed += 1
    if changed:
        db.commit()
    return changed


def enqueue_automatic_candidate_cleaning(db: Session) -> int:
    """每次启动自动补齐尚未清洗的候选，不把清洗动作暴露给用户。"""
    novel_ids = {
        row[0]
        for row in db.query(models.CharacterCandidate.novel_id).filter(
            models.CharacterCandidate.status == "pending",
            models.CharacterCandidate.cleaning_action.in_(("unprocessed", "rule_keep")),
        ).distinct().all()
    }
    created = 0
    for novel_id in novel_ids:
        source_runs = db.query(models.ImportRun).filter_by(novel_id=novel_id).order_by(
            models.ImportRun.created_at.desc(),
            models.ImportRun.id.desc(),
        ).all()
        latest_source_run = next(
            (run for run in source_runs if (run.result or {}).get("sourcePath")),
            None,
        )
        if latest_source_run:
            if latest_source_run.status in {"cancel_requested", "cancelled", "failed"}:
                continue
        active = db.query(models.ImportRun).filter(
            models.ImportRun.novel_id == novel_id,
            models.ImportRun.status.in_(("queued", "running", "cancel_requested")),
        ).first()
        if active:
            continue
        count = db.query(models.CharacterCandidate).filter(
            models.CharacterCandidate.novel_id == novel_id,
            models.CharacterCandidate.status == "pending",
            models.CharacterCandidate.cleaning_action.in_(("unprocessed", "rule_keep")),
        ).count()
        if not count:
            continue
        db.add(models.ImportRun(
            novel_id=novel_id,
            trace_id=trace_id(),
            status="queued",
            stage="candidate_cleaning",
            total_chapters=count,
            result={"candidateCleaningOnly": True, "automatic": True},
        ))
        created += 1
    if created:
        db.commit()
    return created


@app.on_event("startup")
async def recover_persistent_runs() -> None:
    db = SessionLocal()
    try:
        for item in db.query(models.ImportRun).filter(models.ImportRun.status.in_(("queued", "running", "cancel_requested"))).all():
            item.status = "cancelled"
            item.stage = "cancelled"
            item.error = item.error or "服务启动后未自动恢复旧任务，请手动重试"
            snapshot_id = (item.result or {}).get("experienceSnapshotId")
            if snapshot_id:
                snapshot = db.get(models.ExperienceSnapshot, str(snapshot_id))
                if snapshot and snapshot.status in {"queued", "running"}:
                    snapshot.status = "cancelled"
                    snapshot.error = item.error
        for item in db.query(models.GenerationRun).filter(models.GenerationRun.status.in_(("queued", "running", "cancel_requested"))).all():
            item.status = "cancelled"
            item.error = item.error or "服务启动后未自动恢复旧任务，请手动重试"
        db.commit()
        backfill_completed_task_progress(db)
        demote_unconfirmed_llm_characters(db)
        unbound_relationships = materialize_unbound_relationship_events(db)
        if unbound_relationships:
            logger.info("unbound relationship migration completed created=%s", unbound_relationships)
        enqueue_automatic_candidate_cleaning(db)
    finally:
        db.close()
raw_cors = os.getenv(
    "CORS_ORIGINS",
    "http://127.0.0.1:5179,http://localhost:5179",
)
allow_origins = [o.strip() for o in raw_cors.split(",") if o.strip()]
_tracking_migration_lock = Lock()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def response(data=None, msg: str = "ok", code: int = 0):
    return ApiResponseDTO(code=code, data=data, msg=msg, traceId=trace_id()).model_dump()


def list_response(items, msg: str = "ok", code: int = 0, pagination: dict | None = None):
    return ApiListResponseDTO(code=code, list=items, msg=msg, traceId=trace_id(), pagination=pagination).model_dump(exclude_none=True)


class NovelDomainError(HTTPException):
    def __init__(self, code: int, msg: str, status_code: int = 409, data=None):
        super().__init__(status_code=status_code, detail={"code": code, "msg": msg, "data": data})


def novel_data(novel: models.Novel, db: Session | None = None) -> dict:
    written_words = 0
    chapter_count = 0
    if db is not None:
        chapter_bodies = db.query(models.Chapter.body).filter_by(novel_id=novel.id).all()
        written_words = sum(text_word_count(body) for body, in chapter_bodies)
        chapter_count = len(chapter_bodies)
    return {
        "id": novel.id,
        "title": novel.title,
        "genre": novel.genre,
        "genreTag": novel.genre_tag,
        "targetPlatform": novel.target_platform,
        "targetWords": novel.target_words,
        "writtenWords": written_words,
        "sourceMode": novel.source_mode,
        "scriptPublished": bool(novel.script_published),
        "corePromise": novel.core_promise,
        "protagonistAgency": novel.protagonist_agency,
        "bookSetup": novel.book_setup or {},
        "fullOutline": novel.full_outline or {},
        "status": novel.status,
        "importedChapterCount": chapter_count,
        "createdAt": novel.created_at.isoformat() if novel.created_at else None,
    }


def chapter_data(chapter: models.Chapter) -> dict:
    return {
        "id": chapter.id,
        "plotUnitId": chapter.plot_unit_id,
        "sequence": chapter.sequence,
        "sourceSegmentOrder": chapter.source_segment_order or chapter.sequence,
        "title": chapter.title,
        "outline": chapter.outline,
        "blueprint": chapter.blueprint or {},
        "body": chapter.body,
        "wordCount": text_word_count(chapter.body),
        "status": chapter.status,
        "contextPack": chapter.context_pack or {},
        "canonChanges": chapter.canon_changes or [],
    }


def plot_unit_data(unit: models.PlotUnit) -> dict:
    return {
        "id": unit.id,
        "sequence": unit.sequence,
        "title": unit.title,
        "promise": unit.promise,
        "protagonistGoal": unit.protagonist_goal,
        "obstacle": unit.obstacle,
        "payoff": unit.payoff,
        "forbiddenReveals": unit.forbidden_reveals,
        "status": "active" if unit.status == "in_progress" else unit.status,
    }


def current_plot_unit(db: Session, novel_id: str) -> models.PlotUnit | None:
    units = db.query(models.PlotUnit).filter_by(novel_id=novel_id).order_by(models.PlotUnit.sequence).all()
    return next((unit for unit in units if unit.status in {"active", "in_progress"}), next((unit for unit in units if unit.status != "archived"), None))


def text_word_count(text: str) -> int:
    """Novel's word count is visible Chinese/non-whitespace characters, not token count."""
    return len(re.sub(r"\s+", "", text or ""))


def snapshot_data(snapshot: models.ChapterRevisionSnapshot) -> dict:
    return {
        "id": snapshot.id, "title": snapshot.title, "body": snapshot.body,
        "wordCount": snapshot.word_count, "reason": snapshot.reason,
        "createdAt": snapshot.created_at.isoformat() if snapshot.created_at else None,
    }


def draft_history_title() -> str:
    return datetime.now().astimezone().strftime("草稿编辑 · %Y-%m-%d %H:%M:%S")


def revision_quality_report(before: str, after: str) -> dict:
    before_count, after_count = text_word_count(before), text_word_count(after)
    delta = after_count - before_count
    findings = []
    if not after.strip():
        findings.append({"level": "blocking", "label": "正文为空，不能采纳为正史"})
    artifact = re.search(r"(?:作为AI|我无法(?:续写|改写)|本章|下一章|细纲|伏笔)", after or "")
    if artifact:
        findings.append({"level": "warning", "label": f"疑似写作工程词泄漏，请人工复核：{artifact.group(0)}"})
    if before_count and abs(delta) > max(800, round(before_count * 0.3)):
        findings.append({"level": "warning", "label": f"字数变化 {delta:+d} 字，超过原稿 30% 或 800 字阈值"})
    if not findings:
        findings.append({"level": "pass", "label": "基础长度与工程词检查通过；人物、伏笔和后续承接仍需结合影响报告确认。"})
    return {"beforeWords": before_count, "afterWords": after_count, "deltaWords": delta, "findings": findings, "blocking": any(item["level"] == "blocking" for item in findings)}


def revision_impact_report(db: Session, novel_id: str, chapter: models.Chapter, before: str, after: str) -> dict:
    following = db.query(models.Chapter).filter(models.Chapter.novel_id == novel_id, models.Chapter.sequence > chapter.sequence, models.Chapter.status == "accepted").order_by(models.Chapter.sequence).all()
    characters = db.query(models.Character).filter_by(novel_id=novel_id).all()
    foreshadows = db.query(models.Foreshadow).filter_by(novel_id=novel_id).all()
    removed_names = [item.name for item in characters if item.name and item.name in before and item.name not in after]
    removed_clues = [item.title for item in foreshadows if item.title and item.title in before and item.title not in after]
    affected = []
    for item in following:
        reasons = ["需核对与修订章节的事件先后及开篇承接"]
        names_used = [name for name in removed_names if name in item.body]
        clues_used = [title for title in removed_clues if title in item.body]
        if names_used:
            reasons.append(f"后章仍出现已从本章移除的人物：{'、'.join(names_used[:3])}")
        if clues_used:
            reasons.append(f"后章仍引用可能已移除的线索：{'、'.join(clues_used[:3])}")
        affected.append({"chapterId": item.id, "sequence": item.sequence, "title": item.title, "reasons": reasons})
    tracking = []
    if removed_names:
        tracking.append({"type": "人物状态", "message": f"请确认人物档案是否仍应保留：{'、'.join(removed_names[:5])}"})
    if removed_clues:
        tracking.append({"type": "伏笔", "message": f"请确认线索是否仍有效：{'、'.join(removed_clues[:5])}"})
    tracking.append({"type": "时间线", "message": "请核对本章事件的发生顺序、持续时间与后续章节的时间衔接。"})
    return {"affectedChapters": affected, "trackingChecks": tracking}


def import_run_data(run: models.ImportRun) -> dict:
    return {"id": run.id, "status": run.status, "stage": run.stage, "processedChapters": run.processed_chapters, "totalChapters": run.total_chapters, "result": run.result or {}, "error": run.error or "", "traceId": run.trace_id}


def active_import_task_data(run: models.ImportRun) -> dict:
    meta = run.result or {}
    task_type = "character_modeling" if meta.get("characterModeling") else "character_index" if meta.get("characterId") else "import_analysis"
    return {"runId": run.id, "traceId": run.trace_id, "status": run.status, "stage": run.stage, "type": task_type}


def import_task_stage_progress(run: models.ImportRun) -> tuple[int, int]:
    meta = run.result or {}
    if meta.get("experienceSnapshotId"):
        return (1 if run.status == "succeeded" else 0), 1
    if meta.get("characterModeling"):
        positions = {"character_modeling": 1, "character_indexing": 1, "completed": 2}
        return positions.get(run.stage, 0), 2
    if meta.get("candidateCleaningOnly"):
        return (1 if run.stage in {"candidate_cleaning", "candidate_names_ready", "index_ready", "completed"} else 0), 1
    if meta.get("importMode") == "script":
        stages = ("parsing_source", "persisting_chapters", "candidate_indexing", "character_selection", "index_ready")
        positions = {stage: index + 1 for index, stage in enumerate(stages)}
        positions["candidate_names_ready"] = len(stages)
        return (len(stages) if run.status == "succeeded" else positions.get(run.stage, 0)), len(stages)
    positions = {
        "parsing_source": 1,
        "persisting_chapters": 2,
        "candidate_indexing": 3,
        "candidate_cleaning": 4,
        "chapter_analysis": 5,
        "sample_indexing": 5,
        "post_analysis_candidate_cleaning": 6,
        "canon_aggregation": 7,
        "completed": 8,
    }
    return (8 if run.status == "succeeded" else positions.get(run.stage, 0)), 8


def task_data(run, novel: models.Novel, task_type: str) -> dict:
    if task_type == "import":
        if (run.result or {}).get("experienceSnapshotId"):
            stage_processed, stage_total = import_task_stage_progress(run)
            return {"id": run.id, "type": "experience_snapshot", "label": "创建体验副本", "novelId": novel.id, "novelTitle": novel.title, "status": run.status, "stage": run.stage, "progressMode": "stage", "processed": stage_processed, "total": stage_total, "tokenUsage": (run.result or {}).get("tokenUsage") or {}, "traceId": run.trace_id, "error": run.error or "", "createdAt": run.created_at.isoformat() if run.created_at else None, "finishedAt": run.finished_at.isoformat() if run.finished_at else None, "updatedAt": run.updated_at.isoformat() if run.updated_at else None}
        character_modeling = bool((run.result or {}).get("characterModeling"))
        incremental = bool((run.result or {}).get("incremental"))
        script_index = (run.result or {}).get("importMode") == "script"
        stage_processed, stage_total = import_task_stage_progress(run)
        return {
            "id": run.id, "type": "character_modeling" if character_modeling else "import_analysis", "label": f"人物建模 · {(run.result or {}).get('characterName') or '未命名人物'}" if character_modeling else (("增量剧本索引" if incremental else "剧本索引") if script_index else ("增量导入分析" if incremental else "导入分析")), "novelId": novel.id, "novelTitle": novel.title,
            "status": run.status, "stage": run.stage, "progressMode": "stage", "processed": stage_processed, "total": stage_total,
            "tokenUsage": (run.result or {}).get("tokenUsage") or {},
            "traceId": run.trace_id, "error": run.error or "", "createdAt": run.created_at.isoformat() if run.created_at else None,
            "finishedAt": run.finished_at.isoformat() if run.finished_at else None,
            "updatedAt": run.updated_at.isoformat() if run.updated_at else None,
        }
    return {
        "id": run.id, "type": run.kind,
        "label": {"chapter_revision": "AI 章节修订", "deslop": "去AI味", "chapter_review": "多视角审稿"}.get(run.kind, "章节生成"),
        "novelId": novel.id, "novelTitle": novel.title,
        "status": run.status, "stage": run.kind, "processed": 1 if run.status == "succeeded" else 0, "total": 1,
        "traceId": run.trace_id, "error": run.error or "", "createdAt": run.created_at.isoformat() if run.created_at else None,
        "finishedAt": run.finished_at.isoformat() if run.finished_at else None,
        "updatedAt": run.updated_at.isoformat() if run.updated_at else None,
    }


def foreshadow_data(item: models.Foreshadow) -> dict:
    return {"id": item.id, "title": item.title, "content": item.content, "status": item.status, "sourceRunId": item.source_run_id, "appearanceChapter": item.appearance_chapter, "plannedChapter": item.planned_chapter, "importance": item.importance, "relatedCharacterNames": item.related_character_names or [], "resolutionChapter": item.resolution_chapter, "resolutionMethod": item.resolution_method, "resolutionEffect": item.resolution_effect, "sortOrder": item.sort_order, "createdAt": item.created_at.isoformat() if item.created_at else None}


def character_data(item: models.Character) -> dict:
    return {"id": item.id, "name": item.name, "aliases": item.aliases or [], "role": item.role, "status": item.status, "identity": item.identity, "traits": item.traits, "motivation": item.motivation, "goal": item.goal, "voice": item.voice, "currentState": item.current_state, "publicImage": item.public_image, "firstAppearanceChapter": item.first_appearance_chapter, "changeLog": item.change_log or []}


def memory_event_data(item: models.CharacterMemoryEvent) -> dict:
    reason = memory_event_review_reason(item.value, item.quote, item.evidence_status)
    actions = (["split", "edit", "accept_as_is", "reject"] if reason == "composite_event" else ["edit", "accept_as_is", "reject"]) if item.review_status == "pending" else []
    high_risk = item.event_type in {"identity", "relationship", "status", "faction", "death", "marriage"}
    suggestion = "needs_confirmation" if high_risk or reason else "suggest_accept"
    return {"id": item.id, "characterId": item.character_id, "relatedCharacterId": item.related_character_id, "sourceChapterId": item.source_chapter_id, "eventType": item.event_type, "memoryKey": item.memory_key, "value": item.value, "validFromSourceSegment": item.valid_from_source_segment, "validToSourceSegment": item.valid_to_source_segment, "quote": item.quote, "evidenceStatus": item.evidence_status, "knowledgeScope": item.knowledge_scope, "evidenceLevel": item.evidence_level, "source": item.source, "reviewStatus": item.review_status, "confidence": item.confidence, "supersededBy": item.superseded_by, "replacesEventId": item.replaces_event_id, "replacementEventIds": item.replacement_event_ids or [], "reviewReason": reason, "reviewSuggestion": suggestion, "riskLevel": "high" if high_risk else "normal", "actions": actions}


def record_memory_event_version(db: Session, item: models.CharacterMemoryEvent, action: str) -> None:
    db.add(models.CharacterMemoryEventVersion(event_id=item.id, novel_id=item.novel_id, action=action, snapshot=memory_event_data(item)))


_CURRENT_MEMORY_TYPES = CURRENT_MEMORY_TYPES


def memory_event_review_reason(value: str, quote: str, evidence_status: str) -> str:
    if evidence_status == "rejected":
        return "rejected"
    if not quote and evidence_status != "manually_confirmed":
        return "quote_not_found"
    atomic_markers = ("并且", "同时", "以及", "随后", "并获得", "并成为", "且被")
    if any(marker in value for marker in atomic_markers):
        return "composite_event"
    if evidence_status == "insufficient_evidence":
        return "quote_does_not_cover_core_claim"
    return ""


def invalidate_chapter_memory_events(db: Session, chapter: models.Chapter) -> list[str]:
    invalidated = []
    rows = db.query(models.CharacterMemoryEvent).filter_by(novel_id=chapter.novel_id, source_chapter_id=chapter.id).all()
    for event in rows:
        record_memory_event_version(db, event, "chapter_revision_invalidate")
        event.review_status = "pending"
        if not event.quote or event.quote not in chapter.body:
            event.evidence_status = "insufficient_evidence"
            event.evidence_level = "inferred_text"
        invalidated.append(event.id)
    return invalidated


def relationship_data(item: models.CharacterRelationship, names: dict[str, str]) -> dict:
    return {"id": item.id, "fromCharacterId": item.from_character_id, "fromCharacterName": names.get(item.from_character_id, "未知人物"), "toCharacterId": item.to_character_id, "toCharacterName": names.get(item.to_character_id, "未知人物"), "relationType": item.relation_type, "sentiment": item.sentiment, "currentState": item.current_state, "sourceEventId": item.source_event_id, "startedChapter": item.started_chapter, "changedChapter": item.changed_chapter}


def tracking_context(db: Session, novel_id: str, next_sequence: int) -> dict:
    ensure_import_characters(db, novel_id)
    ensure_import_foreshadows(db, novel_id)
    characters = db.query(models.Character).filter_by(novel_id=novel_id, status="active").order_by(models.Character.first_appearance_chapter.asc()).all()
    foreshadows = db.query(models.Foreshadow).filter(models.Foreshadow.novel_id == novel_id, models.Foreshadow.status.in_(("active", "progressing"))).order_by(models.Foreshadow.sort_order.asc()).all()
    relationships = db.query(models.CharacterRelationship).filter_by(novel_id=novel_id).all()
    names = {item.id: item.name for item in characters}
    return {"forChapter": next_sequence, "characters": [{"name": item.name, "currentState": item.current_state, "goal": item.goal, "voice": item.voice} for item in characters], "relationships": [relationship_data(item, names) for item in relationships if item.from_character_id in names and item.to_character_id in names], "foreshadows": [{"title": item.title, "content": item.content, "appearanceChapter": item.appearance_chapter, "plannedChapter": item.planned_chapter, "importance": item.importance} for item in foreshadows]}


def memory_focus_context(db: Session, novel_id: str, names: list[str], resource_focus=None) -> dict:
    """把作者勾选的故事资源收敛为可直接进入章节提示词的上下文。"""
    resource_focus = resource_focus or {}
    selected = {name.strip() for name in [*names, *(getattr(resource_focus, "character_names", []) or [])] if name.strip()}
    relationship_ids = {item.strip() for item in (getattr(resource_focus, "relationship_ids", []) or []) if item.strip()}
    foreshadow_ids = {item.strip() for item in (getattr(resource_focus, "foreshadow_ids", []) or []) if item.strip()}
    if not selected and not relationship_ids and not foreshadow_ids:
        return {}
    characters = db.query(models.Character).filter(models.Character.novel_id == novel_id, models.Character.name.in_(selected)).all() if selected else []
    ids = {item.id for item in characters}
    character_names = {item.id: item.name for item in db.query(models.Character).filter_by(novel_id=novel_id).all()}
    relationships = db.query(models.CharacterRelationship).filter_by(novel_id=novel_id).all()
    foreshadows = db.query(models.Foreshadow).filter(models.Foreshadow.novel_id == novel_id, models.Foreshadow.status.in_(("active", "progressing"))).all()
    selected_relationships = [item for item in relationships if item.id in relationship_ids or item.from_character_id in ids or item.to_character_id in ids]
    selected_foreshadows = [item for item in foreshadows if item.id in foreshadow_ids or selected.intersection(set(item.related_character_names or []))]
    return {
        "selectedCharacters": [{"name": item.name, "identity": item.identity, "goal": item.goal, "motivation": item.motivation, "currentState": item.current_state, "voice": item.voice} for item in characters],
        "relationships": [relationship_data(item, character_names) for item in selected_relationships],
        "relatedForeshadows": [{"title": item.title, "content": item.content, "appearanceChapter": item.appearance_chapter} for item in selected_foreshadows],
    }


def latest_import_analysis(db: Session, novel_id: str):
    """ImportRun 也承载人物索引任务；这里只返回包含完整导入圣经的运行。"""
    rows = db.query(models.ImportRun).filter_by(novel_id=novel_id, status="succeeded").order_by(models.ImportRun.finished_at.desc(), models.ImportRun.id.desc()).all()
    bible_keys = {"current_situation", "character_states", "timeline", "style_guide"}
    return next((item for item in rows if bible_keys.intersection((item.result or {}).keys())), None)


def ensure_import_foreshadows(db: Session, novel_id: str) -> None:
    """兼容已有导入：首次访问时将旧 ImportRun 的候选线索迁移为可管理资产。"""
    if db.query(models.Foreshadow).filter_by(novel_id=novel_id).first():
        return
    run = latest_import_analysis(db, novel_id)
    if not run:
        return
    for index, source in enumerate((run.result or {}).get("active_foreshadows") or []):
        title, content = foreshadow_fields(source, index)
        appearance_chapter = foreshadow_appearance_chapter(source)
        db.add(models.Foreshadow(novel_id=novel_id, title=title, content=content, status="active", source_run_id=run.id, appearance_chapter=appearance_chapter, sort_order=(appearance_chapter or 999999) * 10000 + index + 1))
    db.commit()


def ensure_import_characters(db: Session, novel_id: str) -> None:
    """将导入分析中的角色状态候选转换为作者可编辑的正史档案。"""
    # 人物与关系接口会并发调用本迁移；互斥后再查询，避免同一导入结果被重复写入。
    with _tracking_migration_lock:
        rows = db.query(models.Character).filter_by(novel_id=novel_id).order_by(models.Character.created_at.asc(), models.Character.id.asc()).all()
        kept_by_name: dict[str, models.Character] = {}
        for item in rows:
            key = item.name.strip()
            canonical = kept_by_name.get(key)
            if not canonical:
                kept_by_name[key] = item
                continue
            db.query(models.CharacterRelationship).filter_by(novel_id=novel_id, from_character_id=item.id).update({"from_character_id": canonical.id}, synchronize_session=False)
            db.query(models.CharacterRelationship).filter_by(novel_id=novel_id, to_character_id=item.id).update({"to_character_id": canonical.id}, synchronize_session=False)
            db.delete(item)
        if rows:
            db.commit()
        if kept_by_name:
            return
        run = latest_import_analysis(db, novel_id)
        if not run:
            return
        seen_names: set[str] = set()
        for index, source in enumerate((run.result or {}).get("character_states") or []):
            if isinstance(source, str):
                name, current_state = f"人物 {index + 1}", source
                source = {}
            else:
                source = source or {}
                name = str(source.get("name") or source.get("character") or f"人物 {index + 1}")
                current_state = str(source.get("current_state") or source.get("state") or source.get("status") or source.get("summary") or "")
            name = name.strip()[:120]
            if name in seen_names:
                continue
            seen_names.add(name)
            try:
                first_appearance_chapter = max(0, int(source.get("first_appearance_chapter") or 0))
            except (TypeError, ValueError):
                first_appearance_chapter = 0
            db.add(models.Character(novel_id=novel_id, name=name, role=str(source.get("role") or "supporting")[:64], identity=str(source.get("identity") or "")[:2000], traits=str(source.get("traits") or "")[:2000], motivation=str(source.get("motivation") or "")[:2000], goal=str(source.get("goal") or "")[:2000], voice=str(source.get("voice") or "")[:2000], current_state=current_state[:4000], public_image=str(source.get("public_image") or "")[:2000], first_appearance_chapter=first_appearance_chapter))
        db.commit()


def invalidate_drafts(db: Session, novel_id: str, reason: str) -> int:
    drafts = db.query(models.Chapter).filter(models.Chapter.novel_id == novel_id, models.Chapter.status != "accepted").all()
    for draft in drafts:
        pack = dict(draft.context_pack or {})
        pack["stale"] = True
        pack["staleReason"] = reason
        draft.context_pack = pack
    return len(drafts)


@app.exception_handler(HTTPException)
async def handled_error(_request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=response(exc.detail.get("data"), exc.detail["msg"], exc.detail["code"]))
    return JSONResponse(status_code=exc.status_code, content=response(None, str(exc.detail), 400000 + exc.status_code))


@app.exception_handler(Exception)
async def unhandled_error(_request: Request, exc: Exception):
    logger.exception("unhandled API error")
    # 把可诊断的业务/上游错误透给前端，避免一律「服务暂时不可用」难排查
    detail = str(exc).strip()
    if isinstance(exc, (RuntimeError, ValueError)) and detail and len(detail) <= 240:
        msg = detail
    else:
        msg = "服务暂时不可用，请重试"
    return JSONResponse(status_code=500, content=response(None, msg, 500000))


@app.get("/health")
def health():
    return response({"service": "novel", "status": "ok"})


@app.post("/api/auth/login")
async def login(body: LoginRequest):
    return response(authenticate_admin(body.username, body.password))


@app.get("/api/auth/me")
async def me(request: Request, current_user: CurrentUser = Depends(get_current_user)):
    return response({
        "id": current_user.platform_user_id,
        "email": current_user.email,
        "username": current_user.username,
        "phone": None,
        "phone_verified": False,
    })


@app.get("/api/novels")
def list_novels(
    mode: str = Query("writing", pattern="^(writing|script)$"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.Novel).filter_by(platform_user_id=current_user.platform_user_id)
    if mode == "script":
        query = query.filter(or_(models.Novel.source_mode == "script", models.Novel.script_published.is_(True)))
    else:
        query = query.filter(models.Novel.source_mode == "writing")
    novels = query.order_by(models.Novel.updated_at.desc()).all()
    return list_response([novel_data(item, db) for item in novels])


@app.delete("/api/novels/{novel_id}")
def delete_novel(
    novel_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    novel = db.query(models.Novel).filter_by(
        id=novel_id,
        platform_user_id=current_user.platform_user_id,
    ).first()
    if not novel:
        raise HTTPException(404, "小说不存在")

    active_statuses = ("queued", "running", "cancel_requested")
    active_imports = db.query(models.ImportRun).filter(
        models.ImportRun.novel_id == novel.id,
        models.ImportRun.status.in_(active_statuses),
    ).count()
    active_generations = db.query(models.GenerationRun).filter(
        models.GenerationRun.novel_id == novel.id,
        models.GenerationRun.status.in_(active_statuses),
    ).count()
    if active_imports or active_generations:
        raise NovelDomainError(
            420009,
            "作品仍有进行中的任务，请先在任务中心停止后再删除",
            409,
            {"activeTaskCount": active_imports + active_generations},
        )

    title = novel.title
    source_mode = novel.source_mode
    workspace_path = novel_workspace(current_user.platform_user_id, novel.id)
    try:
        # Delete leaf rows first because existing production databases predate
        # ORM cascades for most of these tables and enforce foreign keys.
        for model in (
            models.CharacterMemoryEventVersion,
            models.CharacterMemoryPackage,
            models.CharacterMemoryEvent,
            models.CharacterCandidate,
            models.CharacterRelationship,
            models.CanonChangeProposal,
            models.GenerationRun,
            models.ChapterRevisionSnapshot,
            models.Foreshadow,
            models.ImportRun,
            models.Chapter,
            models.Character,
            models.PlotUnit,
        ):
            db.query(model).filter(model.novel_id == novel.id).delete(synchronize_session=False)
        db.delete(novel)
        db.flush()
        if workspace_path.exists():
            shutil.rmtree(workspace_path)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return response(
        {"id": novel_id, "title": title, "sourceMode": source_mode},
        "作品已删除",
    )


@app.post("/api/novels/{novel_id}/script-publication")
def set_script_publication(novel_id: str, body: ScriptPublicationRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    if novel.source_mode != "writing":
        raise NovelDomainError(420008, "剧本导入作品已固定展示在剧本书架，无需重复发布", 409)
    novel.script_published = body.published
    db.commit(); db.refresh(novel)
    return response(novel_data(novel, db), "已发布到剧本书架" if body.published else "已从剧本书架撤回")


@app.get("/api/tasks")
def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(8, ge=1, le=50),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import_rows = (
        db.query(models.ImportRun, models.Novel)
        .join(models.Novel, models.ImportRun.novel_id == models.Novel.id)
        .filter(models.Novel.platform_user_id == current_user.platform_user_id)
        .all()
    )
    generation_rows = (
        db.query(models.GenerationRun, models.Novel)
        .join(models.Novel, models.GenerationRun.novel_id == models.Novel.id)
        .filter(models.Novel.platform_user_id == current_user.platform_user_id)
        .all()
    )
    tasks = [task_data(run, novel, "import") for run, novel in import_rows]
    tasks.extend(task_data(run, novel, "generation") for run, novel in generation_rows)
    tasks.sort(key=lambda item: item["updatedAt"] or "", reverse=True)
    total = len(tasks)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)
    start = (page - 1) * page_size
    return list_response(
        tasks[start:start + page_size],
        pagination={"page": page, "pageSize": page_size, "total": total, "totalPages": total_pages},
    )


@app.post("/api/tasks/{run_id}/retry")
async def retry_failed_revision_task(run_id: str, background_tasks: BackgroundTasks, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    source = (
        db.query(models.GenerationRun)
        .join(models.Novel, models.GenerationRun.novel_id == models.Novel.id)
        .filter(models.GenerationRun.id == run_id, models.Novel.platform_user_id == current_user.platform_user_id)
        .first()
    )
    if not source:
        raise HTTPException(404, "任务不存在")
    if source.kind != "chapter_revision" or source.status != "failed":
        raise NovelDomainError(410011, "仅支持重试失败的 AI 章节修订任务", 409)
    chapter = db.query(models.Chapter).filter_by(id=source.chapter_id, novel_id=source.novel_id, status="accepted").first()
    if not chapter:
        raise NovelDomainError(410012, "原章节已不存在或不是正史，无法重试", 409)
    retry = models.GenerationRun(novel_id=source.novel_id, chapter_id=source.chapter_id, trace_id=trace_id(), kind="chapter_revision", status="queued", prompt=source.prompt)
    db.add(retry); db.flush()
    pack = dict(chapter.context_pack or {})
    pack["revisionTask"] = {"runId": retry.id, "status": "queued", "retryOf": source.id}
    chapter.context_pack = pack
    db.commit()
    schedule_persistent(dispatch_generation_run(retry.id))
    return response({"runId": retry.id, "retryOf": source.id}, "已按原修订请求重新进入任务中心")


@app.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    generation = db.query(models.GenerationRun).join(models.Novel, models.GenerationRun.novel_id == models.Novel.id).filter(models.GenerationRun.id == task_id, models.Novel.platform_user_id == current_user.platform_user_id).first()
    import_run = None if generation else db.query(models.ImportRun).join(models.Novel, models.ImportRun.novel_id == models.Novel.id).filter(models.ImportRun.id == task_id, models.Novel.platform_user_id == current_user.platform_user_id).first()
    run = generation or import_run
    if not run:
        raise HTTPException(404, "任务不存在")
    if generation and generation.kind != "chapter_revision":
        raise NovelDomainError(410014, "仅导入分析和 AI 修订草稿支持停止", 409)
    if run.status not in {"queued", "running", "cancel_requested"}:
        raise NovelDomainError(410013, "仅可停止排队中或运行中的任务", 409)
    run.status = "cancel_requested" if run.status == "running" else "cancelled"
    if import_run:
        run.stage = "cancel_requested" if run.status == "cancel_requested" else "cancelled"
    if generation and generation.kind == "chapter_revision":
        chapter = db.get(models.Chapter, generation.chapter_id)
        if chapter:
            pack = dict(chapter.context_pack or {})
            if (pack.get("revisionTask") or {}).get("runId") == generation.id:
                pack["revisionTask"] = {"runId": generation.id, "status": run.status}
                chapter.context_pack = pack
    db.commit()
    return response({"id": task_id, "status": run.status}, "任务正在停止；已返回的结果不会写入正文")


@app.get("/api/novels/{novel_id}/characters")
def list_characters(novel_id: str, keyword: str = "", status: str = "", current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    ensure_import_characters(db, novel.id)
    query = db.query(models.Character).filter_by(novel_id=novel.id)
    if keyword.strip():
        query = query.filter(models.Character.name.ilike(f"%{keyword.strip()}%"))
    if status:
        if status not in {"active", "away", "exited"}:
            raise NovelDomainError(410006, "人物状态仅支持 active、away 或 exited", 422)
        query = query.filter_by(status=status)
    return list_response([character_data(item) for item in query.order_by(models.Character.first_appearance_chapter.asc(), models.Character.created_at.asc(), models.Character.id.asc()).all()])


@app.get("/api/novels/{novel_id}/characters/{character_id}/memory-events")
def list_memory_events(novel_id: str, character_id: str, review_status: str = "", current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(status_code=404, detail={"code": 404404, "msg": "小说不存在"})
    character = db.query(models.Character).filter_by(id=character_id, novel_id=novel.id).first()
    if not character:
        raise HTTPException(status_code=404, detail={"code": 404404, "msg": "人物不存在"})
    query = db.query(models.CharacterMemoryEvent).filter_by(novel_id=novel.id, character_id=character.id)
    if review_status in {"pending", "accepted", "ignored"}:
        query = query.filter_by(review_status=review_status)
    rows = query.order_by(models.CharacterMemoryEvent.valid_from_source_segment.asc(), models.CharacterMemoryEvent.created_at.asc(), models.CharacterMemoryEvent.id.asc()).all()
    result = []
    for row in rows:
        end = row.valid_to_source_segment if row.valid_to_source_segment is not None else 2147483647
        conflicts = db.query(models.CharacterMemoryEvent).filter(models.CharacterMemoryEvent.novel_id == novel.id, models.CharacterMemoryEvent.character_id == character.id, models.CharacterMemoryEvent.id != row.id, models.CharacterMemoryEvent.event_type == row.event_type, models.CharacterMemoryEvent.value != row.value, models.CharacterMemoryEvent.valid_from_source_segment <= end, ((models.CharacterMemoryEvent.valid_to_source_segment.is_(None)) | (models.CharacterMemoryEvent.valid_to_source_segment >= row.valid_from_source_segment)), models.CharacterMemoryEvent.review_status != "ignored").limit(5).all()
        result.append({**memory_event_data(row), "conflicts": [memory_event_data(item) for item in conflicts]})
    return list_response(result)


@app.get("/api/novels/{novel_id}/memory-index-candidates")
def memory_index_candidates(novel_id: str, keyword: str = "", page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(status_code=404, detail={"code": 404404, "msg": "小说不存在"})
    characters = db.query(models.Character).filter_by(novel_id=novel.id).all()
    result = []
    for character in characters:
        names = [character.name, *(character.aliases or [])]
        mention_count = db.query(models.Chapter).filter(models.Chapter.novel_id == novel.id, or_(*(models.Chapter.body.contains(name) for name in names if name))).count()
        event_count = db.query(models.CharacterMemoryEvent).filter_by(novel_id=novel.id, character_id=character.id).count()
        pending_count = db.query(models.CharacterMemoryEvent).filter_by(novel_id=novel.id, character_id=character.id, review_status="pending").count()
        result.append({**character_data(character), "mentionSegmentCount": mention_count, "memoryEventCount": event_count, "pendingReviewCount": pending_count, "indexRecommended": mention_count > 0 and event_count == 0})
    candidate_query = db.query(models.CharacterCandidate).filter(
        models.CharacterCandidate.novel_id == novel.id,
        models.CharacterCandidate.status == "pending",
        models.CharacterCandidate.cleaning_action != "unprocessed",
    )
    if keyword.strip(): candidate_query = candidate_query.filter(models.CharacterCandidate.name.contains(keyword.strip()))
    candidate_total = candidate_query.count()
    candidate_rows = candidate_query.order_by(models.CharacterCandidate.mention_segment_count.desc(), models.CharacterCandidate.name).offset((page - 1) * page_size).limit(page_size).all()
    local_candidates = [{"id": item.id, "name": item.name, "discoveredBy": item.discovered_by, "mentionSegmentCount": item.mention_segment_count, "status": item.status, "canonicalName": item.canonical_name, "cleaningAction": item.cleaning_action, "cleaningConfidence": item.cleaning_confidence, "cleaningReason": item.cleaning_reason, "evidenceSnippets": item.evidence_snippets or []} for item in candidate_rows]
    latest_import = db.query(models.ImportRun).filter_by(novel_id=novel.id, status="succeeded").order_by(models.ImportRun.finished_at.desc(), models.ImportRun.id.desc()).first()
    cleaning_summary = ((latest_import.result or {}).get("candidateCleaning") or {}) if latest_import else {}
    result.sort(key=lambda item: (-item["mentionSegmentCount"], item["firstAppearanceChapter"], item["name"]))
    return response({"characters": result, "localCandidates": local_candidates, "cleaningSummary": cleaning_summary, "candidatePagination": {"page": page, "pageSize": page_size, "total": candidate_total, "totalPages": max(1, (candidate_total + page_size - 1) // page_size)}}, "人物索引候选已完成清洗")


@app.post("/api/novels/{novel_id}/memory-index-candidates/accept")
def accept_memory_index_candidate(novel_id: str, name: str = Query(..., min_length=2, max_length=120), candidate_id: str = Query(""), current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    candidate = db.query(models.CharacterCandidate).filter_by(novel_id=novel.id, id=candidate_id).first() if candidate_id else db.query(models.CharacterCandidate).filter_by(novel_id=novel.id, name=name).first()
    normalized_name = name.replace("熏", "薰")
    siblings = [
        item for item in db.query(models.CharacterCandidate).filter(
            models.CharacterCandidate.novel_id == novel.id,
            models.CharacterCandidate.status.in_(("pending", "merged")),
        ).all()
        if (item.canonical_name or item.name).replace("熏", "薰") == normalized_name
        or item.name.replace("熏", "薰") == normalized_name
    ]
    if candidate and candidate not in siblings:
        siblings.append(candidate)
    item = next((row for row in db.query(models.Character).filter_by(novel_id=novel.id).all() if row.name.replace("熏", "薰") == normalized_name), None)
    created = item is None
    if created:
        item = models.Character(novel_id=novel.id, name=name, role="supporting", status="active", aliases=[])
        db.add(item); db.flush()
    aliases = list(item.aliases or [])
    for sibling in siblings:
        sibling.status, sibling.character_id = "accepted", item.id
        clean_aliases = (sibling.name, sibling.canonical_name) if sibling.name.replace("熏", "薰") == normalized_name else (sibling.canonical_name,)
        for alias in clean_aliases:
            if alias and alias != item.name and alias not in aliases:
                aliases.append(alias)
    item.aliases = aliases
    db.commit(); db.refresh(item)
    materialize_confirmed_candidate_events(db, novel.id)
    return response(character_data(item), "候选人物已建立，可补充人物记忆索引" if created else "人物已存在")


@app.post("/api/novels/{novel_id}/memory-index-candidates/ignore")
def ignore_memory_index_candidate(novel_id: str, candidate_id: str = Query(...), current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    item = db.query(models.CharacterCandidate).filter_by(id=candidate_id, novel_id=novel.id if novel else "").first() if novel else None
    if not item: raise HTTPException(404, "候选人物不存在")
    item.status = "ignored"; db.commit()
    return response(None, "候选人物已忽略")


@app.post("/api/novels/{novel_id}/memory-index-candidates/{candidate_id}/model")
async def model_memory_index_candidate(novel_id: str, candidate_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """作者按需把路人候选升级为正式人物，并启动完整人物建模。"""
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    candidate = db.query(models.CharacterCandidate).filter_by(id=candidate_id, novel_id=novel.id if novel else "").first() if novel else None
    if not candidate or candidate.status not in {"pending", "merged"}:
        raise HTTPException(404, "候选人物不存在或已处理")
    if candidate.cleaning_action in {"unprocessed", "ignore_non_person"}:
        raise NovelDomainError(410021, "该候选尚未通过人物清洗，不能建模", 422)
    active = db.query(models.ImportRun).filter(
        models.ImportRun.novel_id == novel.id,
        models.ImportRun.status.in_(("queued", "running", "cancel_requested")),
    ).first()
    if active:
        raise NovelDomainError(420004, "已有任务执行中，请在任务中心查看进度", 409, active_import_task_data(active))

    accepted_name = candidate.canonical_name if candidate.cleaning_action == "merge_alias" and candidate.canonical_name else candidate.name
    accepted = accept_memory_index_candidate(novel.id, accepted_name, candidate.id, current_user, db)
    character_id = str((accepted.get("data") or {}).get("id") or "")
    character = db.get(models.Character, character_id)
    if not character:
        raise NovelDomainError(410022, "候选人物建档失败", 500)
    run = models.ImportRun(
        novel_id=novel.id,
        trace_id=trace_id(),
        status="queued",
        stage="character_modeling",
        result={
            "characterModeling": True,
            "automatic": False,
            "candidateId": candidate.id,
            "characterId": character.id,
            "characterName": character.name,
            "mentionSegmentCount": candidate.mention_segment_count,
        },
    )
    db.add(run); db.commit(); db.refresh(run)
    logger.info("candidate character modeling queued novel=%s run=%s candidate=%s character=%s name=%s mentions=%s", novel.id, run.id, candidate.id, character.id, character.name, candidate.mention_segment_count)
    schedule_persistent(dispatch_import_run(run.id))
    return response({"runId": run.id, "traceId": run.trace_id, "characterId": character.id, "characterName": character.name}, "候选人物建模任务已进入任务中心")


@app.post("/api/novels/{novel_id}/characters/{character_id}/memory-index")
async def start_character_memory_index(novel_id: str, character_id: str, background_tasks: BackgroundTasks, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    character = db.query(models.Character).filter_by(id=character_id, novel_id=novel.id if novel else "").first() if novel else None
    if not character:
        raise HTTPException(status_code=404, detail={"code": 404404, "msg": "人物不存在"})
    active = db.query(models.ImportRun).filter(models.ImportRun.novel_id == novel.id, models.ImportRun.status.in_(("queued", "running", "cancel_requested"))).first()
    if active:
        raise NovelDomainError(420004, "已有任务执行中，请在任务中心查看进度", 409, active_import_task_data(active))
    run = models.ImportRun(novel_id=novel.id, trace_id=trace_id(), status="queued", stage="character_indexing", total_chapters=0, result={"characterId": character.id})
    db.add(run); db.commit(); db.refresh(run)
    schedule_persistent(dispatch_import_run(run.id))
    return response({"runId": run.id, "traceId": run.trace_id, "characterId": character.id}, "人物增量索引任务已进入任务中心")


@app.post("/api/novels/{novel_id}/characters/{character_id}/memory-events")
def create_memory_event(novel_id: str, character_id: str, body: CharacterMemoryEventCreateRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(status_code=404, detail={"code": 404404, "msg": "小说不存在"})
    character = db.query(models.Character).filter_by(id=character_id, novel_id=novel.id).first()
    if not character:
        raise HTTPException(status_code=404, detail={"code": 404404, "msg": "人物不存在"})
    payload = body.model_dump()
    if payload.get("related_character_id") and not db.query(models.Character).filter_by(id=payload["related_character_id"], novel_id=novel.id).first():
        raise NovelDomainError(410017, "关系对象人物不存在", 422)
    review_reason = memory_event_review_reason(payload["value"], payload["quote"], payload["evidence_status"])
    if review_reason:
        payload["review_status"] = "pending"
    duplicate = db.query(models.CharacterMemoryEvent).filter_by(novel_id=novel.id, character_id=character.id, event_type=payload["event_type"], value=payload["value"], valid_from_source_segment=payload["valid_from_source_segment"]).first()
    if duplicate:
        return response(memory_event_data(duplicate), "重复事件，已返回已有记录")
    new_end = payload["valid_to_source_segment"] if payload["valid_to_source_segment"] is not None else 2147483647
    conflict = db.query(models.CharacterMemoryEvent).filter(models.CharacterMemoryEvent.novel_id == novel.id, models.CharacterMemoryEvent.character_id == character.id, models.CharacterMemoryEvent.event_type == payload["event_type"], models.CharacterMemoryEvent.value != payload["value"], models.CharacterMemoryEvent.valid_from_source_segment <= new_end, ((models.CharacterMemoryEvent.valid_to_source_segment.is_(None)) | (models.CharacterMemoryEvent.valid_to_source_segment >= payload["valid_from_source_segment"])), models.CharacterMemoryEvent.review_status != "ignored").first()
    item = models.CharacterMemoryEvent(novel_id=novel.id, character_id=character.id, **payload)
    if conflict and payload["review_status"] == "accepted":
        item.review_status = "pending"
    db.add(item)
    db.flush()
    record_memory_event_version(db, item, "create")
    if item.review_status == "accepted":
        close_previous_memory_states(db, item)
        sync_relationship_projection(db, item)
    db.commit()
    db.refresh(item)
    return response({"event": memory_event_data(item), "conflict": memory_event_data(conflict) if conflict else None}, "检测到同类型时间冲突，已转为待确认" if conflict else "人物记忆事件已创建")


@app.post("/api/novels/{novel_id}/characters/{character_id}/memory-events/{event_id}/decision")
def decide_memory_event(novel_id: str, character_id: str, event_id: str, action: str = Query(..., pattern="^(accept|ignore)$"), current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    item = db.query(models.CharacterMemoryEvent).filter_by(id=event_id, novel_id=novel.id if novel else "", character_id=character_id).first() if novel else None
    if not item:
        raise HTTPException(status_code=404, detail={"code": 404404, "msg": "记忆事件不存在"})
    record_memory_event_version(db, item, action)
    item.review_status = "accepted" if action == "accept" else "ignored"
    if action == "accept" and item.evidence_status == "insufficient_evidence":
        item.evidence_status = "manually_confirmed"
    superseded = []
    if action == "accept":
        superseded = close_previous_memory_states(db, item)
        sync_relationship_projection(db, item)
    db.commit()
    db.refresh(item)
    return response({"event": memory_event_data(item), "supersededEventIds": superseded}, "记忆事件已采纳" if action == "accept" else "记忆事件已忽略")

@app.patch("/api/novels/{novel_id}/characters/{character_id}/memory-events/{event_id}")
def edit_memory_event(novel_id: str, character_id: str, event_id: str, body: CharacterMemoryEventCreateRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    item = db.query(models.CharacterMemoryEvent).filter_by(id=event_id, novel_id=novel.id if novel else "", character_id=character_id).first() if novel else None
    if not item:
        raise HTTPException(status_code=404, detail={"code": 404404, "msg": "记忆事件不存在"})
    record_memory_event_version(db, item, "edit")
    payload = body.model_dump()
    if payload.get("related_character_id") and not db.query(models.Character).filter_by(id=payload["related_character_id"], novel_id=novel.id).first():
        raise NovelDomainError(410017, "关系对象人物不存在", 422)
    for key, value in payload.items():
        setattr(item, key, value)
    item.review_status = "pending"
    db.commit(); db.refresh(item)
    return response(memory_event_data(item), "记忆事件已修改，等待确认")

@app.post("/api/novels/{novel_id}/characters/{character_id}/memory-events/{event_id}/split")
def split_memory_event(novel_id: str, character_id: str, event_id: str, parts: list[CharacterMemoryEventCreateRequest], current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    original = db.query(models.CharacterMemoryEvent).filter_by(id=event_id, novel_id=novel.id if novel else "", character_id=character_id).first() if novel else None
    if not original or not parts:
        raise HTTPException(status_code=404, detail={"code": 404404, "msg": "事件不存在或拆分内容为空"})
    record_memory_event_version(db, original, "split")
    original.review_status = "ignored"
    created = []
    for part in parts:
        payload = part.model_dump(); payload["review_status"] = "pending"
        related_id = payload.get("related_character_id")
        if related_id and not db.query(models.Character).filter_by(id=related_id, novel_id=novel.id).first():
            raise NovelDomainError(410017, "关系对象人物不存在", 422)
        item = models.CharacterMemoryEvent(novel_id=novel.id, character_id=character_id, replaces_event_id=original.id, **payload)
        db.add(item); created.append(item)
    db.flush()
    for item in created:
        record_memory_event_version(db, item, "create_from_split")
    original.superseded_by = created[0].id if created else None
    original.replacement_event_ids = [item.id for item in created]
    db.commit()
    return response({"replacedEventId": event_id, "events": [memory_event_data(item) for item in created]}, "事件已拆分为待确认候选")


@app.get("/api/novels/{novel_id}/characters/{character_id}/memory-events/{event_id}/versions")
def list_memory_event_versions(novel_id: str, character_id: str, event_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    event = db.query(models.CharacterMemoryEvent).filter_by(id=event_id, novel_id=novel_id, character_id=character_id).first()
    if not novel or not event: raise HTTPException(404, "记忆事件不存在")
    rows = db.query(models.CharacterMemoryEventVersion).filter_by(event_id=event_id, novel_id=novel_id).order_by(models.CharacterMemoryEventVersion.created_at.desc(), models.CharacterMemoryEventVersion.id.desc()).all()
    versions = [{"id": "current", "action": "current", "snapshot": memory_event_data(event), "createdAt": event.updated_at.isoformat() if event.updated_at else None}]
    versions.extend({"id": item.id, "action": item.action, "snapshot": item.snapshot, "createdAt": item.created_at.isoformat() if item.created_at else None} for item in rows)
    return list_response(versions)


@app.get("/api/novels/{novel_id}/characters/{character_id}/snapshot")
def character_memory_snapshot(novel_id: str, character_id: str, source_segment_order: int = Query(0, ge=0), current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    character = db.query(models.Character).filter_by(id=character_id, novel_id=novel.id if novel else "").first() if novel else None
    if not character:
        raise HTTPException(status_code=404, detail={"code": 404404, "msg": "人物不存在"})
    chapters = db.query(models.Chapter).filter_by(novel_id=novel.id).order_by(models.Chapter.source_segment_order.asc(), models.Chapter.sequence.asc(), models.Chapter.id.asc()).all()
    max_target = max((chapter.source_segment_order or chapter.sequence for chapter in chapters), default=0)
    target = source_segment_order or max_target
    anchor = next((chapter for chapter in chapters if (chapter.source_segment_order or chapter.sequence) == target), None)
    if not anchor and chapters:
        raise NovelDomainError(410026, "对话时间点对应的章节不存在", 422)
    if not anchor and source_segment_order:
        raise NovelDomainError(410026, "对话时间点对应的章节不存在", 422)
    if character.first_appearance_chapter and target < character.first_appearance_chapter:
        raise NovelDomainError(410027, "该人物在所选章节尚未登场", 422)
    known_rows = db.query(models.CharacterMemoryEvent).filter(
        models.CharacterMemoryEvent.novel_id == novel.id,
        models.CharacterMemoryEvent.character_id == character.id,
        models.CharacterMemoryEvent.valid_from_source_segment <= target,
        models.CharacterMemoryEvent.review_status == "accepted",
        models.CharacterMemoryEvent.evidence_status.in_(("verified", "manually_confirmed")),
        models.CharacterMemoryEvent.knowledge_scope.in_(("character_known", "character_misunderstood")),
    ).order_by(models.CharacterMemoryEvent.valid_from_source_segment.asc(), models.CharacterMemoryEvent.created_at.asc(), models.CharacterMemoryEvent.id.asc()).all()
    active_ids = {
        row.id for row in known_rows
        if row.valid_to_source_segment is None or row.valid_to_source_segment >= target
    }
    chapter_titles = {item.id: item.title for item in chapters}
    sources = [{"eventId": row.id, "sourceChapterId": row.source_chapter_id, "chapterTitle": chapter_titles.get(row.source_chapter_id, ""), "eventType": row.event_type, "knowledgeScope": row.knowledge_scope, "sourceSegmentOrder": row.valid_from_source_segment, "quote": row.quote} for row in known_rows if row.quote]
    current: dict[str, dict] = {}
    historical = []
    relationship_groups: dict[str, list[models.CharacterMemoryEvent]] = {}
    for row in known_rows:
        if row.event_type == "relationship":
            unbound_name = row.memory_key.removeprefix("relationship.") if row.memory_key.startswith("relationship.") else row.value
            relationship_groups.setdefault(row.related_character_id or f"unbound:{unbound_name}", []).append(row)
            continue
        if row.id in active_ids and row.event_type in _CURRENT_MEMORY_TYPES:
            base_key = row.memory_key or row.event_type
            key = base_key if base_key not in current else f"{base_key}:{row.id}"
            current[key] = memory_event_data(row)
        else:
            historical.append(memory_event_data(row))
    # Character 表是全书当前投影，只允许最新时间点回退使用，避免早期对话泄漏后期信息。
    if not current and target == max_target:
        if character.identity:
            current["identity"] = {"value": character.identity, "source": "character_profile"}
        if character.current_state:
            current["situation"] = {"value": character.current_state, "source": "character_profile"}
        if character.goal:
            current["goal"] = {"value": character.goal, "source": "character_profile"}
    related_ids = [key for key in relationship_groups if not key.startswith("unbound:")]
    related_names = {item.id: item.name for item in db.query(models.Character).filter(models.Character.novel_id == novel.id, models.Character.id.in_(related_ids)).all()} if related_ids else {}
    relationships = []
    for key, items in relationship_groups.items():
        active = [item for item in items if item.id in active_ids]
        if not active:
            continue
        relationships.append({"relatedCharacterId": None if key.startswith("unbound:") else key, "relatedCharacterName": key.removeprefix("unbound:") if key.startswith("unbound:") else related_names.get(key, "未绑定人物"), "current": memory_event_data(active[-1]), "history": [memory_event_data(item) for item in items]})
    snapshot_character = character_data(character)
    if target < max_target:
        for key in ("identity", "traits", "motivation", "goal", "voice", "currentState", "publicImage"):
            snapshot_character[key] = ""
        snapshot_character["status"] = "active"
    anchor_data = {"chapterId": anchor.id if anchor else None, "sequence": anchor.sequence if anchor else 0, "sourceSegmentOrder": target, "chapterTitle": anchor.title if anchor else "尚无章节", "anchorType": "chapter_end"}
    return response({"character": snapshot_character, "anchor": anchor_data, "targetSourceSegment": target, "historicalFacts": historical, "currentState": current, "relationships": relationships, "sources": sources, "pendingReviewCount": db.query(models.CharacterMemoryEvent).filter_by(novel_id=novel.id, character_id=character.id, review_status="pending").count()})


@app.post("/api/novels/{novel_id}/characters/{character_id}/script-dialogue")
async def script_dialogue(novel_id: str, character_id: str, body: ScriptDialogueRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    character = db.query(models.Character).filter_by(id=character_id, novel_id=novel.id if novel else "").first() if novel else None
    if not character:
        raise HTTPException(status_code=404, detail={"code": 404404, "msg": "人物不存在"})
    snapshot_result = character_memory_snapshot(novel_id, character_id, body.source_segment_order, current_user, db)
    snapshot = snapshot_result["data"]
    retrieved_passages = retrieve_character_dialogue_sources(
        db,
        novel.id,
        character,
        body.message,
        target_source_segment=snapshot["targetSourceSegment"],
    )
    snapshot["retrievedPassages"] = retrieved_passages
    result, model = await run_script_dialogue(
        platform_user_id=current_user.platform_user_id,
        character=character,
        snapshot=snapshot,
        message=body.message,
        dialogue_history=[item.model_dump() for item in body.history],
    )
    sources = [*snapshot.get("sources", []), *retrieved_passages]
    return response({"characterId": character.id, "reply": result, "model": model, "persistent": False, "anchor": snapshot.get("anchor"), "targetSourceSegment": snapshot["targetSourceSegment"], "sources": sources}, "人物临时对话完成")


@app.post("/api/novels/{novel_id}/experiences")
async def create_experience(novel_id: str, body: ExperienceCreateRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    chapters = db.query(models.Chapter).filter_by(novel_id=novel.id).filter(models.Chapter.source_segment_order >= body.start_source_segment, models.Chapter.source_segment_order <= body.end_source_segment).count()
    if body.start_source_segment > body.end_source_segment or body.end_source_segment - body.start_source_segment >= 30:
        raise HTTPException(400, "体验副本必须选择连续且不超过30章的范围")
    if not chapters:
        raise HTTPException(400, "所选章节不存在")
    item = models.ExperienceSnapshot(novel_id=novel.id, title=body.title or f"第{body.start_source_segment}—{body.end_source_segment}章体验", start_source_segment=body.start_source_segment, end_source_segment=body.end_source_segment, status="queued", snapshot={}, token_usage={})
    db.add(item); db.flush()
    run = models.ImportRun(novel_id=novel.id, trace_id=trace_id(), status="queued", stage="experience_snapshot", total_chapters=chapters, result={"experienceSnapshotId": item.id, "experience": True, "importMode": "experience"})
    db.add(run); db.commit(); db.refresh(item); db.refresh(run)
    schedule_persistent(dispatch_import_run(run.id))
    return response({"id": item.id, "title": item.title, "startSourceSegment": item.start_source_segment, "endSourceSegment": item.end_source_segment, "status": item.status, "runId": run.id, "traceId": run.trace_id}, "体验副本已进入任务中心")


@app.get("/api/novels/{novel_id}/experiences")
def list_experiences(novel_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    items = db.query(models.ExperienceSnapshot).filter_by(novel_id=novel.id).order_by(models.ExperienceSnapshot.created_at.desc()).all()
    return list_response([{"id": item.id, "title": item.title, "startSourceSegment": item.start_source_segment, "endSourceSegment": item.end_source_segment, "status": item.status, "createdAt": item.created_at.isoformat() if item.created_at else None} for item in items])


@app.get("/api/novels/{novel_id}/experiences/{experience_id}")
def get_experience(novel_id: str, experience_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    item = db.query(models.ExperienceSnapshot).filter_by(id=experience_id, novel_id=novel_id).first() if novel else None
    if not item:
        raise HTTPException(404, "体验副本不存在")
    if item.status in {"queued", "running"}:
        linked_run = next((run for run in db.query(models.ImportRun).filter_by(novel_id=novel_id).order_by(models.ImportRun.created_at.desc()).all() if str((run.result or {}).get("experienceSnapshotId") or "") == item.id), None)
        if linked_run and linked_run.status in {"cancelled", "failed"}:
            item.status = "cancelled" if linked_run.status == "cancelled" else "failed"
            item.error = linked_run.error or ("任务已停止" if linked_run.status == "cancelled" else "任务执行失败")
            db.commit()
    sessions = db.query(models.ExperienceSession).filter_by(snapshot_id=item.id).order_by(models.ExperienceSession.created_at.desc()).all()
    return response({"id": item.id, "title": item.title, "startSourceSegment": item.start_source_segment, "endSourceSegment": item.end_source_segment, "status": item.status, "error": item.error or "", "snapshot": item.snapshot or {}, "sessions": [{"id": s.id, "characterId": s.character_id, "characterName": s.selected_character_name, "title": (s.state or {}).get("title") or s.selected_character_name, "createdAt": s.created_at.isoformat() if s.created_at else None, "perspective": s.perspective, "status": s.status, "turn": s.turn} for s in sessions]}, "体验副本详情")


def _experience_runtime_snapshot(db: Session, novel_id: str, snapshot: dict) -> dict:
    """仅在副本运行时按章节引用加载正史正文，不把正文写回副本快照。"""
    if not isinstance(snapshot, dict) or isinstance(snapshot.get("chapters"), list):
        return snapshot
    refs = snapshot.get("chapterRefs")
    if not isinstance(refs, list):
        return snapshot
    ids = [str(item.get("id")) for item in refs if isinstance(item, dict) and item.get("id")]
    if not ids:
        return snapshot
    rows = db.query(models.Chapter).filter(
        models.Chapter.novel_id == novel_id,
        models.Chapter.id.in_(ids),
    ).all()
    by_id = {str(row.id): row for row in rows}
    hydrated = dict(snapshot)
    hydrated["chapters"] = [{
        "id": str(ref.get("id")),
        "sequence": ref.get("sequence") or chapter.sequence,
        "sourceSegmentOrder": ref.get("sourceSegmentOrder") or chapter.source_segment_order or chapter.sequence,
        "title": chapter.title,
        "body": chapter.body,
    } for ref in refs if isinstance(ref, dict) and (chapter := by_id.get(str(ref.get("id"))))]
    return hydrated


@app.get("/api/novels/{novel_id}/experiences/{experience_id}/role-cards")
def list_experience_role_cards(novel_id: str, experience_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    item = db.query(models.ExperienceSnapshot).filter_by(id=experience_id, novel_id=novel_id).first() if novel else None
    if not item:
        raise HTTPException(404, "体验副本不存在")
    snapshot = item.snapshot or {}
    cards = []
    first_extracted = {}
    for chapter in snapshot.get("chapterExtractions") or []:
        for character in chapter.get("characters") or []:
            if isinstance(character, dict) and character.get("name"):
                first_extracted.setdefault(str(character["name"]), character)
    for row in snapshot.get("characters") or []:
        first_row = first_extracted.get(str(row.get("name") or ""))
        first_attributes = first_row.get("attributes") if isinstance(first_row, dict) else None
        first_attributes = first_attributes if isinstance(first_attributes, dict) else {}
        current_state = row.get("currentState")
        if first_row is not None:
            current_state = first_attributes.get("current_state") or first_attributes.get("currentState") or first_attributes.get("当前状态") or ""
        cards.append({**row, "currentState": current_state, "source": "existing_character", "roleMode": "original", "sourceSegmentOrders": [row.get("firstAppearanceChapter")] if row.get("firstAppearanceChapter") else []})
    existing_names = {str(row.get("name") or "") for row in cards}
    for row in snapshot.get("extractedCharacters") or []:
        if row.get("name") not in existing_names:
            attributes = row.get("attributes") if isinstance(row.get("attributes"), dict) else {}
            first_attributes = first_extracted.get(str(row.get("name") or ""), {}).get("attributes")
            first_attributes = first_attributes if isinstance(first_attributes, dict) else {}
            traits_attributes = dict(attributes)
            first_state = first_attributes.get("current_state") or first_attributes.get("currentState") or first_attributes.get("当前状态") or ""
            if first_extracted.get(str(row.get("name") or "")) is not None:
                traits_attributes["current_state"] = first_state
            cards.append({
                "id": None,
                "name": row.get("name"),
                "aliases": [],
                "role": "supporting",
                "identity": str(attributes.get("identity") or attributes.get("身份") or ""),
                "affiliation": str(attributes.get("affiliation") or attributes.get("所属势力") or attributes.get("势力") or ""),
                "ability": str(attributes.get("ability") or attributes.get("能力") or attributes.get("实力") or attributes.get("修为") or ""),
                "appearance": str(row.get("appearance") or ""),
                "traits": json.dumps(traits_attributes, ensure_ascii=False),
                "currentState": str(first_state),
                "source": "chapter_extraction",
                "sourceSegmentOrders": row.get("sourceSegmentOrders", []),
                "roleMode": "replacement",
            })
    return list_response(cards, "副本角色卡")


@app.post("/api/novels/{novel_id}/experiences/{experience_id}/sessions")
async def create_experience_session(novel_id: str, experience_id: str, body: ExperienceSessionCreateRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    snapshot = db.query(models.ExperienceSnapshot).filter_by(id=experience_id, novel_id=novel_id).first() if novel else None
    character = db.query(models.Character).filter_by(id=body.character_id, novel_id=novel_id).first() if novel and body.character_id else None
    if not character and snapshot and body.character_name:
        extracted = next((row for row in (snapshot.snapshot or {}).get("extractedCharacters", []) if row.get("name") == body.character_name), None)
        if extracted:
            attrs = extracted.get("attributes") or {}
            character = models.Character(novel_id=novel_id, name=body.character_name, role="supporting", identity=str(attrs.get("身份") or attrs.get("identity") or ""), traits=json.dumps(attrs, ensure_ascii=False), status="active")
    if not snapshot or not character:
        raise HTTPException(404, "体验副本或人物不存在")
    item = models.ExperienceSession(novel_id=novel_id, snapshot_id=snapshot.id, character_id=character.id if getattr(character, "id", None) else None, selected_character_name=character.name, role_mode=body.role_mode, perspective="third", state={"characterName": character.name}, history=[])
    db.add(item); db.commit(); db.refresh(item)
    context = _experience_runtime_snapshot(db, novel_id, dict(snapshot.snapshot or {}))
    context["experiencePerspective"] = item.perspective
    context["experienceRole"] = character.name
    # 历史信息仅来自创建副本时已完成的按问题回溯；选择人物不会再触发额外 LLM 回溯。
    history_backfill = {
        "questionBacktracking": context.get("historicalQuestions") if isinstance(context.get("historicalQuestions"), list) else [],
        "backtracking": context.get("historicalBacktracking") or {},
    }
    context["historicalBackfill"] = history_backfill
    opening_prompt = "开始副本。只描述当前场景、其他人物的已发生动作、替换角色可观察到的处境和第一个可行动节点；不要替替换角色说话、行动或做决定。"
    try:
        opening, model = await run_experience_scene(character=character, snapshot=context, message=opening_prompt, dialogue_history=[], opening=True)
    except Exception as exc:
        db.delete(item); db.commit()
        raise HTTPException(502, f"副本开场生成失败：{exc}") from exc
    item.history = [{"role": "assistant", "content": opening}]
    item.state = {"characterName": character.name, "phase": "awaiting_user_action", "opening": opening, "historicalBackfill": history_backfill}
    db.commit()
    return response({"id": item.id, "characterId": character.id, "characterName": character.name, "perspective": item.perspective, "roleMode": item.role_mode, "status": item.status, "phase": "awaiting_user_action", "opening": opening, "model": model}, "副本已开场，等待你的行动")


@app.delete("/api/novels/{novel_id}/experiences/{experience_id}/sessions/{session_id}")
async def delete_experience_session(novel_id: str, experience_id: str, session_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    session = db.query(models.ExperienceSession).filter_by(id=session_id, snapshot_id=experience_id, novel_id=novel_id).first() if novel else None
    if not session:
        raise HTTPException(404, "副本对话不存在")
    db.delete(session)
    db.commit()
    return response({"id": session_id}, "副本对话已永久删除")


@app.get("/api/novels/{novel_id}/experiences/{experience_id}/sessions/{session_id}")
async def get_experience_session(novel_id: str, experience_id: str, session_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    session = db.query(models.ExperienceSession).filter_by(id=session_id, snapshot_id=experience_id, novel_id=novel_id).first() if novel else None
    if not session:
        raise HTTPException(404, "副本对话不存在")
    return response({"id": session.id, "characterName": session.selected_character_name, "title": (session.state or {}).get("title") or session.selected_character_name, "createdAt": session.created_at.isoformat() if session.created_at else None, "perspective": "third", "status": session.status, "turn": session.turn, "history": session.history or [], "state": session.state or {}}, "副本对话详情")


@app.patch("/api/novels/{novel_id}/experiences/{experience_id}/sessions/{session_id}")
async def rename_experience_session(novel_id: str, experience_id: str, session_id: str, body: dict = Body(...), current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    session = db.query(models.ExperienceSession).filter_by(id=session_id, snapshot_id=experience_id, novel_id=novel_id).first() if novel else None
    if not session:
        raise HTTPException(404, "副本对话不存在")
    title = str(body.get("title") or "").strip()[:120]
    state = dict(session.state or {})
    state["title"] = title or session.selected_character_name
    session.state = state
    db.commit()
    return response({"id": session.id, "title": state["title"]}, "副本对话名称已更新")


@app.get("/api/novels/{novel_id}/experiences/{experience_id}/backfills")
async def list_experience_backfills(novel_id: str, experience_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    rows = db.query(models.ExperienceCharacterBackfill).filter_by(novel_id=novel_id, snapshot_id=experience_id).order_by(models.ExperienceCharacterBackfill.updated_at.desc()).all() if novel else []
    return list_response([{"id": row.id, "characterName": row.character_name, "status": row.status, "error": row.error or "", "updatedAt": row.updated_at.isoformat() if row.updated_at else None} for row in rows], "人物回溯状态")


@app.post("/api/novels/{novel_id}/experiences/{experience_id}/sessions/{session_id}/turn")
async def experience_turn(novel_id: str, experience_id: str, session_id: str, body: ExperienceTurnRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    session = db.query(models.ExperienceSession).filter_by(id=session_id, snapshot_id=experience_id, novel_id=novel_id, status="active").first() if novel else None
    snapshot_item = db.get(models.ExperienceSnapshot, experience_id)
    character = db.get(models.Character, session.character_id) if session and session.character_id else None
    if not session or not snapshot_item or not character:
        if not session or not snapshot_item:
            raise HTTPException(404, "体验会话不存在")
        extracted = next((row for row in (snapshot_item.snapshot or {}).get("extractedCharacters", []) if row.get("name") == session.selected_character_name), None)
        if not extracted:
            raise HTTPException(404, "体验角色不存在")
        attrs = extracted.get("attributes") or {}
        character = models.Character(novel_id=novel_id, name=session.selected_character_name, role="supporting", identity=str(attrs.get("身份") or ""), traits=json.dumps(attrs, ensure_ascii=False), status="active")
    history = list(session.history or [])[-10:]
    context = _experience_runtime_snapshot(db, novel_id, dict(snapshot_item.snapshot or {}))
    context["experiencePerspective"] = session.perspective
    context["experienceRole"] = character.name
    context["historicalBackfill"] = (session.state or {}).get("historicalBackfill", {})
    result, model = await run_experience_scene(character=character, snapshot=context, message=body.message, dialogue_history=history)
    history.extend([{"role": "user", "content": body.message}, {"role": "assistant", "content": result}])
    session.history = history[-20:]
    session.turn += 1
    db.commit()
    return response({"sessionId": session.id, "reply": result, "model": model, "turn": session.turn, "perspective": session.perspective, "persistent": False}, "副本回应完成")


@app.post("/api/novels/{novel_id}/characters")
def create_character(novel_id: str, body: CharacterUpdateRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    payload = body.model_dump(exclude_none=True)
    payload.setdefault("aliases", [])
    item = models.Character(novel_id=novel.id, **payload)
    db.add(item)
    db.commit()
    return response(character_data(item), "人物档案已创建")


@app.patch("/api/novels/{novel_id}/characters/{character_id}")
def update_character(novel_id: str, character_id: str, body: CharacterUpdateRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    item = db.query(models.Character).filter_by(id=character_id, novel_id=novel_id).first()
    if not novel or not item:
        raise HTTPException(404, "人物不存在")
    before = item.current_state
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(item, key, value)
    if before != item.current_state:
        item.change_log = ([* (item.change_log or []), {"chapter": body.first_appearance_chapter, "change": item.current_state}])[-10:]
    db.commit()
    return response(character_data(item), "人物档案已保存")


@app.post("/api/novels/{novel_id}/characters/{character_id}/aliases")
def update_character_alias(novel_id: str, character_id: str, alias: str = Query(..., min_length=1, max_length=120), action: str = Query("add", pattern="^(add|remove)$"), current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    item = db.query(models.Character).filter_by(id=character_id, novel_id=novel_id).first()
    if not novel or not item:
        raise HTTPException(404, "人物不存在")
    aliases = [value for value in (item.aliases or []) if value and value != item.name]
    if action == "add" and alias != item.name and alias not in aliases:
        aliases.append(alias)
    elif action == "remove":
        aliases = [value for value in aliases if value != alias]
    item.aliases = aliases
    db.commit(); db.refresh(item)
    return response(character_data(item), "人物别名已更新")


@app.post("/api/novels/{novel_id}/characters/merge")
def merge_characters(novel_id: str, body: CharacterMergeRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    target = db.query(models.Character).filter_by(id=body.target_character_id, novel_id=novel_id).first()
    source_ids = [item for item in dict.fromkeys(body.source_character_ids) if item != body.target_character_id]
    sources = db.query(models.Character).filter(models.Character.novel_id == novel_id, models.Character.id.in_(source_ids)).all() if source_ids else []
    if not novel or not target or len(sources) != len(source_ids): raise HTTPException(404, "待合并人物不存在")
    aliases = list(dict.fromkeys([*(target.aliases or []), *(item.name for item in sources), *(alias for item in sources for alias in (item.aliases or []))]))
    target.aliases = [item for item in aliases if item and item != target.name]
    moved_events = deduplicated_events = moved_relationships = 0
    profile_fields = ("identity", "traits", "motivation", "goal", "voice", "current_state", "public_image")
    versioned_event_ids: set[str] = set()
    for source in sources:
        for field in profile_fields:
            if not getattr(target, field) and getattr(source, field):
                setattr(target, field, getattr(source, field))
        if source.first_appearance_chapter and (not target.first_appearance_chapter or source.first_appearance_chapter < target.first_appearance_chapter):
            target.first_appearance_chapter = source.first_appearance_chapter
        if source.status == "active":
            target.status = "active"
        merged_log = []
        seen_log = set()
        for item in [*(target.change_log or []), *(source.change_log or [])]:
            key = repr(item)
            if key not in seen_log:
                seen_log.add(key)
                merged_log.append(item)
        target.change_log = merged_log[-20:]
        for event in db.query(models.CharacterMemoryEvent).filter_by(novel_id=novel_id, character_id=source.id).all():
            record_memory_event_version(db, event, "merge_character")
            versioned_event_ids.add(event.id)
            duplicate = db.query(models.CharacterMemoryEvent).filter(models.CharacterMemoryEvent.character_id == target.id, models.CharacterMemoryEvent.event_type == event.event_type, models.CharacterMemoryEvent.value == event.value, models.CharacterMemoryEvent.valid_from_source_segment == event.valid_from_source_segment, models.CharacterMemoryEvent.id != event.id).first()
            event.character_id = target.id
            if duplicate:
                event.review_status, event.superseded_by, event.replacement_event_ids = "ignored", duplicate.id, [duplicate.id]; deduplicated_events += 1
            else: moved_events += 1
        for event in db.query(models.CharacterMemoryEvent).filter_by(novel_id=novel_id, related_character_id=source.id).all():
            if event.id not in versioned_event_ids:
                record_memory_event_version(db, event, "merge_related_character")
                versioned_event_ids.add(event.id)
            event.related_character_id = target.id
        for relation in db.query(models.CharacterRelationship).filter((models.CharacterRelationship.from_character_id == source.id) | (models.CharacterRelationship.to_character_id == source.id)).all():
            from_id = target.id if relation.from_character_id == source.id else relation.from_character_id
            to_id = target.id if relation.to_character_id == source.id else relation.to_character_id
            if from_id == to_id:
                db.delete(relation); continue
            duplicate_relation = db.query(models.CharacterRelationship).filter_by(novel_id=novel_id, from_character_id=from_id, to_character_id=to_id, relation_type=relation.relation_type).first()
            if duplicate_relation and duplicate_relation.id != relation.id:
                if relation.current_state and not duplicate_relation.current_state: duplicate_relation.current_state = relation.current_state
                db.delete(relation)
            else:
                relation.from_character_id, relation.to_character_id = from_id, to_id; moved_relationships += 1
        # 历史表保留至数据迁移完成；这里只维护外键，记忆包不再参与业务链路。
        db.query(models.CharacterMemoryPackage).filter_by(novel_id=novel_id, character_id=source.id).update({"character_id": target.id}, synchronize_session=False)
        db.query(models.CharacterCandidate).filter_by(novel_id=novel_id, character_id=source.id).update({"character_id": target.id, "status": "accepted"}, synchronize_session=False)
        db.delete(source)
    db.commit(); db.refresh(target)
    return response({"character": character_data(target), "mergedCharacterIds": source_ids, "movedEvents": moved_events, "deduplicatedEvents": deduplicated_events, "movedRelationships": moved_relationships}, "重复人物已合并")


@app.delete("/api/novels/{novel_id}/characters/{character_id}")
def delete_character(novel_id: str, character_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    item = db.query(models.Character).filter_by(id=character_id, novel_id=novel_id).first()
    if not novel or not item:
        raise HTTPException(404, "人物不存在")
    db.query(models.CharacterRelationship).filter((models.CharacterRelationship.from_character_id == item.id) | (models.CharacterRelationship.to_character_id == item.id)).delete(synchronize_session=False)
    db.delete(item)
    db.commit()
    return response(None, "人物档案已删除")


@app.get("/api/novels/{novel_id}/relationships")
def list_relationships(novel_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    ensure_import_characters(db, novel.id)
    names = {item.id: item.name for item in db.query(models.Character).filter_by(novel_id=novel.id).all()}
    return list_response([relationship_data(item, names) for item in db.query(models.CharacterRelationship).filter_by(novel_id=novel.id).order_by(models.CharacterRelationship.started_chapter.asc(), models.CharacterRelationship.created_at.asc()).all()])


@app.post("/api/novels/{novel_id}/relationships")
def create_relationship(novel_id: str, body: RelationshipUpdateRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    valid_ids = {item.id for item in db.query(models.Character).filter_by(novel_id=novel_id).all()}
    if not novel or body.from_character_id not in valid_ids or body.to_character_id not in valid_ids or body.from_character_id == body.to_character_id:
        raise NovelDomainError(410007, "请选择同一本书中的两个不同人物", 422)
    item = models.CharacterRelationship(novel_id=novel_id, **body.model_dump())
    db.add(item)
    db.commit()
    return response(relationship_data(item, {entry.id: entry.name for entry in db.query(models.Character).filter_by(novel_id=novel_id).all()}), "人物关系已创建")


@app.patch("/api/novels/{novel_id}/relationships/{relationship_id}")
def update_relationship(novel_id: str, relationship_id: str, body: RelationshipUpdateRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    item = db.query(models.CharacterRelationship).filter_by(id=relationship_id, novel_id=novel_id).first()
    if not novel or not item:
        raise HTTPException(404, "人物关系不存在")
    for key, value in body.model_dump().items():
        setattr(item, key, value)
    db.commit()
    names = {entry.id: entry.name for entry in db.query(models.Character).filter_by(novel_id=novel_id).all()}
    return response(relationship_data(item, names), "人物关系已保存")


@app.delete("/api/novels/{novel_id}/relationships/{relationship_id}")
def delete_relationship(novel_id: str, relationship_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    item = db.query(models.CharacterRelationship).filter_by(id=relationship_id, novel_id=novel_id).first()
    if not novel or not item:
        raise HTTPException(404, "人物关系不存在")
    db.delete(item)
    db.commit()
    return response(None, "人物关系已删除")


@app.get("/api/novels/{novel_id}/chapters/{chapter_id}/proposals")
def list_canon_proposals(novel_id: str, chapter_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    rows = db.query(models.CanonChangeProposal).filter_by(novel_id=novel_id, chapter_id=chapter_id).order_by(models.CanonChangeProposal.created_at.asc()).all()
    return list_response([{"id": row.id, "kind": row.kind, "payload": row.payload, "status": row.status} for row in rows])


@app.post("/api/novels/{novel_id}/proposals/{proposal_id}/decision")
def decide_canon_proposal(novel_id: str, proposal_id: str, body: ProposalDecisionRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    proposal = db.query(models.CanonChangeProposal).filter_by(id=proposal_id, novel_id=novel_id, status="pending").first()
    if not novel or not proposal:
        raise HTTPException(404, "候选变更不存在或已处理")
    source_chapter = db.get(models.Chapter, proposal.chapter_id)
    if body.action == "approve":
        applied, reason = materialize_canon_change_proposal(db, proposal)
        if not applied:
            raise NovelDomainError(410016, reason, 422)
    else:
        proposal.status = "rejected"
    proposal.decided_at = datetime.now(timezone.utc)
    if source_chapter:
        pending_count = db.query(models.CanonChangeProposal).filter_by(chapter_id=source_chapter.id, status="pending").count()
        source_chapter.canon_changes = [{"type": "canon_proposals", "status": "pending" if pending_count else "completed", "summary": f"仍有 {pending_count} 条正史变更候选待确认" if pending_count else "本章正史变更候选已全部处理"}]
    db.commit()
    return response({"id": proposal.id, "status": proposal.status}, "候选变更已处理")


@app.get("/api/novels/{novel_id}/foreshadows")
def list_foreshadows(novel_id: str, status: str = "active", keyword: str = "", current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    if status not in {"planned", "active", "progressing", "resolved", "expired", "ignored"}:
        raise NovelDomainError(410005, "伏笔状态不合法", 422)
    ensure_import_foreshadows(db, novel.id)
    query = db.query(models.Foreshadow).filter_by(novel_id=novel.id, status=status)
    if keyword.strip():
        query = query.filter(models.Foreshadow.title.ilike(f"%{keyword.strip()}%"))
    rows = query.order_by(models.Foreshadow.sort_order.asc(), models.Foreshadow.appearance_chapter.asc(), models.Foreshadow.created_at.asc(), models.Foreshadow.id.asc()).all()
    return list_response([foreshadow_data(item) for item in rows])


@app.patch("/api/novels/{novel_id}/foreshadows/{foreshadow_id}")
def update_foreshadow(novel_id: str, foreshadow_id: str, body: ForeshadowUpdateRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    item = db.query(models.Foreshadow).filter_by(id=foreshadow_id, novel_id=novel_id).first()
    if not novel or not item:
        raise HTTPException(404, "线索不存在")
    item.title, item.content, item.planned_chapter, item.importance, item.related_character_names, item.resolution_chapter, item.resolution_method, item.resolution_effect, item.status = body.title, body.content, body.planned_chapter, body.importance, body.related_character_names, body.resolution_chapter, body.resolution_method, body.resolution_effect, body.status
    db.commit()
    return response(foreshadow_data(item), "线索已保存")


@app.post("/api/novels/{novel_id}/foreshadows/{foreshadow_id}/ignore")
def ignore_foreshadow(novel_id: str, foreshadow_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    item = db.query(models.Foreshadow).filter_by(id=foreshadow_id, novel_id=novel_id).first()
    if not novel or not item:
        raise HTTPException(404, "线索不存在")
    item.status = "ignored"
    db.commit()
    return response(foreshadow_data(item), "线索已忽略，不会进入后续续写上下文")


@app.post("/api/novels/{novel_id}/foreshadows/{foreshadow_id}/resolve")
def resolve_foreshadow(novel_id: str, foreshadow_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    item = db.query(models.Foreshadow).filter_by(id=foreshadow_id, novel_id=novel_id).first()
    if not novel or not item:
        raise HTTPException(404, "线索不存在")
    item.status = "resolved"
    db.commit()
    return response(foreshadow_data(item), "线索已标记为已解决，不会进入后续续写上下文")


@app.post("/api/novels/{novel_id}/foreshadows/{foreshadow_id}/restore")
def restore_foreshadow(novel_id: str, foreshadow_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    item = db.query(models.Foreshadow).filter_by(id=foreshadow_id, novel_id=novel_id).first()
    if not novel or not item:
        raise HTTPException(404, "线索不存在")
    item.status = "active"
    db.commit()
    return response(foreshadow_data(item), "线索已恢复，将进入后续续写上下文")


@app.post("/api/novels/{novel_id}/foreshadows/{foreshadow_id}/move")
def move_foreshadow(novel_id: str, foreshadow_id: str, body: ForeshadowMoveRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    item = db.query(models.Foreshadow).filter_by(id=foreshadow_id, novel_id=novel_id).first()
    if not novel or not item:
        raise HTTPException(404, "线索不存在")
    rows = db.query(models.Foreshadow).filter_by(novel_id=novel.id, status=item.status).order_by(models.Foreshadow.sort_order.asc(), models.Foreshadow.appearance_chapter.asc(), models.Foreshadow.created_at.asc(), models.Foreshadow.id.asc()).all()
    index = next((index for index, row in enumerate(rows) if row.id == item.id), -1)
    target_index = index - 1 if body.direction == "up" else index + 1
    if index < 0 or target_index < 0 or target_index >= len(rows):
        return response(foreshadow_data(item), "已处于当前列表边界")
    target = rows[target_index]
    item.sort_order, target.sort_order = target.sort_order, item.sort_order
    db.commit()
    return response(foreshadow_data(item), "线索排序已调整")


@app.delete("/api/novels/{novel_id}/foreshadows/{foreshadow_id}")
def delete_foreshadow(novel_id: str, foreshadow_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    item = db.query(models.Foreshadow).filter_by(id=foreshadow_id, novel_id=novel_id).first()
    if not novel or not item:
        raise HTTPException(404, "线索不存在")
    db.delete(item)
    db.commit()
    return response(None, "线索已删除")


@app.post("/api/novel-assistant/setup-suggestion")
async def setup_suggestion(body: AssistantPlanRequest, current_user: CurrentUser = Depends(get_current_user)):
    try:
        data = await suggest_novel_setup(current_user.platform_user_id, body.brief, body.target_platform, body.target_words)
    except Exception as exc:
        logger.exception("avatar setup suggestion failed user=%s", current_user.platform_user_id)
        return JSONResponse(status_code=502, content=response(None, "分身暂时无法生成开书方案，请稍后重试", 430002))
    return response(data, "已根据分身画像生成可编辑的开书方案")


@app.post("/api/novels")
def create_novel(body: NovelCreateRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = models.Novel(
        platform_user_id=current_user.platform_user_id,
        title=body.title,
        genre=body.genre,
        genre_tag=body.genre_tag,
        target_platform=body.target_platform,
        target_words=body.target_words,
        source_mode="writing",
        core_promise=body.core_promise,
        protagonist_agency=body.protagonist_agency,
    )
    db.add(novel)
    db.flush()
    unit = models.PlotUnit(
        novel_id=novel.id,
        title=body.plot_unit_title,
        promise=body.plot_unit_promise,
        protagonist_goal=body.protagonist_goal,
        obstacle=body.obstacle,
        payoff=body.payoff,
        forbidden_reveals=body.forbidden_reveals,
        status="active",
    )
    db.add(unit)
    db.commit()
    db.refresh(novel)
    write_artifact(current_user.platform_user_id, novel.id, "setup/novel.json", {
        "novel": novel_data(novel, db),
        "plotUnit": {"id": unit.id, "title": unit.title, "promise": unit.promise},
    })
    return response({**novel_data(novel, db), "plotUnit": {"id": unit.id, "title": unit.title, "status": unit.status}})


@app.patch("/api/novels/{novel_id}/book-setup")
def update_book_setup(novel_id: str, body: BookSetupUpdateRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    novel.core_promise = body.core_promise
    novel.protagonist_agency = body.protagonist_agency
    novel.target_words = body.target_words
    setup = {
        "targetAudience": body.target_audience.strip(),
        "logline": body.logline.strip(),
        "coreConflict": body.core_conflict.strip(),
        "genrePositioning": body.genre_positioning.strip(),
        "irreplaceableContribution": body.irreplaceable_contribution.strip(),
        "expectedSettlement": body.expected_settlement.strip(),
        "coreAssetsBoundary": body.core_assets_boundary.strip(),
    }
    novel.book_setup = setup
    stale_count = invalidate_drafts(db, novel.id, "本书方向已更新")
    db.commit()
    write_artifact(current_user.platform_user_id, novel.id, "setup/book-setup.json", {"corePromise": novel.core_promise, "protagonistAgency": novel.protagonist_agency, "targetWords": novel.target_words, **setup})
    return response({"novel": novel_data(novel), "staleDraftCount": stale_count}, "本书方向已保存；已采纳章节保持不变")


@app.patch("/api/novels/{novel_id}/full-outline")
def update_full_outline(novel_id: str, body: FullOutlineUpdateRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    outline = {
        "overview": body.overview.strip(),
        "ending": body.ending.strip(),
        "emotionalCurve": body.emotional_curve.strip(),
        "keyHooks": body.key_hooks.strip(),
        "endgameReserves": body.endgame_reserves.strip(),
        "progressionLadders": body.progression_ladders.strip(),
        "stages": [
            {
                "title": stage.title.strip(),
                "chapterRange": stage.chapter_range.strip(),
                "goal": stage.goal.strip(),
                "turningPoint": stage.turning_point.strip(),
                "forbiddenReveals": stage.forbidden_reveals.strip(),
            }
            for stage in body.stages
        ],
    }
    novel.full_outline = outline
    stale_count = invalidate_drafts(db, novel.id, "全书大纲已更新")
    db.commit()
    write_artifact(current_user.platform_user_id, novel.id, "setup/full-outline.json", outline)
    return response({"fullOutline": outline, "staleDraftCount": stale_count}, "全书大纲已保存；已采纳章节保持不变")


@app.post("/api/novels/{novel_id}/plot-units")
def create_plot_unit(novel_id: str, body: PlotUnitUpdateRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    next_sequence = (db.query(func.max(models.PlotUnit.sequence)).filter_by(novel_id=novel_id).scalar() or 0) + 1
    if body.status == "active":
        db.query(models.PlotUnit).filter(models.PlotUnit.novel_id == novel_id, models.PlotUnit.status.in_(("active", "in_progress"))).update({"status": "planned"}, synchronize_session=False)
    unit = models.PlotUnit(
        novel_id=novel_id,
        sequence=next_sequence,
        title=body.title,
        promise=body.promise,
        protagonist_goal=body.protagonist_goal,
        obstacle=body.obstacle,
        payoff=body.payoff,
        forbidden_reveals=body.forbidden_reveals,
        status=body.status,
    )
    db.add(unit)
    db.commit()
    return response({"plotUnit": plot_unit_data(unit)}, "剧情单元已创建")


@app.patch("/api/novels/{novel_id}/plot-units/{unit_id}")
def update_plot_unit(novel_id: str, unit_id: str, body: PlotUnitUpdateRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    unit = db.query(models.PlotUnit).filter_by(id=unit_id, novel_id=novel_id).first()
    if not novel or not unit:
        raise HTTPException(404, "小说或剧情单元不存在")
    if body.status == "active":
        db.query(models.PlotUnit).filter(models.PlotUnit.novel_id == novel_id, models.PlotUnit.id != unit_id, models.PlotUnit.status.in_(("active", "in_progress"))).update({"status": "planned"}, synchronize_session=False)
    unit.title, unit.promise, unit.status = body.title, body.promise, body.status
    unit.protagonist_goal, unit.obstacle = body.protagonist_goal, body.obstacle
    unit.payoff, unit.forbidden_reveals = body.payoff, body.forbidden_reveals
    stale_count = invalidate_drafts(db, novel.id, "剧情单元已更新")
    db.commit()
    write_artifact(current_user.platform_user_id, novel.id, f"setup/plot-units/{unit.sequence}.json", plot_unit_data(unit))
    return response({"plotUnit": plot_unit_data(unit), "staleDraftCount": stale_count}, "剧情单元已保存；已采纳章节保持不变")


@app.delete("/api/novels/{novel_id}/plot-units/{unit_id}")
def delete_plot_unit(novel_id: str, unit_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    unit = db.query(models.PlotUnit).filter_by(id=unit_id, novel_id=novel_id).first()
    if not novel or not unit:
        raise HTTPException(404, "小说或剧情单元不存在")
    if db.query(models.Chapter).filter_by(plot_unit_id=unit.id).count():
        raise NovelDomainError(410017, "已有章节归属于该剧情单元，不能删除；请改为归档")
    db.delete(unit)
    db.commit()
    return response(None, "剧情单元已删除")


@app.post("/api/novels/import")
async def import_novel(
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
    file: UploadFile | None = File(default=None),
    content: str = Form(default=""),
    title: str = Form(default=""),
    genre: str = Form(default=""),
    target_platform: str = Form(default="番茄"),
    import_mode: str = Form(default="writing"),
    confirm_incremental: bool = Form(default=False),
    incremental_novel_id: str = Form(default=""),
    db: Session = Depends(get_db),
):
    filename = "pasted.md"
    if file and file.filename:
        if not file.filename.lower().endswith((".txt", ".md", ".zip")):
            raise NovelDomainError(420001, "目前仅支持 .txt、.md 或 .zip 小说文件", 422)
        filename, source_bytes = file.filename, await file.read()
        title = title or file.filename.rsplit(".", 1)[0]
    else:
        source_bytes = content.encode("utf-8")
    if not source_bytes:
        raise NovelDomainError(420002, "未提供可导入的正文", 422)
    if import_mode not in {"writing", "script"}:
        raise NovelDomainError(420007, "导入模式无效", 422)
    resolved_title = (title or "未命名导入小说").strip()[:160]
    existing = None
    if import_mode == "script":
        existing = db.query(models.Novel).filter_by(platform_user_id=current_user.platform_user_id, title=resolved_title, source_mode="script").order_by(models.Novel.updated_at.desc(), models.Novel.id.desc()).first()
    incremental = existing is not None
    if existing and (not confirm_incremental or incremental_novel_id != existing.id):
        chapter_count = db.query(models.Chapter).filter_by(novel_id=existing.id).count()
        raise NovelDomainError(420005, f"已存在同名剧本《{resolved_title}》，确认后可增量导入", 409, {"existingNovelId": existing.id, "title": existing.title, "chapterCount": chapter_count})
    if existing:
        active = db.query(models.ImportRun).filter(models.ImportRun.novel_id == existing.id, models.ImportRun.status.in_(("queued", "running", "cancel_requested"))).first()
        if active:
            raise NovelDomainError(420006, "该剧本已有导入或人物索引任务执行中，请完成后再增量导入", 409, {"runId": active.id, "traceId": active.trace_id})
        novel = existing
        if genre.strip() and not novel.genre:
            novel.genre = genre.strip()[:120]
    else:
        novel = models.Novel(
            platform_user_id=current_user.platform_user_id,
            title=resolved_title,
            genre=genre[:120],
            target_platform=target_platform[:80],
            source_mode=import_mode,
            core_promise="已从已有正文导入；可使用分身助手补全读者契约与剧情规划。",
            protagonist_agency="待从导入正文和作者确认中补全。",
            status="importing",
        )
        db.add(novel)
        db.flush()
        db.add(models.PlotUnit(novel_id=novel.id, title="已导入正文后的续写单元", promise="承接现有剧情并保持人物、因果和文风连续", status="in_progress"))
    existing_chapters = db.query(models.Chapter).filter_by(novel_id=novel.id).all() if incremental else []
    base_sequence = max((item.sequence for item in existing_chapters), default=0)
    base_source_order = max((item.source_segment_order or item.sequence for item in existing_chapters), default=0)
    run = models.ImportRun(novel_id=novel.id, trace_id=trace_id(), status="queued", stage="upload_received", total_chapters=0)
    db.add(run)
    db.flush()
    source_path = f"imports/runs/{run.id}/source.bin"
    run.result = {"filename": filename, "sourcePath": source_path, "importMode": import_mode, "incremental": incremental, "baseSequence": base_sequence, "baseSourceSegmentOrder": base_source_order}
    write_blob(current_user.platform_user_id, novel.id, source_path, source_bytes)
    db.commit()
    schedule_persistent(dispatch_import_run(run.id))
    return response({**novel_data(novel, db), "incremental": incremental, "importedChapterCount": 0, "existingChapterCount": len(existing_chapters), "run": import_run_data(run)}, "增量原稿已接收，正在追加新章节并更新人物索引" if incremental else "原稿已接收，正在后台解析、落库并建立索引")


@app.get("/api/novels/{novel_id}")
def get_novel(novel_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    unit = current_plot_unit(db, novel.id)
    units = db.query(models.PlotUnit).filter_by(novel_id=novel.id).order_by(models.PlotUnit.sequence).all()
    chapters = db.query(models.Chapter).filter_by(novel_id=novel.id).order_by(models.Chapter.sequence).all()
    repaired_titles = False
    for chapter in chapters:
        repaired = normalize_import_title(chapter.title)
        if repaired != chapter.title:
            chapter.title = repaired
            repaired_titles = True
    if repaired_titles:
        db.commit()
    latest_import = db.query(models.ImportRun).filter_by(novel_id=novel.id).order_by(models.ImportRun.created_at.desc()).first()
    # 导入任务是持久化记录；服务重启或旧链路失败后，任务已进入终态但
    # 书籍状态可能仍停留在创建时的 importing。读取详情时同步修正，避免
    # 概览继续显示“导入中”。
    if novel.status == "importing" and latest_import and latest_import.status in {"succeeded", "failed", "cancelled"}:
        if latest_import.status == "succeeded":
            novel.status = "script_ready" if novel.source_mode == "script" else "drafting"
        elif chapters:
            novel.status = "script_ready" if novel.source_mode == "script" else "drafting"
        else:
            novel.status = "import_failed"
        db.commit()
    return response({**novel_data(novel, db), "plotUnit": plot_unit_data(unit) if unit else None, "plotUnits": [plot_unit_data(item) for item in units], "chapters": [chapter_data(item) for item in chapters], "importRun": import_run_data(latest_import) if latest_import else None})


@app.get("/api/novels/{novel_id}/imports/{run_id}")
def get_import_run(novel_id: str, run_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    run = db.query(models.ImportRun).filter_by(id=run_id, novel_id=novel_id).first()
    if not novel or not run:
        raise HTTPException(404, "导入任务不存在")
    return response(import_run_data(run))


@app.get("/api/novels/{novel_id}/next-context")
def get_next_context(novel_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    latest = db.query(models.Chapter).filter_by(novel_id=novel_id).order_by(models.Chapter.sequence.desc()).first()
    return response(tracking_context(db, novel_id, (latest.sequence if latest else 0) + 1))


def chapter_blueprint_data(body: ChapterBlueprintRequest) -> dict:
    return {
        "summary": body.summary.strip(),
        "protagonistGoal": body.protagonist_goal.strip(),
        "targetEmotion": body.target_emotion.strip(),
        "keyChoice": body.key_choice.strip(),
        "characterChange": body.character_change.strip(),
        "endingHook": body.ending_hook.strip(),
        "targetWords": body.target_words,
    }


def chapter_outline_from_blueprint(blueprint: dict) -> str:
    fields = [
        ("本章事件", blueprint.get("summary", "")),
        ("主角目标", blueprint.get("protagonistGoal", "")),
        ("目标情绪", blueprint.get("targetEmotion", "")),
        ("关键选择", blueprint.get("keyChoice", "")),
        ("人物变化", blueprint.get("characterChange", "")),
        ("结尾钩子", blueprint.get("endingHook", "")),
    ]
    return "\n".join(f"{label}：{value}" for label, value in fields if value)


@app.post("/api/novels/{novel_id}/plot-units/suggest")
async def suggest_next_plot_unit(novel_id: str, body: PlanningSuggestionRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    chapters = db.query(models.Chapter).filter_by(novel_id=novel_id, status="accepted").order_by(models.Chapter.sequence).all()
    current = current_plot_unit(db, novel_id)
    suggestion = await suggest_plot_unit(db, novel, chapters, current, body.instruction)
    return response({"suggestion": suggestion}, "已生成剧情单元建议；确认保存前不会写入规划")


@app.post("/api/novels/{novel_id}/chapter-blueprints/suggest")
async def suggest_next_chapter_blueprints(novel_id: str, body: PlanningSuggestionRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    unit = db.query(models.PlotUnit).filter_by(id=body.plot_unit_id, novel_id=novel_id).first() if body.plot_unit_id else current_plot_unit(db, novel_id)
    if not novel or not unit:
        raise NovelDomainError(410018, "请先选择一个有效的剧情单元")
    chapters = db.query(models.Chapter).filter_by(novel_id=novel_id, status="accepted").order_by(models.Chapter.sequence).all()
    suggestions = await suggest_chapter_blueprints(novel, chapters, unit, body.instruction, body.chapter_count)
    return response({"plotUnitId": unit.id, "suggestions": suggestions}, "已生成章节细纲建议；确认保存前不会创建章节")


@app.post("/api/novels/{novel_id}/chapter-blueprints")
def create_chapter_blueprint(novel_id: str, body: ChapterBlueprintRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    unit = db.query(models.PlotUnit).filter_by(id=body.plot_unit_id, novel_id=novel_id).first() if body.plot_unit_id else current_plot_unit(db, novel_id)
    if not novel or not unit:
        raise NovelDomainError(410018, "请先选择一个有效的剧情单元")
    sequence = (db.query(func.max(models.Chapter.sequence)).filter_by(novel_id=novel_id).scalar() or 0) + 1
    blueprint = chapter_blueprint_data(body)
    chapter = models.Chapter(novel_id=novel_id, plot_unit_id=unit.id, sequence=sequence, title=body.title.strip(), outline=chapter_outline_from_blueprint(blueprint), blueprint=blueprint, status="planned")
    db.add(chapter)
    db.commit()
    return response({"chapter": chapter_data(chapter)}, "章节细纲已创建")


@app.patch("/api/novels/{novel_id}/chapter-blueprints/{chapter_id}")
def update_chapter_blueprint(novel_id: str, chapter_id: str, body: ChapterBlueprintRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    chapter = db.query(models.Chapter).filter_by(id=chapter_id, novel_id=novel_id, status="planned").first()
    unit = db.query(models.PlotUnit).filter_by(id=body.plot_unit_id, novel_id=novel_id).first() if body.plot_unit_id else current_plot_unit(db, novel_id)
    if not novel or not chapter or not unit:
        raise NovelDomainError(410019, "只有尚未生成的章节细纲可以编辑")
    blueprint = chapter_blueprint_data(body)
    chapter.plot_unit_id, chapter.title = unit.id, body.title.strip()
    chapter.blueprint, chapter.outline = blueprint, chapter_outline_from_blueprint(blueprint)
    db.commit()
    return response({"chapter": chapter_data(chapter)}, "章节细纲已保存")


@app.delete("/api/novels/{novel_id}/chapter-blueprints/{chapter_id}")
def delete_chapter_blueprint(novel_id: str, chapter_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    chapter = db.query(models.Chapter).filter_by(id=chapter_id, novel_id=novel_id, status="planned").first()
    if not novel or not chapter:
        raise NovelDomainError(410020, "只有尚未生成的章节细纲可以删除")
    db.query(models.GenerationRun).filter_by(chapter_id=chapter.id).delete()
    db.delete(chapter)
    db.commit()
    return response(None, "章节细纲已删除")


@app.post("/api/novels/{novel_id}/chapters/{chapter_id}/generate")
async def generate_blueprint_chapter(novel_id: str, chapter_id: str, body: ChapterGenerateRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    chapter = db.query(models.Chapter).filter_by(id=chapter_id, novel_id=novel_id, status="planned").first()
    if not novel or not chapter:
        raise NovelDomainError(410021, "章节细纲不存在或已经开始生成")
    active_draft = db.query(models.Chapter).filter(models.Chapter.novel_id == novel_id, models.Chapter.id != chapter.id, models.Chapter.status.in_(("drafting", "ready_for_author"))).first()
    if active_draft:
        raise NovelDomainError(410022, f"请先处理第{active_draft.sequence}章草稿，全书同时只能保留一份草稿")
    previous = db.query(models.Chapter).filter_by(novel_id=novel_id, sequence=chapter.sequence - 1).first()
    if previous and previous.status != "accepted":
        raise NovelDomainError(410004, "请先采纳上一章，再生成这章细纲")
    unit = db.query(models.PlotUnit).filter_by(id=chapter.plot_unit_id, novel_id=novel_id).first()
    if not unit:
        raise NovelDomainError(410018, "章节细纲所属的剧情单元不存在")
    blueprint_target_words = int((chapter.blueprint or {}).get("targetWords") or 0)
    effective_target_words = blueprint_target_words if blueprint_target_words >= 500 else body.target_words
    chapter.status = "drafting"
    db.commit()
    run = await generate_chapter(db, novel, chapter, unit, trace_id(), effective_target_words, previous, memory_focus=memory_focus_context(db, novel.id, body.memory_focus, body.resource_focus))
    if run.status == "failed":
        return JSONResponse(status_code=502, content=response({"runId": run.id}, "章节草稿生成失败，请复制 traceId 排查或重试", 430001))
    return response({"runId": run.id, "chapter": chapter_data(chapter), "model": run.model}, "章节草稿已生成：已回填草稿正文、生成上下文与去 AI 味结果；采纳前不会修改故事事实或长期规划")


@app.post("/api/novels/{novel_id}/chapters/first/generate")
async def generate_first(novel_id: str, body: ChapterGenerateRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    unit = current_plot_unit(db, novel.id)
    if not unit:
        raise NovelDomainError(410001, "首个剧情单元缺失")
    chapter = db.query(models.Chapter).filter_by(novel_id=novel.id, sequence=1).first()
    if not chapter:
        chapter = models.Chapter(novel_id=novel.id, plot_unit_id=unit.id, sequence=1, title=body.title or "第一章", outline=body.outline or unit.promise, status="drafting")
        db.add(chapter)
        db.commit()
        db.refresh(chapter)
    elif chapter.status == "accepted":
        raise NovelDomainError(410002, "第一章已采纳，不能直接覆盖")
    else:
        chapter.title = body.title or chapter.title
        chapter.outline = body.outline or chapter.outline
        chapter.status = "drafting"
        db.commit()
    run = await generate_chapter(db, novel, chapter, unit, trace_id(), body.target_words, memory_focus=memory_focus_context(db, novel.id, body.memory_focus, body.resource_focus))
    if run.status == "failed":
        return JSONResponse(status_code=502, content=response({"runId": run.id}, "第一章生成失败，请复制 traceId 排查或重试", 430001))
    return response({"runId": run.id, "chapter": chapter_data(chapter), "model": run.model}, "第一章草稿已生成：已回填草稿正文、生成上下文与去 AI 味结果；采纳前不会修改故事事实或长期规划")


@app.post("/api/novels/{novel_id}/chapters/next/generate")
async def generate_next(novel_id: str, body: ChapterGenerateRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    active_draft = db.query(models.Chapter).filter(models.Chapter.novel_id == novel_id, models.Chapter.status.in_(("drafting", "ready_for_author"))).first()
    if active_draft:
        raise NovelDomainError(410022, f"请先处理第{active_draft.sequence}章草稿，全书同时只能保留一份草稿")
    unit = current_plot_unit(db, novel.id)
    previous = db.query(models.Chapter).filter_by(novel_id=novel.id).order_by(models.Chapter.sequence.desc()).first()
    if not unit or not previous or previous.status != "accepted":
        raise NovelDomainError(410004, "请先采纳当前最新章节，再继续生成")
    pending_review = db.query(models.Chapter).filter_by(novel_id=novel.id, status="accepted").all()
    if any((item.context_pack or {}).get("needsReview") for item in pending_review):
        raise NovelDomainError(410009, "存在重写后待校验章节，请确认无冲突后再继续续写", 409)
    chapter = models.Chapter(novel_id=novel.id, plot_unit_id=unit.id, sequence=previous.sequence + 1, title=body.title or f"第{previous.sequence + 1}章", outline=body.outline, status="drafting")
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    import_run = latest_import_analysis(db, novel.id)
    import_bible = dict(import_run.result or {}) if import_run else None
    if import_bible is not None:
        import_bible["tracking_context"] = tracking_context(db, novel.id, chapter.sequence)
    run = await generate_chapter(db, novel, chapter, unit, trace_id(), body.target_words, previous, import_bible, memory_focus_context(db, novel.id, body.memory_focus, body.resource_focus))
    if run.status == "failed":
        return JSONResponse(status_code=502, content=response({"runId": run.id}, "续写生成失败，请复制 traceId 排查或重试", 430001))
    return response({"runId": run.id, "chapter": chapter_data(chapter), "model": run.model}, "续写草稿已生成：已回填草稿正文、生成上下文与去 AI 味结果；采纳前不会修改故事事实或长期规划")


@app.patch("/api/novels/{novel_id}/chapters/{chapter_id}/draft")
def update_chapter_draft(novel_id: str, chapter_id: str, body: ChapterRevisionRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    chapter = db.query(models.Chapter).filter_by(id=chapter_id, novel_id=novel_id, status="ready_for_author").first()
    if not novel or not chapter:
        raise HTTPException(404, "可编辑草稿不存在")
    snapshot = models.ChapterRevisionSnapshot(novel_id=novel_id, chapter_id=chapter.id, title=draft_history_title(), body=chapter.body, word_count=text_word_count(chapter.body), reason="draft_edit")
    db.add(snapshot)
    chapter.title, chapter.body = body.title.strip() or chapter.title, body.body
    pack = dict(chapter.context_pack or {})
    pack.pop("reviewTask", None)
    pack["draftEdited"] = {"snapshotId": snapshot.id}
    chapter.context_pack = pack
    db.commit()
    return response({"chapter": chapter_data(chapter), "snapshot": snapshot_data(snapshot)}, "草稿已保存，修改前版本已加入本草稿历史")


@app.patch("/api/novels/{novel_id}/chapters/{chapter_id}/revision")
def revise_recent_chapter(novel_id: str, chapter_id: str, body: ChapterRevisionRequest, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    chapter = db.query(models.Chapter).filter_by(id=chapter_id, novel_id=novel_id, status="accepted").first()
    if not novel or not chapter:
        raise HTTPException(404, "已采纳章节不存在")
    latest = db.query(models.Chapter).filter_by(novel_id=novel_id, status="accepted").order_by(models.Chapter.sequence.desc()).first()
    if latest.sequence - chapter.sequence >= 10:
        raise NovelDomainError(410008, "仅允许修订最近 10 章已采纳章节", 409)
    quality = revision_quality_report(chapter.body, body.body)
    if quality["blocking"]:
        raise NovelDomainError(410010, "修订草稿未通过基础质量检查", 422)
    before_title, before_body = chapter.title, chapter.body
    impact = revision_impact_report(db, novel_id, chapter, before_body, body.body)
    snapshot = models.ChapterRevisionSnapshot(novel_id=novel_id, chapter_id=chapter.id, title=before_title, body=before_body, word_count=text_word_count(before_body), reason="revision")
    db.add(snapshot)
    chapter.title, chapter.body = body.title, body.body
    chapter_pack = dict(chapter.context_pack or {})
    # The replacement has been accepted as canon; do not retain an actionable
    # draft banner for the task that produced it.
    chapter_pack.pop("revisionTask", None)
    # A review evaluates the exact prior body. Once a replacement is accepted,
    # its findings must not be presented as a verdict on the new canon.
    chapter_pack.pop("reviewTask", None)
    chapter_pack["reviewInvalidated"] = {"reason": "chapter_revised"}
    chapter_pack["lastRevision"] = {"snapshotId": snapshot.id, "quality": quality, "impact": impact}
    chapter.context_pack = chapter_pack
    invalidated_memory_event_ids = invalidate_chapter_memory_events(db, chapter)
    affected = db.query(models.Chapter).filter(models.Chapter.novel_id == novel_id, models.Chapter.sequence > chapter.sequence, models.Chapter.status == "accepted").all()
    for item in affected:
        pack = dict(item.context_pack or {}); pack.update({"needsReview": True, "revisionSourceChapter": chapter.sequence}); item.context_pack = pack
    db.commit()
    return response({"chapter": chapter_data(chapter), "snapshot": snapshot_data(snapshot), "quality": quality, "impact": impact, "affectedChapters": [item.sequence for item in affected], "invalidatedMemoryEventIds": invalidated_memory_event_ids, "writingBlocked": bool(affected)}, "章节正史已修订；相关人物记忆已转为待确认")


@app.post("/api/novels/{novel_id}/chapters/{chapter_id}/revision/ai")
async def ai_revise_recent_chapter(novel_id: str, chapter_id: str, body: ChapterAiRevisionRequest, background_tasks: BackgroundTasks, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    chapter = db.query(models.Chapter).filter_by(id=chapter_id, novel_id=novel_id, status="accepted").first()
    latest = db.query(models.Chapter).filter_by(novel_id=novel_id, status="accepted").order_by(models.Chapter.sequence.desc()).first()
    if not novel or not chapter or latest.sequence - chapter.sequence >= 10:
        raise NovelDomainError(410008, "仅允许 AI 修订最近 10 章已采纳章节", 409)
    previous = db.query(models.Chapter).filter_by(novel_id=novel_id, sequence=chapter.sequence - 1).first()
    following = db.query(models.Chapter).filter(models.Chapter.novel_id == novel_id, models.Chapter.sequence > chapter.sequence).order_by(models.Chapter.sequence).limit(3).all()
    source_body = body.draft_body.strip() or chapter.body
    focus_text = "、".join(body.focuses) or "以修改建议为准"
    prompt = f'''你是长篇小说修订编辑。根据修改建议改写“当前章节”正文。必须保留与前章承接，并尽量不破坏后续章节已发生的事实；只输出改写后的正文，不要标题、解释或 Markdown。\n小说：{novel.title}\n优先优化维度：{focus_text}\n修改建议：{body.instruction}\n前章结尾：{(previous.body[-2500:] if previous else '无')}\n当前待修订稿《{chapter.title}》：{source_body[:18000]}\n后续章节事实（不可随意冲突）：{[(item.sequence, item.title, item.body[:1200]) for item in following]}'''
    run = models.GenerationRun(novel_id=novel_id, chapter_id=chapter.id, trace_id=trace_id(), kind="chapter_revision", status="queued", prompt=prompt)
    db.add(run); db.flush()
    pack = dict(chapter.context_pack or {}); pack["revisionTask"] = {"runId": run.id, "status": "queued"}; chapter.context_pack = pack
    db.commit()
    schedule_persistent(dispatch_generation_run(run.id))
    return response({"runId": run.id}, "AI 修订任务已进入任务中心")


@app.post("/api/novels/{novel_id}/chapters/{chapter_id}/memory-reindex")
async def start_chapter_memory_reindex(novel_id: str, chapter_id: str, background_tasks: BackgroundTasks, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    chapter = db.query(models.Chapter).filter_by(id=chapter_id, novel_id=novel_id, status="accepted").first()
    if not novel or not chapter: raise HTTPException(404, "已采纳章节不存在")
    active = db.query(models.ImportRun).filter(models.ImportRun.novel_id == novel.id, models.ImportRun.status.in_(("queued", "running", "cancel_requested"))).first()
    if active: raise NovelDomainError(420004, "已有任务执行中，请在任务中心查看进度", 409, active_import_task_data(active))
    run = models.ImportRun(novel_id=novel.id, trace_id=trace_id(), status="queued", stage="chapter_memory_reindex", total_chapters=1, result={"chapterId": chapter.id})
    db.add(run); db.commit(); db.refresh(run)
    schedule_persistent(dispatch_import_run(run.id))
    return response({"runId": run.id, "traceId": run.trace_id, "chapterId": chapter.id}, "本章人物记忆重新索引任务已进入任务中心")


@app.post("/api/novels/{novel_id}/chapters/{chapter_id}/deslop")
async def deslop_chapter(novel_id: str, chapter_id: str, body: DeslopRequest, background_tasks: BackgroundTasks, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    chapter = db.query(models.Chapter).filter_by(id=chapter_id, novel_id=novel_id, status="accepted").first()
    if not novel or not chapter:
        raise HTTPException(404, "已采纳章节不存在")
    if chapter.context_pack and chapter.context_pack.get("deslopTask", {}).get("status") in ("queued", "running"):
        raise NovelDomainError(410009, "去AI味任务进行中，请稍后", 409)
    source_body = body.draft_body.strip() or chapter.body
    level = _deslop_level(source_body)
    prompt = _build_deslop_prompt(chapter.title, source_body, level)
    run = models.GenerationRun(novel_id=novel_id, chapter_id=chapter.id, trace_id=trace_id(), kind="deslop", status="queued", prompt=prompt)
    db.add(run); db.flush()
    pack = dict(chapter.context_pack or {})
    pack["deslopTask"] = {"runId": run.id, "status": "queued", "level": level}
    chapter.context_pack = pack
    invalidated_memory_event_ids = invalidate_chapter_memory_events(db, chapter)
    db.commit()
    schedule_persistent(dispatch_generation_run(run.id))
    return response({"runId": run.id, "level": level}, f"去AI味任务已启动（{level}），可在任务中心查看进度")


@app.post("/api/novels/{novel_id}/chapters/{chapter_id}/deslop/discard")
def discard_deslop_draft(novel_id: str, chapter_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    chapter = db.query(models.Chapter).filter_by(id=chapter_id, novel_id=novel_id, status="accepted").first()
    if not novel or not chapter:
        raise HTTPException(404, "已采纳章节不存在")
    pack = dict(chapter.context_pack or {})
    pack.pop("deslopTask", None)
    chapter.context_pack = pack
    db.commit()
    return response({"chapter": chapter_data(chapter)}, "去AI味草稿已放弃，原正史保持不变")


@app.post("/api/novels/{novel_id}/chapters/{chapter_id}/review")
async def review_chapter(novel_id: str, chapter_id: str, body: ReviewRequest, background_tasks: BackgroundTasks, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    chapter = db.query(models.Chapter).filter_by(id=chapter_id, novel_id=novel_id, status="accepted").first()
    if not novel or not chapter:
        raise HTTPException(404, "已采纳章节不存在")
    if chapter.context_pack and chapter.context_pack.get("reviewTask", {}).get("status") in ("queued", "running"):
        raise NovelDomainError(410010, "审稿任务进行中，请稍后", 409)
    run = models.GenerationRun(novel_id=novel_id, chapter_id=chapter.id, trace_id=trace_id(), kind="chapter_review", status="queued", prompt=f"review:{chapter.id}")
    db.add(run); db.flush()
    pack = dict(chapter.context_pack or {})
    pack.pop("reviewInvalidated", None)
    pack["reviewTask"] = {"runId": run.id, "status": "queued", "platform": body.platform or novel.target_platform or "番茄"}
    chapter.context_pack = pack
    db.commit()
    schedule_persistent(dispatch_generation_run(run.id))
    return response({"runId": run.id}, "多视角审稿任务已启动，可在任务中心查看进度")


@app.delete("/api/novels/{novel_id}/chapters/{chapter_id}/review")
def clear_review_result(novel_id: str, chapter_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    chapter = db.query(models.Chapter).filter_by(id=chapter_id, novel_id=novel_id, status="accepted").first()
    if not novel or not chapter:
        raise HTTPException(404, "已采纳章节不存在")
    pack = dict(chapter.context_pack or {})
    pack.pop("reviewTask", None)
    chapter.context_pack = pack
    db.commit()
    return response({"chapter": chapter_data(chapter)}, "审稿结果已清除")



def discard_chapter_revision_draft(novel_id: str, chapter_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    chapter = db.query(models.Chapter).filter_by(id=chapter_id, novel_id=novel_id, status="accepted").first()
    if not novel or not chapter:
        raise HTTPException(404, "已采纳章节不存在")
    pack = dict(chapter.context_pack or {})
    pack.pop("revisionTask", None)
    chapter.context_pack = pack
    db.commit()
    return response({"chapter": chapter_data(chapter)}, "AI 替代草稿已放弃，原正史保持不变")


@app.get("/api/novels/{novel_id}/chapters/{chapter_id}/revisions")
def list_chapter_revisions(novel_id: str, chapter_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    chapter = db.query(models.Chapter).filter_by(id=chapter_id, novel_id=novel_id).first()
    if not novel or not chapter:
        raise HTTPException(404, "章节不存在")
    snapshots = db.query(models.ChapterRevisionSnapshot).filter_by(chapter_id=chapter.id).order_by(models.ChapterRevisionSnapshot.created_at.desc(), models.ChapterRevisionSnapshot.id.desc()).all()
    return list_response([snapshot_data(item) for item in snapshots])


@app.post("/api/novels/{novel_id}/chapters/{chapter_id}/revisions/{snapshot_id}/restore")
def restore_chapter_revision(novel_id: str, chapter_id: str, snapshot_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    chapter = db.query(models.Chapter).filter_by(id=chapter_id, novel_id=novel_id, status="accepted").first()
    snapshot = db.query(models.ChapterRevisionSnapshot).filter_by(id=snapshot_id, chapter_id=chapter_id, novel_id=novel_id).first()
    latest = db.query(models.Chapter).filter_by(novel_id=novel_id, status="accepted").order_by(models.Chapter.sequence.desc()).first()
    if not novel or not chapter or not snapshot:
        raise HTTPException(404, "可恢复版本不存在")
    if latest.sequence - chapter.sequence >= 10:
        raise NovelDomainError(410008, "仅允许恢复最近 10 章已采纳章节", 409)
    before_title, before_body = chapter.title, chapter.body
    impact = revision_impact_report(db, novel_id, chapter, before_body, snapshot.body)
    current_snapshot = models.ChapterRevisionSnapshot(novel_id=novel_id, chapter_id=chapter.id, title=before_title, body=before_body, word_count=text_word_count(before_body), reason="before_restore")
    db.add(current_snapshot)
    chapter.title, chapter.body = snapshot.title, snapshot.body
    pack = dict(chapter.context_pack or {})
    pack.pop("revisionTask", None)
    pack.pop("reviewTask", None)
    pack["reviewInvalidated"] = {"reason": "chapter_restored"}
    pack["lastRevision"] = {"snapshotId": current_snapshot.id, "quality": revision_quality_report(before_body, snapshot.body), "impact": impact, "restoredFrom": snapshot.id}
    chapter.context_pack = pack
    affected = db.query(models.Chapter).filter(models.Chapter.novel_id == novel_id, models.Chapter.sequence > chapter.sequence, models.Chapter.status == "accepted").all()
    for item in affected:
        item_pack = dict(item.context_pack or {}); item_pack.update({"needsReview": True, "revisionSourceChapter": chapter.sequence}); item.context_pack = item_pack
    db.commit()
    return response({"chapter": chapter_data(chapter), "impact": impact, "affectedChapters": [item.sequence for item in affected], "invalidatedMemoryEventIds": invalidated_memory_event_ids}, "已恢复历史版本；相关人物记忆已转为待确认")


@app.post("/api/novels/{novel_id}/chapters/revision-review/confirm")
def confirm_revision_review(novel_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    if not novel:
        raise HTTPException(404, "小说不存在")
    rows = db.query(models.Chapter).filter_by(novel_id=novel_id, status="accepted").all()
    cleared = []
    for item in rows:
        pack = dict(item.context_pack or {})
        if pack.pop("needsReview", False):
            pack.pop("revisionSourceChapter", None)
            item.context_pack = pack
            cleared.append(item.sequence)
    db.commit()
    return response({"clearedChapters": cleared}, "已确认后续章节无冲突，续写已解除阻断")


@app.post("/api/novels/{novel_id}/chapters/{chapter_id}/accept")
def accept_chapter(novel_id: str, chapter_id: str, background_tasks: BackgroundTasks, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    chapter = db.query(models.Chapter).filter_by(id=chapter_id, novel_id=novel_id).first()
    if not novel or not chapter:
        raise HTTPException(404, "小说或章节不存在")
    if chapter.status != "ready_for_author":
        raise NovelDomainError(410003, "当前章节尚未完成生成，不能采纳")
    chapter.status = "accepted"
    unit = db.query(models.PlotUnit).filter_by(id=chapter.plot_unit_id).first()
    if unit:
        unit.status = "active"
    db.commit()
    background_tasks.add_task(propose_canon_changes, chapter.id)
    return response({"chapter": chapter_data(chapter)}, "章节已采纳：正文已进入正史并激活当前剧情单元；人物、关系与伏笔将后台自动沉淀为故事事实")


@app.delete("/api/novels/{novel_id}/chapters/{chapter_id}/draft")
def delete_chapter_draft(novel_id: str, chapter_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """删除草稿：同时删除章节记录。适用于完全放弃这一章。"""
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    chapter = db.query(models.Chapter).filter_by(id=chapter_id, novel_id=novel_id).filter(models.Chapter.status.in_(["drafting", "ready_for_author"])).first()
    if not novel or not chapter:
        raise NovelDomainError(410023, "草稿不存在或已采纳，无法删除")
    db.query(models.ChapterRevisionSnapshot).filter_by(chapter_id=chapter.id).delete()
    db.query(models.GenerationRun).filter_by(chapter_id=chapter.id).delete()
    db.delete(chapter)
    db.commit()
    return response(None, "草稿及章节已删除")


@app.post("/api/novels/{novel_id}/chapters/{chapter_id}/draft/discard")
def discard_chapter_draft(novel_id: str, chapter_id: str, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """废弃草稿：章节回退到 planned 状态，保留细纲，下次重新生成。"""
    novel = db.query(models.Novel).filter_by(id=novel_id, platform_user_id=current_user.platform_user_id).first()
    chapter = db.query(models.Chapter).filter_by(id=chapter_id, novel_id=novel_id).filter(models.Chapter.status.in_(["drafting", "ready_for_author"])).first()
    if not novel or not chapter:
        raise NovelDomainError(410024, "草稿不存在或已采纳，无法废弃")
    chapter.status = "planned"
    chapter.body = ""
    pack = dict(chapter.context_pack or {})
    pack.pop("draftEdited", None)
    pack.pop("reviewTask", None)
    chapter.context_pack = pack
    db.query(models.ChapterRevisionSnapshot).filter_by(chapter_id=chapter.id).delete()
    db.query(models.GenerationRun).filter_by(chapter_id=chapter.id).delete()
    db.commit()
    return response({"chapter": chapter_data(chapter)}, "草稿已废弃，章节回退到待生成状态")
