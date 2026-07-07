import pytest

from app.config import Settings
from app.logging_setup import get_trace_id, set_trace_id
from app.services.agent_service import AgentService
from app.services.case_library import CaseLibraryService


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
    assert "优先避免下游继续外溢" in ticket["constraints"]

    diagnosis = result["artifacts"]["data_analysis_diagnosis"]
    assert diagnosis["problem_confirmed"] is True
    assert diagnosis["metrics"]["queue_ratio"] == pytest.approx(0.925, abs=0.01)
    assert diagnosis["downstream_trace"]["available"] is True
    assert diagnosis["flow_trace"]["available"] is True
    assert diagnosis["downstream_trace"]["adjacent_intersections"][0]["inter_name"]
    assert diagnosis["flow_trace"]["entry_traces"]
    assert diagnosis["arterial_analysis"]["need_upstream_metering"] is True
    assert diagnosis["downstream_diagnosis"]["release_answer"] == "下游接不住"
    assert diagnosis["map_scenes"]["downstream_trace_map"]["turn_traces"]

    intent = result["artifacts"]["intent_understanding"]
    assert intent["spatial_scene"]["available"] is True
    assert intent["diagnosis_ticket"]["inter_id"] == "demo_wenhua_shunhua"

    cause = result["artifacts"]["cause_analysis"]
    assert cause["arterial_coordination_needed"] is True
    assert len(cause["similar_cases"]) > 0
    assert cause["case_cards"]["cards"]

    strategy = result["artifacts"]["strategy_generation"]
    assert strategy["strategy_package"] == "arterial_coordination"
    assert "单点激进加绿" in strategy["strategy"]["not_recommended"]
    assert strategy["control_scope_map"]["available"] is True

    plan = result["artifacts"]["plan_generation"]
    assert plan["recommended"]["plan_id"] == "arterial_coordination"
    assert plan["recommended"]["guardrail_pass"] is True
    assert plan["recommended"]["timing"]["phase_stage_timing_list"]
    assert len(plan["candidates"]) == 3


@pytest.mark.asyncio
async def test_trace_id_propagation(script_user_input):
    settings = Settings(llm_mock=True)
    agent = AgentService(settings)
    tid = set_trace_id("propagation-test")
    result = await agent.run(script_user_input)
    assert result["trace_id"] == "propagation-test"
    assert get_trace_id() == "propagation-test"


def test_case_library_search():
    settings = Settings()
    service = CaseLibraryService(settings.case_library_abs_path)
    assert service.count() > 0
    cases = service.search_similar(problem_type="排队溢出", limit=3)
    assert len(cases) <= 3
    assert all("score" in c for c in cases)
