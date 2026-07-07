import pytest

from app.config import Settings
from app.runtime.pipeline_validation import PipelineValidationError, resolve_pipeline
from app.services.agent_service import AgentService


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
    assert result["diagnosis_ticket"]["problem_type"] == "排队溢出"
    assert result["pipeline_complete"] is False


@pytest.mark.asyncio
async def test_skill_ids_diagnosis_only(script_user_input, overflow_fixtures):
    metrics, topology = overflow_fixtures
    settings = Settings(llm_mock=True)
    agent = AgentService(settings)

    first = await agent.run(script_user_input, trace_id="step-diag-1", stop_after="intent_understanding")
    task = {
        "artifacts": first["artifacts"],
        "diagnosis_ticket": first["diagnosis_ticket"],
        "metrics": metrics,
        "topology": topology,
    }
    second = await agent.run(
        "",
        trace_id="step-diag-2",
        task=task,
        skill_ids=["data_analysis_diagnosis"],
    )

    assert second["completed"] is True
    assert "data_analysis_diagnosis" in second["artifacts"]
    assert "cause_analysis" not in second["artifacts"]
    assert second["artifacts"]["data_analysis_diagnosis"]["problem_confirmed"] is True


def test_invalid_skill_ids_order():
    with pytest.raises(PipelineValidationError):
        resolve_pipeline(skill_ids=["cause_analysis", "intent_understanding"])


@pytest.mark.asyncio
async def test_resume_from_cause(script_user_input, overflow_fixtures):
    metrics, topology = overflow_fixtures
    settings = Settings(llm_mock=True)
    agent = AgentService(settings)

    partial = await agent.run(
        script_user_input,
        trace_id="resume-cause",
        task={"metrics": metrics, "topology": topology},
        stop_after="data_analysis_diagnosis",
    )
    task = {
        "artifacts": partial["artifacts"],
        "diagnosis_ticket": partial["diagnosis_ticket"],
        "metrics": metrics,
        "topology": topology,
    }
    continued = await agent.run(
        "",
        trace_id="resume-cause",
        task=task,
        skill_ids=["cause_analysis", "strategy_generation", "plan_generation"],
    )

    assert continued["completed"] is True
    assert continued["pipeline_complete"] is True
    assert continued["artifacts"]["plan_generation"]["recommended"]["plan_id"] == "arterial_coordination"
