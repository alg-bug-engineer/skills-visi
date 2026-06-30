"""Skill package structure tests."""

from intersection_agent.models.domain import SuggestionResult
from intersection_agent.services.skill_service import SkillService
from intersection_agent.services.suggestion_service import SuggestionService


def test_build_measure_line_prefers_action_plan_over_formula():
    suggestion = SuggestionResult(
        delta_seconds=8,
        direction="reallocate",
        narrative="",
        confidence=0.8,
        rule_id="rule_turn_imbalance",
        action_type="reallocate_green",
    )
    governance = {
        "action_plan": {
            "action_type": "reallocate_green",
            "donor_turn": {"label": "北左转"},
            "recipient_turn": {"label": "东左转"},
        }
    }
    line = SuggestionService.build_measure_line(suggestion, governance)
    assert "北左转" in line and "东左转" in line and "8 秒" in line
    # 量化措施不应暴露 min(...) 公式
    assert "min(" not in line


def test_skill_package_renders_solution_measure_demotes_formula(skill_dir_path):
    from tests.test_skill_fast_path import _sample_session

    session = _sample_session()
    session.suggestion = SuggestionResult(
        delta_seconds=8,
        direction="reallocate",
        narrative="压缩北左转低效绿灯，转移至东左转。",
        confidence=0.82,
        rule_id="rule_turn_imbalance",
        action_type="reallocate_green",
    )
    session.data_payload = {
        "flow_timing_governance": {
            "action_plan": {
                "action_type": "reallocate_green",
                "donor_turn": {"label": "北左转"},
                "recipient_turn": {"label": "东左转"},
            }
        },
        "case_experience": [
            {
                "scenario_name": "短间距协调路口",
                "problems": [
                    {"problem": "下游回溢", "solutions": [{"name": "协调控流"}]}
                ],
            }
        ],
    }

    service = SkillService()
    result = service.upsert_from_session(session)
    assert result.record.solution_measure
    assert "东左转" in result.record.solution_measure

    pkg = skill_dir_path / result.record.skill_dir
    skill_md = (pkg / "SKILL.md").read_text(encoding="utf-8")
    reference = (pkg / "reference.md").read_text(encoding="utf-8")

    # 治理建议改为量化措施呈现
    assert "东左转" in skill_md
    assert "固化治理措施（量化）" in reference
    assert "同类场景经验（案例库）" in reference
    assert "短间距协调路口" in reference
    # 公式被降级为「内部回退」，不再作为对外治理建议
    assert "回退" in reference
    assert "## 建议计算公式" not in reference


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
