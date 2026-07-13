from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from app.api.response_builder import build_public_snapshot
from app.config import Settings
from app.llm.qwen import QwenClient
from app.logging_setup import get_trace_id, set_trace_id
from app.runtime.executor import SkillExecutor
from app.runtime.pipeline_validation import skills_from_restart
from app.runtime.registry import get_registry
from app.services.case_library import CaseLibraryService
from app.services.experience_library import ExperienceLibraryService
from app.services.experience_service import ExperienceService
from app.services.feedback_service import PlanFeedbackService

logger = logging.getLogger(__name__)


class AgentService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.llm = QwenClient(settings)
        self.case_service = CaseLibraryService(
            settings.case_library_abs_path,
            structured_industry_path=settings.structured_catalog_abs_path / "industry_cases.jsonl",
        )
        self.experience_service = ExperienceService(settings.user_experience_abs_path)
        self.experience_library = ExperienceLibraryService(settings.user_experience_abs_path)
        self.feedback_service = PlanFeedbackService(settings.feedback_log_abs_path)
        self.registry = get_registry()
        self.executor = SkillExecutor(self.registry)

    async def run(
        self,
        user_input: str,
        *,
        trace_id: str | None = None,
        task: dict[str, Any] | None = None,
        skill_ids: list[str] | None = None,
        stop_after: str | None = None,
    ) -> dict[str, Any]:
        existing = get_trace_id()
        if trace_id:
            tid = set_trace_id(trace_id)
        elif existing and existing != "-":
            tid = existing
        else:
            tid = set_trace_id()
        logger.info("智能体任务开始 trace_id=%s", tid)

        result = await self.executor.run_pipeline(
            trace_id=tid,
            user_input=user_input,
            task=task,
            skill_ids=skill_ids,
            stop_after=stop_after,
            llm=self.llm,
            case_service=self.case_service,
            experience_service=self.experience_service,
            experience_library=self.experience_library,
            feedback_service=self.feedback_service,
            settings=self.settings,
        )

        intent_artifact = result.get("artifacts", {}).get("intent_understanding", {})
        if intent_artifact.get("diagnosis_ticket"):
            result["diagnosis_ticket"] = intent_artifact["diagnosis_ticket"]
        elif task and task.get("diagnosis_ticket"):
            result["diagnosis_ticket"] = task["diagnosis_ticket"]

        logger.info(
            "智能体任务结束 trace_id=%s completed=%s pipeline_complete=%s",
            tid,
            result.get("completed"),
            result.get("pipeline_complete"),
        )
        return result

    def _resolve_trace_id(self, trace_id: str | None) -> str:
        existing = get_trace_id()
        if trace_id:
            return set_trace_id(trace_id)
        if existing and existing != "-":
            return existing
        return set_trace_id()

    async def run_stream(
        self,
        user_input: str,
        *,
        trace_id: str | None = None,
        task: dict[str, Any] | None = None,
        skill_ids: list[str] | None = None,
        stop_after: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """流式执行：逐 phase 产出 SSE-ready 事件 {"event","data"}。

        事件类型：phase_start / phase_done(含增量 snapshot) / error / pipeline_complete。
        """
        tid = self._resolve_trace_id(trace_id)
        logger.info("智能体流式任务开始 trace_id=%s", tid)

        async for ev in self.executor.iter_pipeline(
            trace_id=tid,
            user_input=user_input,
            task=task,
            skill_ids=skill_ids,
            stop_after=stop_after,
            llm=self.llm,
            case_service=self.case_service,
            experience_service=self.experience_service,
            experience_library=self.experience_library,
            feedback_service=self.feedback_service,
            settings=self.settings,
        ):
            etype = ev.get("type")
            if etype == "phase_start":
                yield {
                    "event": "phase_start",
                    "data": {k: ev[k] for k in ("skill_id", "phase", "index", "total")},
                }
            elif etype == "phase_done":
                snapshot = build_public_snapshot(
                    trace_id=tid,
                    artifacts=ev.get("artifacts") or {},
                    results=ev.get("results") or [],
                    task=task,
                )
                data = {k: ev[k] for k in ("skill_id", "phase", "index", "total", "success", "duration_ms")}
                data["snapshot"] = snapshot
                yield {"event": "phase_done", "data": data}
                if not ev.get("success"):
                    yield {
                        "event": "error",
                        "data": {
                            "skill_id": ev.get("skill_id"),
                            "phase": ev.get("phase"),
                            "errors": ev.get("errors") or [],
                        },
                    }
            elif etype == "final":
                snapshot = build_public_snapshot(
                    trace_id=tid,
                    artifacts=ev.get("artifacts") or {},
                    results=ev.get("results") or [],
                    task=task,
                    completed=ev.get("completed"),
                    pipeline_complete=ev.get("pipeline_complete", False),
                )
                if ev.get("completed"):
                    yield {"event": "pipeline_complete", "data": {"snapshot": snapshot}}
                logger.info(
                    "智能体流式任务结束 trace_id=%s completed=%s pipeline_complete=%s",
                    tid,
                    ev.get("completed"),
                    ev.get("pipeline_complete"),
                )

    async def regenerate(
        self,
        *,
        trace_id: str,
        user_input: str,
        task: dict[str, Any],
        restart_from: str = "plan_generation",
    ) -> dict[str, Any]:
        skill_ids = skills_from_restart(restart_from)
        merged_task = dict(task)
        merged_task["modification_input"] = user_input
        return await self.run(
            user_input,
            trace_id=trace_id,
            task=merged_task,
            skill_ids=skill_ids,
        )

    def list_skills(self) -> list[dict]:
        return self.registry.list_skills()


def validate_pipeline_request(
    skill_ids: list[str] | None,
    stop_after: str | None,
) -> None:
    from app.runtime.pipeline_validation import resolve_pipeline

    resolve_pipeline(skill_ids=skill_ids, stop_after=stop_after)
