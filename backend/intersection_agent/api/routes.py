"""FastAPI route handlers."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from intersection_agent import __version__
from intersection_agent.api.schemas import (
    HealthResponse,
    MessageRequest,
    MessageResponse,
    ReplyPayload,
    SessionCreateResponse,
    SessionDetailResponse,
    SkillLeaderboardResponse,
    SkillResponse,
)
from intersection_agent.api.sse import build_emitter, sse_event_stream
from intersection_agent.config import get_settings
from intersection_agent.logging.helpers import log_event, safe_preview
from intersection_agent.services.orchestrator import Orchestrator
from intersection_agent.services.skill_service import SkillService
from intersection_agent.services.skill_matcher import backfill_tags
from intersection_agent.skills.tag_helpers import read_hit_count, read_last_hit_at
from intersection_agent.stores.session_store import SessionStore

logger = logging.getLogger(__name__)

router = APIRouter()
_sessions = SessionStore()
_orchestrator = Orchestrator()
_skills = SkillService()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Service health check."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        mock_llm=settings.mock_llm,
        mock_db=settings.mock_db,
        version=__version__,
    )


@router.post("/sessions", response_model=SessionCreateResponse)
async def create_session() -> SessionCreateResponse:
    """Create a new conversation session."""
    session = _sessions.create()
    log_event(
        logger,
        logging.INFO,
        "session.created",
        session_id=session.session_id,
        state=session.state.value,
    )
    return SessionCreateResponse(session_id=session.session_id, state=session.state.value)


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(session_id: str) -> SessionDetailResponse:
    """Get session state."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionDetailResponse(
        session_id=session.session_id,
        state=session.state.value,
        message_count=len(session.messages),
        nlu=session.nlu.model_dump() if session.nlu else None,
        meta={
            "inter_id": session.inter_id,
            "resolution_source": session.resolution_source,
            "matched_skill": session.matched_skill_id,
        },
    )


@router.post("/sessions/{session_id}/messages", response_model=MessageResponse)
async def post_message(session_id: str, body: MessageRequest) -> MessageResponse:
    """Send user message and receive assistant reply."""
    session = _sessions.get(session_id)
    if not session:
        log_event(logger, logging.WARNING, "session.not_found", session_id=session_id)
        raise HTTPException(status_code=404, detail="Session not found")

    log_event(
        logger,
        logging.INFO,
        "message.received",
        session_id=session_id,
        state=session.state.value,
        input=safe_preview(body.content),
    )

    try:
        result = await _orchestrator.handle_message(session, body.content)
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "message.failed",
            session_id=session_id,
            error=type(exc).__name__,
            detail=safe_preview(str(exc)),
        )
        raise

    _sessions.save(session)
    log_event(
        logger,
        logging.INFO,
        "message.completed",
        session_id=session_id,
        state=result["state"],
        reply_type=result["reply"]["type"],
        resolution_source=result.get("meta", {}).get("resolution_source"),
        matched_skill=result.get("meta", {}).get("matched_skill"),
    )
    return MessageResponse(
        session_id=result["session_id"],
        state=result["state"],
        reply=ReplyPayload(**result["reply"]),
        nlu=result.get("nlu"),
        diagnosis=result.get("diagnosis"),
        suggestion=result.get("suggestion"),
        meta=result.get("meta", {}),
    )


@router.post("/sessions/{session_id}/messages/stream")
async def post_message_stream(session_id: str, body: MessageRequest) -> StreamingResponse:
    """Send user message and stream execution steps via SSE, then final result."""
    session = _sessions.get(session_id)
    if not session:
        log_event(logger, logging.WARNING, "session.not_found", session_id=session_id)
        raise HTTPException(status_code=404, detail="Session not found")

    log_event(
        logger,
        logging.INFO,
        "message.stream.received",
        session_id=session_id,
        state=session.state.value,
        input=safe_preview(body.content),
    )

    queue: asyncio.Queue[dict | None] = asyncio.Queue()
    emitter = build_emitter(queue)

    async def run_pipeline() -> None:
        try:
            result = await _orchestrator.handle_message(session, body.content, emitter=emitter)
            _sessions.save(session)
            await emitter.emit("complete", "completed", data={"state": result["state"]})
            await emitter.emit_result(result)
            log_event(
                logger,
                logging.INFO,
                "message.stream.completed",
                session_id=session_id,
                state=result["state"],
                reply_type=result["reply"]["type"],
            )
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "message.stream.failed",
                session_id=session_id,
                error=type(exc).__name__,
                detail=safe_preview(str(exc)),
            )
            await emitter.emit_error(f"服务内部错误: {type(exc).__name__}", detail=str(exc))
        finally:
            await queue.put(None)

    asyncio.create_task(run_pipeline())

    return StreamingResponse(
        sse_event_stream(queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/skills", response_model=list[SkillResponse])
async def list_skills(
    intersection: str | None = Query(default=None, description="Filter by intersection name"),
) -> list[SkillResponse]:
    """List persisted intersection skills."""
    records = _skills.list_skills(intersection)
    return [
        SkillResponse(
            skill_id=r.skill_id,
            skill_dir=r.skill_dir,
            intersection=r.intersection,
            problem_type=r.problem_type,
            time_period_label=r.time_period_label,
            rule_ids=r.rule_ids,
            created_at=r.created_at,
        )
        for r in records
    ]


def _leaderboard_item(record) -> SkillLeaderboardResponse:
    tags = backfill_tags(record)
    return SkillLeaderboardResponse(
        skill_id=record.skill_id,
        skill_dir=record.skill_dir,
        intersection=record.intersection,
        inter_id=record.inter_id,
        problem_type=record.problem_type,
        time_period_label=record.time_period_label,
        rule_ids=record.rule_ids,
        created_at=record.created_at,
        updated_at=record.updated_at,
        hit_count=read_hit_count(record.tags),
        last_hit_at=read_last_hit_at(record.tags),
        tags=tags,
        user_constraints=record.user_constraints,
        suggestion_formula=record.suggestion_formula,
        download_url=f"/api/v1/skills/{record.skill_id}/download",
    )


@router.get("/skills/leaderboard", response_model=list[SkillLeaderboardResponse])
async def list_skill_leaderboard(
    sort: str = Query(
        default="hits",
        description="Sort key: hits | created | updated",
        pattern="^(hits|created|updated)$",
    ),
    intersection: str | None = Query(default=None, description="Filter by intersection name"),
) -> list[SkillLeaderboardResponse]:
    """List persisted skills for the leaderboard panel."""
    if sort not in {"hits", "created", "updated"}:
        raise HTTPException(status_code=422, detail="Invalid sort")
    records = _skills.list_leaderboard(sort=sort, intersection=intersection)
    return [_leaderboard_item(r) for r in records]


@router.get("/skills/{skill_id}/download")
async def download_skill_package(skill_id: str) -> Response:
    """Download skill package as zip."""
    try:
        data, filename = _skills.package_zip(skill_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Skill not found") from exc
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
