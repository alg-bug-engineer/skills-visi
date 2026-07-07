from __future__ import annotations

import logging
from typing import Any

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
        self.case_service = CaseLibraryService(settings.case_library_abs_path)
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
