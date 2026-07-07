from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.data.intersection_registry import enrich_ticket
from app.llm.qwen import QwenClient
from app.runtime.skill_types import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def _load_script_module(script_name: str):
    script_path = Path(__file__).resolve().parent / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(script_name.replace(".py", ""), script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载脚本: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _preview_topology(inter_id: str | None) -> dict[str, Any]:
    if not inter_id:
        return {}
    path = FIXTURES_ROOT / "overflow_topology.json"
    if not path.exists():
        return {}
    topology = json.loads(path.read_text(encoding="utf-8"))
    if topology.get("target_inter_id") == inter_id:
        return topology
    return {}


class IntentUnderstandingSkill(BaseSkill):
    async def run(self, context: SkillContext, **deps: Any) -> SkillResult:
        settings: Settings = deps.get("settings") or get_settings()
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

        pre_ticket = context.task.get("diagnosis_ticket") or {}
        if pre_ticket.get("inter_id") or pre_ticket.get("intersection_name"):
            merged = {**parsed, **pre_ticket}
        else:
            merged = parsed
        enriched = enrich_ticket(merged, user_input=context.user_input)
        spatial_module = _load_script_module("build_spatial_objects.py")
        scene_module = _load_script_module("build_spatial_scene.py")
        topology_preview = context.task.get("topology") or _preview_topology(enriched.get("inter_id"))

        ticket = {
            "diagnosis_ticket": enriched,
            "spatial_objects": spatial_module.build_spatial_objects(enriched),
            "spatial_scene": scene_module.build_spatial_scene(enriched, topology=topology_preview),
        }
        context.task.update(ticket)
        logger.info(
            "意图理解完成 trace_id=%s intersection=%s inter_id=%s problem=%s",
            context.trace_id,
            enriched.get("intersection_name"),
            enriched.get("inter_id"),
            enriched.get("problem_type"),
        )
        return SkillResult(
            skill_id=self.meta.skill_id,
            phase=self.meta.phase,
            success=True,
            output=ticket,
        )
