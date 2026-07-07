import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_plan_regenerate_endpoint(script_user_input, overflow_fixtures):
    metrics, topology = overflow_fixtures
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/api/v1/agent/run",
            json={
                "user_input": script_user_input,
                "trace_id": "regen-test",
                "task": {"metrics": metrics, "topology": topology},
                "stop_after": "strategy_generation",
            },
        )
        assert first.status_code == 200
        first_data = first.json()

        artifacts = {
            "intent": first_data["phases"].get("intent"),
            "diagnosis": first_data["phases"].get("diagnosis"),
            "cause": first_data["phases"].get("cause"),
            "strategy": first_data["phases"].get("strategy"),
        }
        task = {
            "artifacts": {
                "intent_understanding": artifacts["intent"],
                "data_analysis_diagnosis": artifacts["diagnosis"],
                "cause_analysis": artifacts["cause"],
                "strategy_generation": artifacts["strategy"],
            },
            "diagnosis_ticket": first_data["diagnosis_ticket"],
            "metrics": metrics,
            "topology": topology,
        }

        regen = await client.post(
            "/api/v1/agent/plan/regenerate",
            json={
                "trace_id": "regen-test",
                "user_input": "保持下游保护，小幅增加东向西绿灯",
                "task": task,
                "restart_from": "plan_generation",
            },
        )

    assert regen.status_code == 200
    data = regen.json()
    assert data["completed"] is True
    assert data["plan"]["recommended"]["plan_id"]
    assert data["plan"]["recommendation"]["rationale"]
