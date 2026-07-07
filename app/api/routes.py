from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.services.agent_service import AgentService

router = APIRouter(prefix="/api/v1")


class AgentRunRequest(BaseModel):
    user_input: str = Field(..., min_length=1, description="自然语言问题描述")
    trace_id: str | None = Field(None, description="可选 trace_id，便于日志追踪")
    task: dict[str, Any] | None = Field(None, description="可选预置任务上下文")


def get_agent_service(settings: Settings = Depends(get_settings)) -> AgentService:
    return AgentService(settings)


@router.get("/health")
async def health(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {
        "status": "ok",
        "llm_mock": settings.llm_mock,
        "model": settings.qwen_model,
    }


@router.get("/agent/skills")
async def list_skills(agent: AgentService = Depends(get_agent_service)) -> dict[str, Any]:
    return {"skills": agent.list_skills()}


@router.post("/agent/run")
async def run_agent(
    request: AgentRunRequest,
    agent: AgentService = Depends(get_agent_service),
) -> dict[str, Any]:
    return await agent.run(
        request.user_input,
        trace_id=request.trace_id,
        task=request.task,
    )
