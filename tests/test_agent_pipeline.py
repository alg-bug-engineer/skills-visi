"""Agent 全链路宏观冒烟：完整跑通、健康短路、分步控制。"""

import pytest

from app.config import Settings
from app.logging_setup import get_trace_id, set_trace_id
from app.runtime.pipeline_validation import PipelineValidationError, resolve_pipeline
from app.services.agent_service import AgentService


HEALTHY_METRICS = {
    "queue_length_m": 60.0,
    "storage_length_m": 200.0,
    "volume_vph": 1200.0,
    "capacity_vph": 1750.0,
    "green_utilization": 0.7,
    "stop_count": 0.3,
    "avg_delay_s": 18.0,
    "downstream_queue_length_m": 40.0,
    "downstream_storage_length_m": 180.0,
    "downstream_volume_vph": 900.0,
    "downstream_capacity_vph": 1600.0,
    "downstream_green_utilization": 0.6,
    "upstream_arrival_intensity": "medium",
    "time_series_trend": "平稳",
}


@pytest.mark.asyncio
async def test_full_pipeline_with_mock_llm(script_user_input):
    settings = Settings(llm_mock=True)
    agent = AgentService(settings)
    result = await agent.run(script_user_input, trace_id="test-trace-001")

    assert result["completed"] is True
    assert result["trace_id"] == "test-trace-001"
    assert len(result["results"]) == 5

    ticket = result["artifacts"]["intent_understanding"]["diagnosis_ticket"]
    assert ticket["object_type"] == "路口"
    assert "文化西路" in ticket["intersection_name"]
    assert ticket["problem_type"] == "排队溢出"

    diagnosis = result["artifacts"]["data_analysis_diagnosis"]
    assert diagnosis["problem_confirmed"] is True
    assert diagnosis["downstream_trace"]["available"] is True
    assert diagnosis["flow_trace"]["available"] is True

    cause = result["artifacts"]["cause_analysis"]
    assert cause["arterial_coordination_needed"] is True

    strategy = result["artifacts"]["strategy_generation"]
    assert strategy["strategy_package"] == "arterial_coordination"

    plan = result["artifacts"]["plan_generation"]
    assert plan["recommended"]["plan_id"] == "arterial_coordination"
    assert plan["recommended"]["guardrail_pass"] is True
    assert len(plan["candidates"]) == 3


@pytest.mark.asyncio
async def test_healthy_intersection_short_circuits_pipeline(script_user_input, overflow_fixtures):
    _, topology = overflow_fixtures
    settings = Settings(llm_mock=True)
    agent = AgentService(settings)

    result = await agent.run(
        script_user_input,
        trace_id="healthy-run",
        task={"metrics": HEALTHY_METRICS, "topology": topology},
    )

    diag = result["artifacts"]["data_analysis_diagnosis"]
    assert diag["healthy"] is True
    assert diag["problem_confirmed"] is False
    assert "cause_analysis" not in result["artifacts"]
    assert "plan_generation" not in result["artifacts"]
    assert result["pipeline_complete"] is True
    assert result.get("healthy") is True


@pytest.mark.asyncio
async def test_stop_after_intent_only(script_user_input):
    settings = Settings(llm_mock=True)
    agent = AgentService(settings)
    result = await agent.run(
        script_user_input,
        trace_id="step-intent",
        stop_after="intent_understanding",
    )

    assert result["completed"] is True
    assert len(result["results"]) == 1
    assert result["results"][0]["skill_id"] == "intent_understanding"
    assert result["pipeline_complete"] is False


def test_invalid_skill_ids_order():
    with pytest.raises(PipelineValidationError):
        resolve_pipeline(skill_ids=["cause_analysis", "intent_understanding"])


@pytest.mark.asyncio
async def test_trace_id_propagation(script_user_input):
    settings = Settings(llm_mock=True)
    agent = AgentService(settings)
    set_trace_id("propagation-test")
    result = await agent.run(script_user_input)
    assert result["trace_id"] == "propagation-test"
    assert get_trace_id() == "propagation-test"
