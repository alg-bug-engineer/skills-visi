"""Domain models and enums."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class SessionState(str, enum.Enum):
    """Session lifecycle states."""

    IDLE = "idle"
    NLU_INCOMPLETE = "nlu_incomplete"
    INTERSECTION_AMBIGUOUS = "intersection_ambiguous"
    CORRIDOR_NLU_INCOMPLETE = "corridor_nlu_incomplete"
    CORRIDOR_SCANNING = "corridor_scanning"
    AWAITING_CORRIDOR_PICK = "awaiting_corridor_pick"
    PROCESSING = "processing"
    AWAITING_CONFIRM = "awaiting_confirm"
    DONE = "done"


class ReplyType(str, enum.Enum):
    """User-visible reply categories."""

    TEXT = "text"
    FOLLOW_UP = "follow_up"
    DIAGNOSIS = "diagnosis"
    SKILL_CREATED = "skill_created"
    SKILL_UPDATED = "skill_updated"
    ERROR = "error"
    CORRIDOR_SCAN = "corridor_scan"


class TimePeriod(BaseModel):
    """Normalized time window from NLU."""

    start: str
    end: str
    label: str


class CorridorScanNlu(BaseModel):
    corridor: str | None = None
    time_period: TimePeriod | None = None
    problem_type: str = "congestion"


class NluResult(BaseModel):
    """Structured NLU output."""

    intersection: str | None = None
    time_period: TimePeriod | None = None
    problem_type: str | None = None
    problem_types: list[str] = Field(default_factory=lambda: ["congestion"])
    directions: list[str] = Field(default_factory=list)
    user_suggestion: str | None = None


class MessageRecord(BaseModel):
    """Chat message in session history."""

    role: str
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DiagnosisResult(BaseModel):
    """Rule engine output."""

    diagnosed: bool = False
    matched_rules: list[dict[str, Any]] = Field(default_factory=list)
    reason_code: str | None = None
    control_ceiling: str | None = None
    metrics_snapshot: dict[str, Any] = Field(default_factory=dict)


class SuggestionReference(BaseModel):
    """治理建议的依据来源（可溯源到案例库）。"""

    type: str  # "industry" | "intersection"
    id: str  # 跳转锚点，如 industry:school_zone / intersection:inter_001
    title: str
    summary: str = ""
    scenario_id: str | None = None


class SuggestionResult(BaseModel):
    """Governance suggestion."""

    delta_seconds: int
    direction: str
    narrative: str
    confidence: float
    rule_id: str
    action_type: str = "green_light_adjustment"
    action_plan: dict[str, Any] | None = None
    references: list[SuggestionReference] = Field(default_factory=list)


class Session(BaseModel):
    """In-memory session aggregate."""

    session_id: str = Field(default_factory=lambda: str(uuid4()))
    state: SessionState = SessionState.IDLE
    messages: list[MessageRecord] = Field(default_factory=list)
    nlu: NluResult | None = None
    corridor_scan_nlu: CorridorScanNlu | None = None
    raw_user_context: str = ""
    inter_id: str | None = None
    resolved_intersection: str | None = None
    resolution_source: str | None = None
    intersection_candidates: list[str] = Field(default_factory=list)
    data_payload: dict[str, Any] = Field(default_factory=dict)
    diagnosis: DiagnosisResult | None = None
    suggestion: SuggestionResult | None = None
    matched_skill_id: str | None = None
    skill_reuse_mode: bool = False
    pending_follow_up_field: str | None = None
    pending_skill_action: str | None = None  # "create" | "update"
    pending_suggestion_action: str | None = None  # "generate"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        """Update last modified timestamp."""
        self.updated_at = datetime.now(timezone.utc)

    def user_messages_text(self) -> str:
        """Concatenate all user messages for NLU context."""
        return "\n".join(m.content for m in self.messages if m.role == "user")
