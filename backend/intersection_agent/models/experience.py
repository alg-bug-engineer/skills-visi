"""三级经验档案模型：认知 / 诊断 / 方案。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


CognitionStatus = Literal["verified", "data_doubt", "manual"]


class CognitionStructured(BaseModel):
    """认知经验结构化拆分（LLM 理解用户原话）。"""

    time_period: str = ""
    directions: list[str] = Field(default_factory=list)
    movement: str = ""
    phenomenon: str = ""
    summary: str = ""


class CognitionEntry(BaseModel):
    """认知经验：问题记录（数据可验证 / 人坚持但数据不显著 / 人工录入）。"""

    text: str
    status: CognitionStatus = "manual"
    source: str = "data"
    evidence: dict[str, Any] = Field(default_factory=dict)
    intersection: str = ""
    tags: list[str] = Field(default_factory=list)
    structured: CognitionStructured = Field(default_factory=CognitionStructured)
    ts: str = Field(default_factory=_now)


class DiagnosisEntry(BaseModel):
    """诊断经验：原因解释先验。"""

    cause: str
    dimension: str
    scope: str | None = None
    source: str = "data"
    confidence: float = 0.0
    ts: str = Field(default_factory=_now)


class SolutionRef(BaseModel):
    """方案经验指针（实体固化在 skill 包）。"""

    skill_id: str
    qualitative: str | None = None
    quantified: str | None = None
    ts: str = Field(default_factory=_now)


class IntersectionProfile(BaseModel):
    """单路口认知档案快照。"""

    inter_id: str
    intersection: str = ""
    cognition: list[CognitionEntry] = Field(default_factory=list)
    diagnosis: list[DiagnosisEntry] = Field(default_factory=list)
    solution_ref: list[SolutionRef] = Field(default_factory=list)
