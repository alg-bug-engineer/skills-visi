"""分类型经验复用：按理解步骤从档案注入对应经验并产出高亮标记。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from intersection_agent.models.experience import (
    CognitionEntry,
    DiagnosisEntry,
    SolutionRef,
)
from intersection_agent.stores.intersection_profile_store import IntersectionProfileStore

Step = Literal["identify", "attribution", "solution"]


class StepReuseContext(BaseModel):
    """单步复用上下文：按步注入的经验先验 + 前端高亮 badge。"""

    step: str
    inter_id: str
    cognition_priors: list[CognitionEntry] = Field(default_factory=list)
    diagnosis_priors: list[DiagnosisEntry] = Field(default_factory=list)
    solution_refs: list[SolutionRef] = Field(default_factory=list)
    reuse_badges: list[str] = Field(default_factory=list)


class ExperienceReuseService:
    """从路口档案按步取经验，识别步注入认知、归因步注入诊断、出方案步注入方案。"""

    def __init__(self, store: IntersectionProfileStore) -> None:
        self._store = store

    def for_step(self, inter_id: str, step: Step) -> StepReuseContext:
        profile = self._store.load(inter_id)
        ctx = StepReuseContext(step=step, inter_id=inter_id)

        if step == "identify":
            ctx.cognition_priors = list(profile.cognition)
            ctx.reuse_badges = [
                f"复用了 {inter_id} 的认知经验：{c.text}" for c in profile.cognition
            ]
        elif step == "attribution":
            ctx.diagnosis_priors = list(profile.diagnosis)
            ctx.reuse_badges = [
                f"复用了 {inter_id} 的诊断经验：{d.cause}" for d in profile.diagnosis
            ]
        elif step == "solution":
            ctx.solution_refs = list(profile.solution_ref)
            ctx.reuse_badges = [
                f"复用了 {inter_id} 的方案经验：{s.quantified or s.qualitative or s.skill_id}"
                for s in profile.solution_ref
            ]
        return ctx
