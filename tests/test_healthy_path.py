import pytest

from app.config import Settings
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
    # 健康分支：诊断后正常收尾，不再执行成因/策略/方案。
    assert "cause_analysis" not in result["artifacts"]
    assert "strategy_generation" not in result["artifacts"]
    assert "plan_generation" not in result["artifacts"]
    assert result["completed"] is True
    assert result["pipeline_complete"] is True
    assert result.get("healthy") is True


@pytest.mark.asyncio
async def test_problem_intersection_runs_full_pipeline(script_user_input, overflow_fixtures):
    metrics, topology = overflow_fixtures
    settings = Settings(llm_mock=True)
    agent = AgentService(settings)

    result = await agent.run(
        script_user_input,
        trace_id="problem-run",
        task={"metrics": metrics, "topology": topology},
    )

    diag = result["artifacts"]["data_analysis_diagnosis"]
    assert diag["healthy"] is False
    assert diag["problem_confirmed"] is True
    # 有问题：链路应走完成因/策略/方案。
    assert "cause_analysis" in result["artifacts"]
    assert "plan_generation" in result["artifacts"]
    assert result["pipeline_complete"] is True
