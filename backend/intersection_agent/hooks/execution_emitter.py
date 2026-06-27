"""Emit structured execution-step events during agent pipeline runs."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

StepCallback = Callable[[dict[str, Any]], Awaitable[None]]

STEP_LABELS: dict[str, str] = {
    "orchestrator.start": "接收用户消息",
    "nlu": "自然语言理解 (NLU)",
    "intersection": "路口名称匹配",
    "skill_match": "Skill 快路径检索",
    "intersection_cognition": "路口认知（渠化/车道）",
    "map_action": "地图动作",
    "data_fetch": "查询路口运行数据",
    "rule_engine": "业务规则诊断",
    "suggestion": "生成治理建议",
    "confirm_intent": "识别确认意图",
    "skill_create": "固化路口 Skill",
    "complete": "处理完成",
}


class ExecutionEmitter:
    """Push pipeline step events to an optional async callback (e.g. SSE queue)."""

    def __init__(self, callback: StepCallback | None = None) -> None:
        self._callback = callback

    async def emit(
        self,
        step: str,
        status: str,
        *,
        label: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Emit a single execution step event."""
        if not self._callback:
            return
        payload: dict[str, Any] = {
            "event": "step",
            "step": step,
            "status": status,
            "label": label or STEP_LABELS.get(step, step),
            "data": data or {},
            "timestamp": datetime.now(UTC).isoformat(),
        }
        try:
            await self._callback(payload)
        except Exception:
            logger.exception("execution_emitter.callback_failed step=%s", step)

    async def emit_result(self, result: dict[str, Any]) -> None:
        """Emit the final message response."""
        if not self._callback:
            return
        payload: dict[str, Any] = {
            "event": "result",
            "data": result,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        try:
            await self._callback(payload)
        except Exception:
            logger.exception("execution_emitter.result_failed")

    async def emit_error(self, message: str, *, detail: str | None = None) -> None:
        """Emit a terminal error event."""
        if not self._callback:
            return
        payload: dict[str, Any] = {
            "event": "error",
            "message": message,
            "detail": detail,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        try:
            await self._callback(payload)
        except Exception:
            logger.exception("execution_emitter.error_failed")

    async def emit_skill_build(
        self,
        event_type: str,
        stage: str,
        **payload: Any,
    ) -> None:
        """Emit a skill-build visualization event."""
        if not self._callback:
            return
        body: dict[str, Any] = {
            "event": "skill_build",
            "type": event_type,
            "stage": stage,
            "timestamp": datetime.now(UTC).isoformat(),
            "payload": payload,
        }
        try:
            await self._callback(body)
        except Exception:
            logger.exception("execution_emitter.skill_build_failed type=%s", event_type)

    async def emit_skill_absorption(
        self,
        event_type: str,
        stage: str,
        **payload: Any,
    ) -> None:
        """Emit an experience-absorption visualization event."""
        if not self._callback:
            return
        body: dict[str, Any] = {
            "event": "skill_absorption",
            "type": event_type,
            "stage": stage,
            "timestamp": datetime.now(UTC).isoformat(),
            "payload": payload,
        }
        try:
            await self._callback(body)
        except Exception:
            logger.exception("execution_emitter.skill_absorption_failed type=%s", event_type)
