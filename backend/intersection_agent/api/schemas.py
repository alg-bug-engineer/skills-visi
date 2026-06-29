"""API request/response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MessageRequest(BaseModel):
    """Incoming user message."""

    content: str = Field(..., min_length=1, max_length=4000)


class ReplyPayload(BaseModel):
    """Assistant reply."""

    type: str
    content: str


class SessionCreateResponse(BaseModel):
    """New session response."""

    session_id: str
    state: str


class MessageResponse(BaseModel):
    """Message handling response."""

    session_id: str
    state: str
    reply: ReplyPayload
    nlu: dict[str, Any] | None = None
    diagnosis: dict[str, Any] | None = None
    suggestion: dict[str, Any] | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class SessionDetailResponse(BaseModel):
    """Session snapshot."""

    session_id: str
    state: str
    message_count: int
    nlu: dict[str, Any] | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class SkillResponse(BaseModel):
    """Skill list item."""

    skill_id: str
    skill_dir: str
    intersection: str
    problem_type: str
    time_period_label: str
    rule_ids: list[str]
    created_at: str


class SkillLeaderboardResponse(BaseModel):
    """Skill leaderboard row with tags and utilization stats."""

    skill_id: str
    skill_dir: str
    intersection: str
    inter_id: str
    problem_type: str
    time_period_label: str
    rule_ids: list[str]
    created_at: str
    updated_at: str | None = None
    hit_count: int = 0
    last_hit_at: str | None = None
    tags: dict[str, Any] = Field(default_factory=dict)
    user_constraints: str | None = None
    suggestion_formula: str = ""
    download_url: str


class HealthResponse(BaseModel):
    """Health check."""

    status: str
    mock_llm: bool
    mock_db: bool
    version: str


class ExecutionStepEvent(BaseModel):
    """Single pipeline step pushed over SSE."""

    event: str = "step"
    step: str
    status: str
    label: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: str
