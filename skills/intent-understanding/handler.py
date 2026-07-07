from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

from app.llm.qwen import QwenClient
from app.runtime.skill_types import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)


def _load_script_module(script_name: str):
    script_path = Path(__file__).resolve().parent / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(script_name.replace(".py", ""), script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载脚本: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IntentUnderstandingSkill(BaseSkill):
    async def run(self, context: SkillContext, **deps: Any) -> SkillResult:
        llm: QwenClient = deps["llm"]
        logger.info(
            "意图理解开始 trace_id=%s input_len=%d",
            context.trace_id,
            len(context.user_input),
        )

        parsed = await llm.chat(
            system_prompt=self.load_resource("system"),
            user_prompt=context.user_input,
            trace_id=context.trace_id,
        )
        if not isinstance(parsed, dict):
            return SkillResult(
                skill_id=self.meta.skill_id,
                phase=self.meta.phase,
                success=False,
                errors=["意图理解返回非 JSON 结构"],
            )

        spatial_module = _load_script_module("build_spatial_objects.py")
        ticket = {
            "diagnosis_ticket": parsed,
            "spatial_objects": spatial_module.build_spatial_objects(parsed),
        }
        context.task.update(ticket)
        logger.info(
            "意图理解完成 trace_id=%s intersection=%s problem=%s",
            context.trace_id,
            parsed.get("intersection_name"),
            parsed.get("problem_type"),
        )
        return SkillResult(
            skill_id=self.meta.skill_id,
            phase=self.meta.phase,
            success=True,
            output=ticket,
        )
