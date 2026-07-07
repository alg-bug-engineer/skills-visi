from __future__ import annotations

import logging
import time
from typing import Any

from app.runtime.registry import SkillRegistry
from app.runtime.skill_types import SkillContext, SkillResult

logger = logging.getLogger(__name__)

DEFAULT_PIPELINE = [
    "intent_understanding",
    "data_analysis_diagnosis",
    "cause_analysis",
    "strategy_generation",
    "plan_generation",
]


class SkillExecutor:
    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    async def run_pipeline(
        self,
        *,
        trace_id: str,
        user_input: str,
        task: dict[str, Any] | None = None,
        skill_ids: list[str] | None = None,
        **deps: Any,
    ) -> dict[str, Any]:
        pipeline = skill_ids or DEFAULT_PIPELINE
        context = SkillContext(
            trace_id=trace_id,
            user_input=user_input,
            task=task or {},
        )
        results: list[SkillResult] = []

        logger.info("开始执行流水线 trace_id=%s pipeline=%s", trace_id, pipeline)

        for skill_id in pipeline:
            skill = self.registry.get(skill_id)
            start = time.perf_counter()
            logger.info(
                "执行技能开始 trace_id=%s skill_id=%s phase=%s",
                trace_id,
                skill_id,
                skill.meta.phase,
            )
            try:
                result = await skill.run(context, **deps)
            except Exception as exc:
                logger.exception(
                    "技能执行异常 trace_id=%s skill_id=%s error=%s",
                    trace_id,
                    skill_id,
                    exc,
                )
                result = SkillResult(
                    skill_id=skill_id,
                    phase=skill.meta.phase,
                    success=False,
                    errors=[str(exc)],
                )

            result.duration_ms = round((time.perf_counter() - start) * 1000, 2)
            results.append(result)
            context.artifacts[skill_id] = result.output

            logger.info(
                "执行技能完成 trace_id=%s skill_id=%s success=%s duration_ms=%s",
                trace_id,
                skill_id,
                result.success,
                result.duration_ms,
            )

            if not result.success:
                break

        return {
            "trace_id": trace_id,
            "pipeline": pipeline,
            "artifacts": context.artifacts,
            "results": [
                {
                    "skill_id": r.skill_id,
                    "phase": r.phase,
                    "success": r.success,
                    "output": r.output,
                    "errors": r.errors,
                    "duration_ms": r.duration_ms,
                }
                for r in results
            ],
            "completed": all(r.success for r in results),
        }
