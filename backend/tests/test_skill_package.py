"""Skill package structure tests."""

from intersection_agent.services.skill_service import SkillService


def test_upsert_writes_standard_skill_package(skill_dir_path, tmp_path):
    from tests.test_skill_fast_path import _sample_session

    service = SkillService()
    session = _sample_session()
    result = service.upsert_from_session(session)
    assert result.action == "created"

    pkg = skill_dir_path / result.record.skill_dir
    assert (pkg / "SKILL.md").is_file()
    assert (pkg / "skill.meta.json").is_file()
    assert (pkg / "reference.md").is_file()
    assert (pkg / "scripts" / "fetch_traffic_data.py").is_file()
    assert (pkg / "scripts" / "fetch_traffic_data.sql").is_file()

    skill_md = (pkg / "SKILL.md").read_text(encoding="utf-8")
    assert skill_md.startswith("---")
    assert "name:" in skill_md
    assert result.record.intersection in skill_md
    assert "fetch_traffic_data.py" in skill_md


def test_list_skills_loads_from_package(skill_dir_path):
    from tests.test_skill_fast_path import _sample_session

    service = SkillService()
    service.upsert_from_session(_sample_session())
    skills = service.list_skills()
    assert len(skills) == 1
    assert skills[0].skill_dir.startswith("congestion-")
