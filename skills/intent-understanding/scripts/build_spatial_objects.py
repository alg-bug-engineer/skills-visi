from __future__ import annotations

from typing import Any

from app.runtime.skill_types import BaseSkill, SkillContext, SkillResult


def build_spatial_objects(ticket: dict[str, Any]) -> dict[str, Any]:
    direction = ticket.get("direction", "")
    return {
        "target_intersection": ticket.get("intersection_name"),
        "target_direction": direction,
        "target_movement": ticket.get("movement", "直行"),
        "upstream_scope": f"{direction}来车来源路段与相邻路口",
        "downstream_scope": f"{direction}出口路段与下游信控节点",
        "main_path": "上游来车 → 目标路口 → 下游承接节点",
    }
