from __future__ import annotations

import logging
from typing import Any

from app.config import Settings
from app.llm.qwen import QwenClient
from app.logging_setup import get_trace_id, set_trace_id
from app.runtime.executor import SkillExecutor
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
            llm=self.llm,
            case_service=self.case_service,
            experience_service=self.experience_service,
            experience_library=self.experience_library,
            feedback_service=self.feedback_service,
            settings=self.settings,
        )

        result["diagnosis_ticket"] = result.get("artifacts", {}).get(
            "intent_understanding", {}
        ).get("diagnosis_ticket")

        logger.info(
            "智能体任务结束 trace_id=%s completed=%s",
            tid,
            result.get("completed"),
        )
        return result

    def list_skills(self) -> list[dict]:
        return self.registry.list_skills()
