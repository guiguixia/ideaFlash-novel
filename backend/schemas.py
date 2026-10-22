from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SmsScene = Literal["register", "login", "bind", "change", "unbind"]


class LoginRequest(BaseModel):
    username: str
    password: str


class SmsSendRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=20)
    scene: SmsScene


class PhoneLoginRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=20)
    code: str = Field(min_length=4, max_length=12)


class PhoneRegisterRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=20)
    code: str = Field(min_length=4, max_length=12)
    invitation_code: str | None = Field(default=None, max_length=64)
    username: str | None = Field(default=None, min_length=2, max_length=64)


class PhoneBindRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=20)
    code: str = Field(min_length=4, max_length=12)


class SsoRequest(BaseModel):
    token: str | None = None


class NovelCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    genre: str = Field(default="", max_length=120)
    genre_tag: str = Field(default="", max_length=40)
    target_platform: str = Field(default="番茄", max_length=80)
    target_words: int = Field(default=0, ge=0)
    core_promise: str = Field(default="", max_length=2000)
    protagonist_agency: str = Field(default="", max_length=2000)
    plot_unit_title: str = Field(default="第一阶段：开局与立足", max_length=160)
    plot_unit_promise: str = Field(default="", max_length=2000)
    protagonist_goal: str = Field(default="", max_length=2000)
    obstacle: str = Field(default="", max_length=2000)
    payoff: str = Field(default="", max_length=2000)
    forbidden_reveals: str = Field(default="", max_length=2000)


class BookSetupUpdateRequest(BaseModel):
    target_words: int = Field(ge=0, le=100_000_000)
    core_promise: str = Field(min_length=1, max_length=2000)
    protagonist_agency: str = Field(min_length=1, max_length=2000)
    target_audience: str = Field(default="", max_length=1000)
    logline: str = Field(default="", max_length=2000)
    core_conflict: str = Field(default="", max_length=2000)
    genre_positioning: str = Field(default="", max_length=1000)
    irreplaceable_contribution: str = Field(default="", max_length=2000)
    expected_settlement: str = Field(default="", max_length=2000)
    core_assets_boundary: str = Field(default="", max_length=2000)


class ScriptPublicationRequest(BaseModel):
    published: bool


class ChapterResourceFocusRequest(BaseModel):
    character_names: list[str] = Field(default_factory=list, max_length=8)
    relationship_ids: list[str] = Field(default_factory=list, max_length=12)
    foreshadow_ids: list[str] = Field(default_factory=list, max_length=12)


class ChapterGenerateRequest(BaseModel):
    title: str = Field(default="", max_length=160)
    outline: str = Field(default="", max_length=8000)
    target_words: int = Field(default=1800, ge=500, le=5000)
    memory_focus: list[str] = Field(default_factory=list, max_length=8)
    resource_focus: ChapterResourceFocusRequest = Field(default_factory=ChapterResourceFocusRequest)


class ChapterBlueprintRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=4000)
    protagonist_goal: str = Field(default="", max_length=2000)
    target_emotion: str = Field(default="", max_length=400)
    key_choice: str = Field(default="", max_length=2000)
    character_change: str = Field(default="", max_length=2000)
    ending_hook: str = Field(default="", max_length=2000)
    plot_unit_id: str = Field(default="", max_length=32)
    target_words: int = Field(default=1800, ge=500, le=5000)


class ChapterRevisionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=50000)


class ChapterAiRevisionRequest(BaseModel):
    instruction: str = Field(min_length=3, max_length=4000)
    draft_body: str = Field(default="", max_length=50000)
    focuses: list[str] = Field(default_factory=list, max_length=6)


class AssistantPlanRequest(BaseModel):
    brief: str = Field(min_length=3, max_length=4000)
    target_platform: str = Field(default="番茄", max_length=80)
    target_words: int = Field(default=1200000, ge=0)


class FullOutlineStage(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    chapter_range: str = Field(default="", max_length=120)
    goal: str = Field(default="", max_length=2000)
    turning_point: str = Field(default="", max_length=2000)
    forbidden_reveals: str = Field(default="", max_length=2000)


class FullOutlineUpdateRequest(BaseModel):
    overview: str = Field(default="", max_length=8000)
    ending: str = Field(default="", max_length=4000)
    emotional_curve: str = Field(default="", max_length=4000)
    key_hooks: str = Field(default="", max_length=4000)
    endgame_reserves: str = Field(default="", max_length=4000)
    progression_ladders: str = Field(default="", max_length=4000)
    stages: list[FullOutlineStage] = Field(default_factory=list, max_length=8)


class PlotUnitUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    promise: str = Field(default="", max_length=2000)
    protagonist_goal: str = Field(default="", max_length=2000)
    obstacle: str = Field(default="", max_length=2000)
    payoff: str = Field(default="", max_length=2000)
    forbidden_reveals: str = Field(default="", max_length=2000)
    status: str = Field(default="planned", pattern="^(planned|active|completed|archived)$")


class PlanningSuggestionRequest(BaseModel):
    instruction: str = Field(default="", max_length=2000)
    plot_unit_id: str = Field(default="", max_length=32)
    chapter_count: int = Field(default=1, ge=1, le=3)


class ForeshadowUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=4000)
    planned_chapter: int = Field(default=0, ge=0)
    importance: str = Field(default="medium", pattern="^(high|medium|low)$")
    related_character_names: list[str] = Field(default_factory=list, max_length=20)
    resolution_chapter: int = Field(default=0, ge=0)
    resolution_method: str = Field(default="", max_length=32)
    resolution_effect: str = Field(default="", max_length=2000)
    status: str = Field(default="active", pattern="^(planned|active|progressing|resolved|expired|ignored)$")


class ForeshadowMoveRequest(BaseModel):
    direction: str = Field(pattern="^(up|down)$")


class CharacterUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    aliases: list[str] | None = Field(default=None, max_length=20)
    role: str = Field(default="supporting", max_length=64)
    status: str = Field(default="active", pattern="^(active|away|exited)$")
    identity: str = Field(default="", max_length=2000)
    traits: str = Field(default="", max_length=2000)
    motivation: str = Field(default="", max_length=2000)
    goal: str = Field(default="", max_length=2000)
    voice: str = Field(default="", max_length=2000)
    current_state: str = Field(default="", max_length=4000)
    public_image: str = Field(default="", max_length=2000)
    first_appearance_chapter: int = Field(default=0, ge=0)


class CharacterMemoryEventCreateRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=32)
    memory_key: str = Field(default="", max_length=160)
    value: str = Field(min_length=1, max_length=4000)
    valid_from_source_segment: int = Field(default=0, ge=0)
    valid_to_source_segment: int | None = Field(default=None, ge=0)
    quote: str = Field(default="", max_length=10000)
    evidence_status: str = Field(default="insufficient_evidence", pattern="^(verified|insufficient_evidence|rejected|manually_confirmed)$")
    source: str = Field(default="manual", max_length=32)
    review_status: str = Field(default="pending", pattern="^(pending|accepted|ignored)$")
    confidence: float | None = Field(default=None, ge=0, le=1)
    knowledge_scope: str = Field(default="objective_canon", max_length=32)
    evidence_level: str = Field(default="author_input", max_length=32)
    source_chapter_id: str | None = Field(default=None, max_length=32)
    related_character_id: str | None = Field(default=None, max_length=32)


class CharacterMergeRequest(BaseModel):
    target_character_id: str = Field(min_length=1, max_length=32)
    source_character_ids: list[str] = Field(min_length=1, max_length=50)


class ScriptDialogueTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=2000)


class ScriptDialogueRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    source_segment_order: int = Field(default=0, ge=0)
    history: list[ScriptDialogueTurn] = Field(default_factory=list, max_length=10)


class ExperienceCreateRequest(BaseModel):
    start_source_segment: int = Field(ge=1)
    end_source_segment: int = Field(ge=1)
    title: str = Field(default="", max_length=200)


class ExperienceSessionCreateRequest(BaseModel):
    character_id: str | None = Field(default=None, max_length=32)
    character_name: str | None = Field(default=None, max_length=120)
    role_mode: str = Field(default="original", pattern="^(original|replacement)$")
    perspective: str = Field(default="third", pattern="^(first|third)$")


class ExperienceTurnRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class RelationshipUpdateRequest(BaseModel):
    from_character_id: str
    to_character_id: str
    relation_type: str = Field(default="", max_length=64)
    sentiment: str = Field(default="neutral", max_length=32)
    current_state: str = Field(default="", max_length=2000)
    started_chapter: int = Field(default=0, ge=0)
    changed_chapter: int = Field(default=0, ge=0)


class DeslopRequest(BaseModel):
    draft_body: str = Field(default="", max_length=50000)


class ReviewRequest(BaseModel):
    platform: str = Field(default="", pattern=r"^(番茄|起点|知乎|)$")


class ProposalDecisionRequest(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
