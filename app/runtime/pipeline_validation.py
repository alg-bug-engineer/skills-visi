"""Validate and resolve skill pipeline execution order."""

from __future__ import annotations

DEFAULT_PIPELINE = [
    "intent_understanding",
    "data_analysis_diagnosis",
    "cause_analysis",
    "strategy_generation",
    "plan_generation",
]


class PipelineValidationError(ValueError):
    """Raised when skill_ids or stop_after are invalid."""


def validate_skill_subsequence(skill_ids: list[str]) -> None:
    if not skill_ids:
        raise PipelineValidationError("skill_ids 不能为空")

    unknown = [sid for sid in skill_ids if sid not in DEFAULT_PIPELINE]
    if unknown:
        raise PipelineValidationError(f"未知 skill_id: {', '.join(unknown)}")

    cursor = 0
    for skill_id in skill_ids:
        while cursor < len(DEFAULT_PIPELINE) and DEFAULT_PIPELINE[cursor] != skill_id:
            cursor += 1
        if cursor >= len(DEFAULT_PIPELINE):
            raise PipelineValidationError(
                f"skill_ids 须为默认流水线的有序子序列，非法项: {skill_id}"
            )
        cursor += 1


def resolve_pipeline(
    *,
    skill_ids: list[str] | None = None,
    stop_after: str | None = None,
) -> list[str]:
    pipeline = list(skill_ids or DEFAULT_PIPELINE)
    if skill_ids:
        validate_skill_subsequence(skill_ids)

    if stop_after:
        if stop_after not in DEFAULT_PIPELINE:
            raise PipelineValidationError(f"未知 stop_after: {stop_after}")
        if stop_after not in pipeline:
            raise PipelineValidationError(f"stop_after={stop_after} 不在本次 skill_ids 范围内")
        stop_index = pipeline.index(stop_after)
        pipeline = pipeline[: stop_index + 1]

    return pipeline


def skills_from_restart(restart_from: str) -> list[str]:
    if restart_from not in DEFAULT_PIPELINE:
        raise PipelineValidationError(f"未知 restart_from: {restart_from}")
    start = DEFAULT_PIPELINE.index(restart_from)
    return DEFAULT_PIPELINE[start:]


def compute_pipeline_complete(task: dict, artifacts: dict[str, object]) -> bool:
    merged = {**(task.get("artifacts") or {}), **artifacts}
    return all(skill_id in merged for skill_id in DEFAULT_PIPELINE)
