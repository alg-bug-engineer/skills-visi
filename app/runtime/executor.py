from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator

from app.runtime.overflow_completion import derive_completion_status
from app.runtime.overflow_transition_validation import apply_overflow_transition
from app.runtime.pipeline_validation import (
    compute_pipeline_complete,
    resolve_pipeline,
)
from app.runtime.registry import SkillRegistry
from app.runtime.skill_types import SkillContext, SkillResult

logger = logging.getLogger(__name__)


def _run_skill_in_worker(skill: Any, context: SkillContext, deps: dict[str, Any]) -> SkillResult:
    """Run one async skill on a worker thread with its own event loop.

    Skills intentionally combine async LLM calls with legacy synchronous PG,
    DuckDB and optimizer work.  Running those coroutines on the ASGI loop lets
    any synchronous section freeze StreamingResponse flushing (and even the
    health endpoint).  A per-invocation loop keeps that blocking work away from
    the server loop while preserving the existing async skill interface.
    """
    return asyncio.run(skill.run(context, **deps))


def _serialize_results(results: list[SkillResult]) -> list[dict[str, Any]]:
    return [
        {
            "skill_id": r.skill_id,
            "phase": r.phase,
            "success": r.success,
            "output": r.output,
            "errors": r.errors,
            "duration_ms": r.duration_ms,
        }
        for r in results
    ]


class SkillExecutor:
    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    async def iter_pipeline(
        self,
        *,
        trace_id: str,
        user_input: str,
        task: dict[str, Any] | None = None,
        skill_ids: list[str] | None = None,
        stop_after: str | None = None,
        **deps: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """逐 skill 执行并产出事件：

        - ``phase_start``：进入某 skill 前
        - ``phase_done``：某 skill 完成后（含截至当前的 artifacts/results 快照）
        - ``final``：整条（子）流水线结束的聚合结果（与 run_pipeline 返回同构）

        失败即在该 skill 的 ``phase_done`` 标记 success=False 后停止（不再产出后续 phase）。
        """
        task = dict(task or {})
        pipeline = resolve_pipeline(skill_ids=skill_ids, stop_after=stop_after)
        prefilled = dict(task.get("artifacts") or {})
        context = SkillContext(
            trace_id=trace_id,
            user_input=user_input,
            task=task,
            artifacts=dict(prefilled),
        )
        results: list[SkillResult] = []
        total = len(pipeline)
        healthy_stop = False
        diagnosis_prefetch: asyncio.Task[Any] | None = None
        settings = deps.get("settings")
        if (
            "intent_understanding" in pipeline
            and "data_analysis_diagnosis" in pipeline
            and settings is not None
            and getattr(settings, "pg_dsn", None)
        ):
            from app.data.diagnosis_prefetch import run_diagnosis_prefetch

            diagnosis_prefetch = asyncio.create_task(
                asyncio.to_thread(
                    run_diagnosis_prefetch,
                    user_input=user_input,
                    task=task,
                    settings=settings,
                )
            )

        logger.info("开始流式执行流水线 trace_id=%s pipeline=%s", trace_id, pipeline)

        for index, skill_id in enumerate(pipeline):
            skill = self.registry.get(skill_id)
            yield {
                "type": "phase_start",
                "skill_id": skill_id,
                "phase": skill.meta.phase,
                "index": index,
                "total": total,
            }

            # The first phase_done has already been yielded, so frontend render
            # can proceed while we join the speculative read.  Only a strict
            # ticket signature match is allowed to reuse it.
            if skill_id == "data_analysis_diagnosis" and diagnosis_prefetch is not None:
                try:
                    prefetched = await diagnosis_prefetch
                    from app.data.diagnosis_prefetch import apply_diagnosis_prefetch

                    actual_ticket = context.task.get("diagnosis_ticket") or {}
                    reused = apply_diagnosis_prefetch(context.task, actual_ticket, prefetched)
                    logger.info("诊断数据预取完成 trace_id=%s reused=%s", trace_id, reused)
                except Exception as exc:  # noqa: BLE001 - prefetch is optional
                    logger.warning("诊断数据预取失败 trace_id=%s error=%s", trace_id, exc)
                diagnosis_prefetch = None

            start = time.perf_counter()
            logger.info(
                "执行技能开始 trace_id=%s skill_id=%s phase=%s",
                trace_id,
                skill_id,
                skill.meta.phase,
            )
            try:
                # A skill may contain synchronous DB/CPU work around its async
                # LLM calls.  Isolate the whole invocation so the ASGI loop can
                # keep flushing phase_done events while the next phase runs.
                result = await asyncio.to_thread(_run_skill_in_worker, skill, context, deps)
            except Exception as exc:  # noqa: BLE001 - 汇集为失败结果，交由上层转 error 事件
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

            # 需求 35：溢出闭环阶段语义校验（对象/机制/决策/可执行一致性）
            if result.success:
                transition_errors = apply_overflow_transition(
                    context,
                    skill_id=skill_id,
                    result_success=True,
                    output=result.output or {},
                )
                if transition_errors:
                    result.success = False
                    result.errors = list(result.errors or []) + transition_errors
                    logger.warning(
                        "溢出阶段转换校验失败 trace_id=%s skill_id=%s errors=%s",
                        trace_id,
                        skill_id,
                        transition_errors,
                    )

            results.append(result)
            context.artifacts[skill_id] = result.output

            logger.info(
                "执行技能完成 trace_id=%s skill_id=%s success=%s duration_ms=%s",
                trace_id,
                skill_id,
                result.success,
                result.duration_ms,
            )

            merged_so_far = {**prefilled, **context.artifacts}
            yield {
                "type": "phase_done",
                "skill_id": skill_id,
                "phase": result.phase,
                "index": index,
                "total": total,
                "success": result.success,
                "duration_ms": result.duration_ms,
                "errors": result.errors,
                "artifacts": dict(merged_so_far),
                "results": _serialize_results(results),
            }

            if not result.success:
                break

            # 健康分支：诊断确认路口无问题时，正常提前收尾，不再执行成因/策略/方案。
            # 仅在完整流水线（含诊断技能）时生效；regenerate 等子流水线不受影响。
            if (
                skill_id == "data_analysis_diagnosis"
                and result.success
                and isinstance(result.output, dict)
                and result.output.get("healthy") is True
            ):
                healthy_stop = True
                logger.info("诊断判定路口健康，提前收尾 trace_id=%s", trace_id)
                break

        if diagnosis_prefetch is not None and not diagnosis_prefetch.done():
            diagnosis_prefetch.cancel()

        merged_artifacts = {**prefilled, **context.artifacts}
        task["artifacts"] = merged_artifacts
        completed = all(r.success for r in results)
        strategy_art = merged_artifacts.get("strategy_generation") or {}
        plan_art = merged_artifacts.get("plan_generation") or {}
        completion_status = derive_completion_status(
            completed=completed,
            healthy=healthy_stop,
            decision=strategy_art.get("decision") if isinstance(strategy_art, dict) else None,
            plan=plan_art if isinstance(plan_art, dict) else None,
        )
        yield {
            "type": "final",
            "trace_id": trace_id,
            "pipeline": pipeline,
            "artifacts": merged_artifacts,
            "results": _serialize_results(results),
            "completed": completed,
            # 健康提前收尾视为完成（无需成因/策略/方案）。
            "pipeline_complete": True
            if healthy_stop
            else compute_pipeline_complete(task, context.artifacts),
            "healthy": healthy_stop,
            "completion_status": completion_status,
        }

    async def run_pipeline(
        self,
        *,
        trace_id: str,
        user_input: str,
        task: dict[str, Any] | None = None,
        skill_ids: list[str] | None = None,
        stop_after: str | None = None,
        **deps: Any,
    ) -> dict[str, Any]:
        """消费 iter_pipeline，返回聚合结果（保持原有非流式行为不变）。"""
        final: dict[str, Any] = {}
        async for event in self.iter_pipeline(
            trace_id=trace_id,
            user_input=user_input,
            task=task,
            skill_ids=skill_ids,
            stop_after=stop_after,
            **deps,
        ):
            if event.get("type") == "final":
                final = {k: v for k, v in event.items() if k != "type"}
        return final
