import pytest

from app.runtime.skill_loader import validate_skill_layout


def test_validate_rejects_md_only_skill(tmp_path):
    skill_dir = tmp_path / "bad-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nmetadata:\n  skill_id: bad\n  phase: bad\n---\n",
        encoding="utf-8",
    )
    errors = validate_skill_layout(skill_dir)
    assert any("scripts" in e for e in errors)
    assert any("references" in e for e in errors)
    assert any("resources" in e for e in errors)
