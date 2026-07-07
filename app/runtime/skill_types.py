from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SkillMeta:
    skill_id: str
    display_name: str
    phase: str
    version: str = "0.1.0"
    description: str = ""
    enabled: bool = True
    handler_class: str = ""
    script_files: list[str] = field(default_factory=list)
    reference_files: list[str] = field(default_factory=list)
    resource_files: dict[str, str] = field(default_factory=dict)
    execution_steps: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SkillContext:
    trace_id: str
    user_input: str
    task: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillResult:
    skill_id: str
    phase: str
    success: bool
    output: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


class BaseSkill(ABC):
    def __init__(self, meta: SkillMeta, skill_dir: Path, skill_doc: str = "") -> None:
        self.meta = meta
        self.skill_dir = skill_dir
        self.skill_doc = skill_doc

    def load_resource(self, key: str) -> str:
        relative = self.meta.resource_files.get(key)
        if not relative:
            raise KeyError(f"技能 {self.meta.skill_id} 未配置 resource: {key}")
        return (self.skill_dir / relative).read_text(encoding="utf-8")

    def load_reference(self, relative_path: str) -> str:
        return (self.skill_dir / relative_path).read_text(encoding="utf-8")

    @abstractmethod
    async def run(self, context: SkillContext, **deps: Any) -> SkillResult:
        raise NotImplementedError
