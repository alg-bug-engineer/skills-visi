from pathlib import Path

import pytest

from app.config import PROJECT_ROOT
from app.runtime.registry import SkillRegistry
from app.runtime.skill_loader import (
    discover_skill_dirs,
    load_skill_from_dir,
    validate_skill_layout,
)


def test_skill_folders_are_standard_layout():
    skills_root = PROJECT_ROOT / "skills"
    skill_dirs = discover_skill_dirs(skills_root)
    assert len(skill_dirs) == 5

    for skill_dir in skill_dirs:
        errors = validate_skill_layout(skill_dir)
        assert errors == [], f"{skill_dir.name} 结构不合规: {errors}"
        assert (skill_dir / "SKILL.md").is_file()
        assert (skill_dir / "handler.py").is_file()
        assert (skill_dir / "scripts").is_dir()
        assert (skill_dir / "references").is_dir()
        assert (skill_dir / "resources").is_dir()
        assert any((skill_dir / "scripts").iterdir())
        assert any((skill_dir / "references").iterdir())
        assert any((skill_dir / "resources").iterdir())


def test_skill_discovery_registers_five_skills():
    registry = SkillRegistry()
    registry.discover_and_register()
    skills = registry.list_skills()
    skill_ids = {s["skill_id"] for s in skills}
    assert skill_ids == {
        "intent_understanding",
        "data_analysis_diagnosis",
        "cause_analysis",
        "strategy_generation",
        "plan_generation",
    }


def test_skill_metadata_from_skill_md():
    registry = SkillRegistry()
    registry.discover_and_register()
    intent = registry.get("intent_understanding")
    assert intent.meta.display_name == "意图理解"
    assert intent.meta.phase == "intent_understanding"
    assert intent.skill_dir.name == "intent-understanding"
    assert "scripts/build_spatial_objects.py" in intent.meta.script_files
    assert "references/rules.md" in intent.meta.reference_files
    assert intent.skill_doc.startswith("# 意图理解")


def test_load_skill_from_dir():
    skill_dir = PROJECT_ROOT / "skills" / "intent-understanding"
    skill = load_skill_from_dir(skill_dir)
    assert skill.meta.skill_id == "intent_understanding"
    assert skill.load_resource("system").startswith("你是交通智能体意图理解技能")
