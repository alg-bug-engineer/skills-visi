from __future__ import annotations

import importlib.util
import logging
import re
from pathlib import Path
from typing import Type

import yaml

from app.runtime.skill_types import BaseSkill, SkillMeta

logger = logging.getLogger(__name__)

SKILL_MANIFEST = "SKILL.md"
HANDLER_MODULE = "handler.py"
REQUIRED_DIRS = ("scripts", "references", "resources")


def _parse_skill_md(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not match:
        raise ValueError(f"SKILL.md 缺少 YAML frontmatter: {path}")
    frontmatter = yaml.safe_load(match.group(1)) or {}
    body = match.group(2).strip()
    return frontmatter, body


def _meta_from_frontmatter(raw: dict) -> SkillMeta:
    metadata = raw.get("metadata") or raw
    resource_files = metadata.get("resource_files") or {}
    if not resource_files and metadata.get("prompt_files"):
        resource_files = metadata["prompt_files"]

    return SkillMeta(
        skill_id=metadata["skill_id"],
        display_name=metadata.get("display_name", metadata["skill_id"]),
        phase=metadata["phase"],
        version=metadata.get("version", "0.1.0"),
        description=raw.get("description", metadata.get("description", "")),
        enabled=metadata.get("enabled", True),
        handler_class=metadata.get("handler_class", ""),
        script_files=metadata.get("script_files", []),
        reference_files=metadata.get("reference_files", []),
        resource_files=resource_files,
        execution_steps=metadata.get("execution_steps", []),
    )


def validate_skill_layout(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    skill_md = skill_dir / SKILL_MANIFEST
    if not skill_md.is_file():
        errors.append(f"缺少 {SKILL_MANIFEST}")

    for dirname in REQUIRED_DIRS:
        subdir = skill_dir / dirname
        if not subdir.is_dir():
            errors.append(f"缺少 {dirname}/ 目录")
            continue
        if not any(subdir.iterdir()):
            errors.append(f"{dirname}/ 目录为空")

    if not (skill_dir / HANDLER_MODULE).is_file():
        errors.append("缺少 handler.py")

    if errors:
        return errors

    _, body = _parse_skill_md(skill_md)
    if not body:
        errors.append(f"{SKILL_MANIFEST} 正文为空，技能不能仅包含 frontmatter")

    return errors


def _load_handler_class(skill_dir: Path, handler_class_name: str) -> Type[BaseSkill]:
    handler_path = skill_dir / HANDLER_MODULE
    module_name = f"skill_handler_{skill_dir.name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, handler_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载技能 handler: {handler_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if not isinstance(attr, type) or not issubclass(attr, BaseSkill) or attr is BaseSkill:
            continue
        if handler_class_name and attr.__name__ != handler_class_name:
            continue
        return attr

    raise RuntimeError(f"技能目录未找到 Handler 类 {handler_class_name}: {skill_dir}")


def load_skill_from_dir(skill_dir: Path) -> BaseSkill:
    layout_errors = validate_skill_layout(skill_dir)
    if layout_errors:
        raise ValueError(f"技能目录结构不合规 {skill_dir}: {'; '.join(layout_errors)}")

    manifest_path = skill_dir / SKILL_MANIFEST
    frontmatter, body = _parse_skill_md(manifest_path)
    meta = _meta_from_frontmatter(frontmatter)
    handler_cls = _load_handler_class(skill_dir, meta.handler_class)
    return handler_cls(meta=meta, skill_dir=skill_dir, skill_doc=body)


def discover_skill_dirs(skills_root: Path) -> list[Path]:
    if not skills_root.is_dir():
        return []
    dirs: list[Path] = []
    for child in sorted(skills_root.iterdir()):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        if (child / SKILL_MANIFEST).exists():
            dirs.append(child)
        else:
            logger.warning("跳过非标准技能目录（缺少 SKILL.md）: %s", child)
    return dirs
