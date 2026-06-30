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


class ExperienceCognitionItem(BaseModel):
    """认知经验：问题记录。"""

    inter_id: str
    text: str
    status: str = "manual"
    source: str = "data"
    evidence: dict[str, Any] = Field(default_factory=dict)
    ts: str = ""


class ExperienceDiagnosisItem(BaseModel):
    """诊断经验：成因先验。"""

    inter_id: str
    cause: str
    dimension: str
    scope: str | None = None
    source: str = "data"
    confidence: float = 0.0
    ts: str = ""


class ExperienceSolutionItem(BaseModel):
    """方案经验：量化方案（关联 skill）。"""

    inter_id: str
    skill_id: str
    qualitative: str | None = None
    quantified: str | None = None
    ts: str = ""
    # 由 skill 包富化，便于面板展示
    intersection: str = ""
    time_period_label: str = ""
    solution_measure: str | None = None
    download_url: str | None = None


class ExperienceLibraryResponse(BaseModel):
    """经验库三桶：认知 / 诊断 / 方案。"""

    inter_id: str | None = None
    cognition: list[ExperienceCognitionItem] = Field(default_factory=list)
    diagnosis: list[ExperienceDiagnosisItem] = Field(default_factory=list)
    solution: list[ExperienceSolutionItem] = Field(default_factory=list)


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


class UpstreamFrame(BaseModel):
    """Storyboard 单帧（逐树串讲 + 帧重建底座）。"""

    idx: int
    tree: str
    kind: str
    focus: Any = None
    reveal: list[str] = Field(default_factory=list)
    camera: str | None = None
    narration: str | None = None


class UpstreamTreeNode(BaseModel):
    """溯源树节点（target / upstream / governance）。"""

    id: str | None = None
    inter_id: str | None = None
    name: str | None = None
    lon: float | None = None
    lat: float | None = None
    role: str | None = None
    hop: int | None = None
    decision: str | None = None
    feeding_dir8: int | None = None
    approach_profiles: list[dict[str, Any]] = Field(default_factory=list)


class UpstreamTreeEdge(BaseModel):
    """溯源树有向边（按 link path 绘制，禁止中心飞线）。"""

    id: str
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    path: list[list[float]] = Field(default_factory=list)
    flow_pct: float | None = None
    dominant_turn: int | None = None


class UpstreamTreeView(BaseModel):
    """单棵溯源树（一个进口道）的节点/边视图。"""

    tree_id: str
    approach: str
    nodes: list[UpstreamTreeNode] = Field(default_factory=list)
    edges: list[UpstreamTreeEdge] = Field(default_factory=list)


class UpstreamStoryboard(BaseModel):
    """完整 storyboard：后端一次产出、前端本地播放。"""

    trees: list[UpstreamTreeView] = Field(default_factory=list)
    frames: list[UpstreamFrame] = Field(default_factory=list)


class UpstreamGovernancePoint(BaseModel):
    """可信控治理落点。"""

    tree_id: str
    approach: str
    inter_id: str | None = None
    inter_name: str | None = None
    hop: int | None = None
    feeding_dir8: int | None = None
    decision: str
    approach_profiles: list[dict[str, Any]] = Field(default_factory=list)


class UpstreamTraceResponse(BaseModel):
    """上游治理溯源结果。"""

    trees: list[dict[str, Any]] = Field(default_factory=list)
    governance_points: list[UpstreamGovernancePoint] = Field(default_factory=list)
    storyboard: UpstreamStoryboard = Field(default_factory=UpstreamStoryboard)
