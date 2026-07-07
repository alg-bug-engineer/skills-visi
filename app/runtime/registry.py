from __future__ import annotations

import logging
from pathlib import Path

from app.config import PROJECT_ROOT
from app.runtime.skill_loader import discover_skill_dirs, load_skill_from_dir
from app.runtime.skill_types import BaseSkill

logger = logging.getLogger(__name__)

SKILLS_ROOT = PROJECT_ROOT / "skills"


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        if not skill.meta.enabled:
            logger.info("技能已禁用，跳过注册: %s", skill.meta.skill_id)
            return
        self._skills[skill.meta.skill_id] = skill
        logger.info(
            "注册技能 skill_id=%s phase=%s version=%s path=%s",
            skill.meta.skill_id,
            skill.meta.phase,
            skill.meta.version,
            skill.skill_dir.name,
        )

    def get(self, skill_id: str) -> BaseSkill:
        if skill_id not in self._skills:
            raise KeyError(f"技能未注册: {skill_id}")
        return self._skills[skill_id]

    def list_skills(self) -> list[dict]:
        return [
            {
                "skill_id": s.meta.skill_id,
                "display_name": s.meta.display_name,
                "phase": s.meta.phase,
                "version": s.meta.version,
                "description": s.meta.description,
                "enabled": s.meta.enabled,
                "skill_dir": s.skill_dir.name,
                "script_files": s.meta.script_files,
                "reference_files": s.meta.reference_files,
                "resource_files": s.meta.resource_files,
            }
            for s in self._skills.values()
        ]

    def discover_and_register(self, skills_root: Path | None = None) -> None:
        root = skills_root or SKILLS_ROOT
        for skill_dir in discover_skill_dirs(root):
            try:
                skill = load_skill_from_dir(skill_dir)
                self.register(skill)
            except Exception as exc:
                logger.exception("技能加载失败 path=%s error=%s", skill_dir, exc)
                raise
        logger.info("技能发现完成，共注册 %d 个技能", len(self._skills))


_registry: SkillRegistry | None = None


def get_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
        _registry.discover_and_register()
    return _registry


def reset_registry() -> None:
    """测试用：重置全局注册表。"""
    global _registry
    _registry = None
