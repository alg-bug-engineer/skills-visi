import pytest

from app.config import PROJECT_ROOT, Settings
from app.llm.qwen import QwenClient
from app.runtime.skill_loader import load_skill_from_dir
from app.runtime.skill_types import SkillContext


@pytest.mark.asyncio
async def test_intent_understanding_skill(script_user_input):
    skill = load_skill_from_dir(PROJECT_ROOT / "skills" / "intent-understanding")
    context = SkillContext(trace_id="unit-001", user_input=script_user_input)
    llm = QwenClient(Settings(llm_mock=True))
    result = await skill.run(context, llm=llm)

    assert result.success is True
    ticket = result.output["diagnosis_ticket"]
    assert ticket["direction"] == "东向西"
    assert ticket["movement"] == "直行"
    assert "user_experiences" in result.output


@pytest.mark.asyncio
async def test_intent_understanding_three_experiences(tmp_path):
    user_input = (
        "文化西路与舜华路交叉口下午3点经常拥堵，"
        "这附近有一个小学那时候放学家长接送孩子导致的，"
        "应该增加一点绿灯时间。"
    )
    skill = load_skill_from_dir(PROJECT_ROOT / "skills" / "intent-understanding")
    context = SkillContext(trace_id="unit-exp", user_input=user_input)
    llm = QwenClient(Settings(llm_mock=True))
    experience_path = tmp_path / "user_experience.jsonl"
    from app.services.experience_service import ExperienceService
    from app.services.experience_library import ExperienceLibraryService

    result = await skill.run(
        context,
        llm=llm,
        experience_service=ExperienceService(experience_path),
        experience_library=ExperienceLibraryService(experience_path),
    )
    assert result.success is True
    experiences = result.output["user_experiences"]
    assert len(experiences) == 3
    assert experience_path.exists()


@pytest.mark.asyncio
async def test_data_analysis_with_custom_metrics():
    skill = load_skill_from_dir(PROJECT_ROOT / "skills" / "data-analysis-diagnosis")
    context = SkillContext(
        trace_id="unit-002",
        user_input="test",
        task={
            "diagnosis_ticket": {"intersection_name": "测试路口", "direction": "东向西"},
            "metrics": {
                "queue_length_m": 50,
                "storage_length_m": 200,
                "volume_vph": 500,
                "capacity_vph": 1000,
                "green_utilization": 0.5,
                "downstream_queue_length_m": 30,
                "downstream_storage_length_m": 150,
                "downstream_volume_vph": 400,
                "downstream_capacity_vph": 1000,
            },
            "topology": {"downstream_nodes": [], "upstream_nodes": []},
        },
    )
    result = await skill.run(context, settings=Settings(allow_demo_fallback=False))
    assert result.success is True
    assert result.output["overflow_verification"]["risk_level"] == "low"
    assert result.output["problem_confirmed"] is False
