from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.response_builder import build_public_run_response, build_public_skill_catalog
from app.config import Settings, get_settings
from app.services.agent_service import AgentService
from app.services.feedback_service import PlanFeedbackService

router = APIRouter(prefix="/api/v1")


class AgentRunRequest(BaseModel):
    user_input: str = Field(..., min_length=1, description="自然语言问题描述")
    trace_id: str | None = Field(None, description="可选 trace_id，便于日志追踪")
    task: dict[str, Any] | None = Field(None, description="可选预置任务上下文")


class PlanDecisionRequest(BaseModel):
    trace_id: str = Field(..., min_length=1)
    plan_id: str = Field(..., min_length=1)
    decision: Literal["accept", "reject"]
    rejection_reason: str | None = Field(
        None,
        description="拒绝方案时的可选理由",
    )
    plan_snapshot: dict[str, Any] | None = Field(
        None,
        description="可选：前端当前展示的推荐方案快照",
    )
    diagnosis_ticket: dict[str, Any] | None = Field(
        None,
        description="可选：关联诊断工单，便于反馈沉淀",
    )
    artifacts_summary: dict[str, Any] | None = Field(
        None,
        description="可选：流水线 artifacts 摘要，用于指纹与标签沉淀",
    )


def get_agent_service(settings: Settings = Depends(get_settings)) -> AgentService:
    return AgentService(settings)


def get_feedback_service(settings: Settings = Depends(get_settings)) -> PlanFeedbackService:
    return PlanFeedbackService(settings.feedback_log_abs_path)


@router.get("/health")
async def health(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {
        "status": "ok",
        "llm_mock": settings.llm_mock,
        "model": settings.qwen_model,
    }


@router.get("/agent/skills")
async def list_skills(agent: AgentService = Depends(get_agent_service)) -> dict[str, Any]:
    return {"skills": build_public_skill_catalog(agent.list_skills())}


@router.post("/agent/run")
async def run_agent(
    request: AgentRunRequest,
    agent: AgentService = Depends(get_agent_service),
) -> dict[str, Any]:
    result = await agent.run(
        request.user_input,
        trace_id=request.trace_id,
        task=request.task,
    )
    return build_public_run_response(result)


@router.post("/agent/plan/decision")
async def submit_plan_decision(
    request: PlanDecisionRequest,
    feedback: PlanFeedbackService = Depends(get_feedback_service),
) -> dict[str, Any]:
    return feedback.record_decision(
        trace_id=request.trace_id,
        plan_id=request.plan_id,
        decision=request.decision,
        rejection_reason=request.rejection_reason,
        plan_snapshot=request.plan_snapshot,
        diagnosis_ticket=request.diagnosis_ticket,
        artifacts_summary=request.artifacts_summary,
    )
