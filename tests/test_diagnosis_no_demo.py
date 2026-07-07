import json
from pathlib import Path

import pytest

from app.config import Settings
from app.data.diagnosis_input import resolve_diagnosis_inputs
from app.runtime.executor import SkillExecutor
from app.runtime.registry import get_registry


FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def overflow_fixtures() -> tuple[dict, dict]:
    metrics = json.loads((FIXTURES / "overflow_metrics.json").read_text(encoding="utf-8"))
    topology = json.loads((FIXTURES / "overflow_topology.json").read_text(encoding="utf-8"))
    return metrics, topology


def test_resolve_rejects_demo_when_fallback_disabled():
    settings = Settings(allow_demo_fallback=False, pg_dsn="")
    resolved = resolve_diagnosis_inputs(
        {"diagnosis_ticket": {"intersection_name": "测试路口"}},
        settings,
    )
    assert resolved["ok"] is False
    assert resolved["available"] is False
    assert "allow_demo_fallback" in resolved["reason"]


def test_resolve_accepts_task_injection(overflow_fixtures):
    metrics, topology = overflow_fixtures
    settings = Settings(allow_demo_fallback=False)
    resolved = resolve_diagnosis_inputs(
        {"metrics": metrics, "topology": topology},
        settings,
    )
    assert resolved["ok"] is True
    assert resolved["source"] == "task_injection"


def test_resolve_demo_explicit_mock_source():
    settings = Settings(allow_demo_fallback=True)
    resolved = resolve_diagnosis_inputs(
        {"diagnosis_ticket": {"intersection_name": "文化西路与舜华路交叉口", "direction": "东向西"}},
        settings,
    )
    assert resolved["ok"] is True
    assert resolved["source"] == "mock"


@pytest.mark.asyncio
async def test_diagnosis_skill_fails_without_data():
    registry = get_registry()
    skill = registry.get("data_analysis_diagnosis")
    from app.runtime.skill_types import SkillContext

    context = SkillContext(
        trace_id="no-data-test",
        user_input="test",
        task={"diagnosis_ticket": {"intersection_name": "未知路口"}},
    )
    result = await skill.run(context, settings=Settings(allow_demo_fallback=False))
    assert result.success is False
    assert result.output["available"] is False


@pytest.mark.asyncio
async def test_diagnosis_skill_with_injection(overflow_fixtures):
    metrics, topology = overflow_fixtures
    registry = get_registry()
    skill = registry.get("data_analysis_diagnosis")
    from app.runtime.skill_types import SkillContext

    context = SkillContext(
        trace_id="inject-test",
        user_input="test",
        task={
            "diagnosis_ticket": {
                "intersection_name": "文化西路与舜华路交叉口",
                "direction": "东向西",
                "movement": "直行",
            },
            "metrics": metrics,
            "topology": topology,
        },
    )
    result = await skill.run(context, settings=Settings(allow_demo_fallback=False))
    assert result.success is True
    assert result.output["data_source"] == "task_injection"
    assert result.output["problem_confirmed"] is True


@pytest.mark.asyncio
async def test_pipeline_stops_when_diagnosis_unavailable(script_user_input):
    executor = SkillExecutor(get_registry())
    result = await executor.run_pipeline(
        trace_id="pipeline-no-data",
        user_input=script_user_input,
        settings=Settings(llm_mock=True, allow_demo_fallback=False),
        llm=__import__("app.llm.qwen", fromlist=["QwenClient"]).QwenClient(
            Settings(llm_mock=True)
        ),
    )
    assert result["completed"] is False
    assert len(result["results"]) == 2
    assert result["results"][1]["skill_id"] == "data_analysis_diagnosis"
    assert result["results"][1]["success"] is False
