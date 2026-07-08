from __future__ import annotations

import json
from typing import Any, AsyncIterator, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, model_validator

from app.api.response_builder import build_public_run_response, build_public_skill_catalog
from app.config import Settings, get_settings
from app.runtime.pipeline_validation import PipelineValidationError, skills_from_restart
from app.services.agent_service import AgentService, validate_pipeline_request
from app.services.cases_catalog_service import CasesCatalogService
from app.services.case_library import CaseLibraryService
from app.services.feedback_service import PlanFeedbackService
from app.services.intersection_load_service import IntersectionLoadService
from app.services.skill_solidification_service import SkillSolidificationService

router = APIRouter(prefix="/api/v1")


class AgentRunRequest(BaseModel):
    user_input: str = Field(default="", description="自然语言问题描述；续跑时可留空")
    trace_id: str | None = Field(None, description="可选 trace_id，便于日志追踪")
    task: dict[str, Any] | None = Field(None, description="可选预置任务上下文")
    skill_ids: list[str] | None = Field(
        None,
        description="可选：仅执行默认流水线的有序子序列",
    )
    stop_after: str | None = Field(
        None,
        description="可选：执行至该 skill 后停止（含）",
    )

    @model_validator(mode="after")
    def validate_input_or_resume(self) -> "AgentRunRequest":
        has_resume = bool(self.task and self.task.get("artifacts"))
        if not self.user_input.strip() and not has_resume:
            raise ValueError("user_input 不能为空，除非 task.artifacts 用于续跑")
        return self


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


class PlanRegenerateRequest(BaseModel):
    trace_id: str = Field(..., min_length=1)
    user_input: str = Field(..., min_length=1, description="修改意见或再生成指令")
    task: dict[str, Any] = Field(..., description="含 artifacts 的续跑上下文")
    restart_from: str = Field(
        "plan_generation",
        description="从哪个 skill 起重跑：cause_analysis | strategy_generation | plan_generation",
    )


class SkillSolidifyRequest(BaseModel):
    trace_id: str = Field(..., min_length=1)
    plan_id: str = Field(..., min_length=1)
    diagnosis_ticket: dict[str, Any] | None = Field(
        None,
        description="本轮已采纳的诊断工单快照",
    )
    plan_snapshot: Any | None = Field(
        None,
        description="本轮推荐方案快照（plan 或 plan.recommended）",
    )
    strategy: dict[str, Any] | None = Field(
        None,
        description="本轮策略生成结果（strategy 或 strategy.strategy）",
    )
    artifacts_summary: Any | None = Field(
        None,
        description="可选：流水线 artifacts 摘要，用于补充规则/问题编码标签",
    )


class IntersectionLoadRequest(BaseModel):
    inter_id: str | None = Field(None, description="路口 ID")
    intersection_name: str | None = Field(None, description="路口名称")
    time_range: str | None = Field(None, description="如 18:10-18:30")
    day_of_week: int | None = Field(None, description="星期，默认由时段推断")
    time_hhmm: str | None = Field(None, description="如 18:10")
    direction: str = Field("东向西", description="目标方向")
    movement: str = Field("直行", description="目标转向")

    @model_validator(mode="after")
    def validate_intersection(self) -> "IntersectionLoadRequest":
        if not self.inter_id and not self.intersection_name:
            raise ValueError("缺少 inter_id 或 intersection_name")
        return self


def get_agent_service(settings: Settings = Depends(get_settings)) -> AgentService:
    return AgentService(settings)


def get_feedback_service(settings: Settings = Depends(get_settings)) -> PlanFeedbackService:
    return PlanFeedbackService(settings.feedback_log_abs_path)


def get_intersection_load_service(settings: Settings = Depends(get_settings)) -> IntersectionLoadService:
    return IntersectionLoadService(settings)


def get_cases_catalog_service(settings: Settings = Depends(get_settings)) -> CasesCatalogService:
    return CasesCatalogService(
        CaseLibraryService(settings.case_library_abs_path),
        PlanFeedbackService(settings.feedback_log_abs_path),
    )


def get_skill_solidification_service(
    settings: Settings = Depends(get_settings),
) -> SkillSolidificationService:
    return SkillSolidificationService(
        settings.skills_output_abs_path,
        pg_schema=settings.pg_schema,
        pg_channel_table=settings.pg_channel_table,
        pg_dim_inter_table=settings.pg_dim_inter_table,
    )


@router.get("/health")
async def health(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {
        "status": "ok",
        "llm_mock": settings.llm_mock,
        "model": settings.qwen_model,
        "pg_configured": bool(settings.pg_dsn),
    }


@router.get("/agent/skills")
async def list_skills(agent: AgentService = Depends(get_agent_service)) -> dict[str, Any]:
    return {"skills": build_public_skill_catalog(agent.list_skills())}


@router.post("/agent/run")
async def run_agent(
    request: AgentRunRequest,
    agent: AgentService = Depends(get_agent_service),
) -> dict[str, Any]:
    try:
        validate_pipeline_request(request.skill_ids, request.stop_after)
    except PipelineValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = await agent.run(
        request.user_input,
        trace_id=request.trace_id,
        task=request.task,
        skill_ids=request.skill_ids,
        stop_after=request.stop_after,
    )
    return build_public_run_response(result)


def _sse_frame(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/agent/run/stream")
async def run_agent_stream(
    request: AgentRunRequest,
    agent: AgentService = Depends(get_agent_service),
) -> StreamingResponse:
    """流式执行智能体：逐 phase 以 SSE 推送，前端边算边渲染。

    非法请求在进入流之前以 422 返回；进入流之后的异常转为 error 事件。
    """
    try:
        validate_pipeline_request(request.skill_ids, request.stop_after)
    except PipelineValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    async def event_source() -> AsyncIterator[str]:
        try:
            async for ev in agent.run_stream(
                request.user_input,
                trace_id=request.trace_id,
                task=request.task,
                skill_ids=request.skill_ids,
                stop_after=request.stop_after,
            ):
                yield _sse_frame(ev["event"], ev["data"])
        except Exception as exc:  # noqa: BLE001 - 流内异常转 error 事件而非中断连接
            yield _sse_frame("error", {"phase": None, "errors": [str(exc)]})

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/agent/plan/regenerate")
async def regenerate_plan(
    request: PlanRegenerateRequest,
    agent: AgentService = Depends(get_agent_service),
) -> dict[str, Any]:
    try:
        skills_from_restart(request.restart_from)
    except PipelineValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = await agent.regenerate(
        trace_id=request.trace_id,
        user_input=request.user_input,
        task=request.task,
        restart_from=request.restart_from,
    )
    return build_public_run_response(result)


@router.get("/agent/cases")
async def list_cases(
    problem_type: str | None = Query(None),
    inter_id: str | None = Query(None),
    category: str | None = Query(None, description="textbook | recommended | risk"),
    limit: int = Query(20, ge=1, le=100),
    catalog: CasesCatalogService = Depends(get_cases_catalog_service),
) -> dict[str, Any]:
    return catalog.list_cases(
        problem_type=problem_type,
        inter_id=inter_id,
        category=category,
        limit=limit,
    )


@router.post("/intersection/load")
async def load_intersection(
    request: IntersectionLoadRequest,
    loader: IntersectionLoadService = Depends(get_intersection_load_service),
) -> dict[str, Any]:
    return loader.load(
        inter_id=request.inter_id,
        intersection_name=request.intersection_name,
        time_range=request.time_range,
        day_of_week=request.day_of_week,
        time_hhmm=request.time_hhmm,
        direction=request.direction,
        movement=request.movement,
    )


@router.post("/intersection/load/stream")
async def load_intersection_stream(
    request: IntersectionLoadRequest,
    loader: IntersectionLoadService = Depends(get_intersection_load_service),
) -> StreamingResponse:
    generator = loader.iter_load_events(
        inter_id=request.inter_id,
        intersection_name=request.intersection_name,
        time_range=request.time_range,
        day_of_week=request.day_of_week,
        time_hhmm=request.time_hhmm,
        direction=request.direction,
        movement=request.movement,
    )
    return StreamingResponse(generator, media_type="text/event-stream")


@router.post("/agent/skill/solidify")
async def solidify_skill(
    request: SkillSolidifyRequest,
    service: SkillSolidificationService = Depends(get_skill_solidification_service),
) -> dict[str, Any]:
    return service.solidify(
        trace_id=request.trace_id,
        plan_id=request.plan_id,
        diagnosis_ticket=request.diagnosis_ticket,
        plan_snapshot=request.plan_snapshot,
        strategy=request.strategy,
        artifacts_summary=request.artifacts_summary,
    )


@router.get("/agent/skills/solidified")
async def list_solidified_skills(
    service: SkillSolidificationService = Depends(get_skill_solidification_service),
) -> dict[str, Any]:
    """列出已固化的技能包（读取 data/skills/*/skill.meta.json）。

    注意：`GET /agent/skills` 已用于列出流水线技能，故固化技能列表使用
    `/agent/skills/solidified` 路径以避免冲突。
    """
    return {"skills": service.list_skills()}


@router.get("/agent/skills/{skill_id}/download")
async def download_skill(
    skill_id: str,
    service: SkillSolidificationService = Depends(get_skill_solidification_service),
) -> Response:
    payload = service.zip_skill(skill_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="技能包不存在")
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{skill_id}.zip"'},
    )


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
