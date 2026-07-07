import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.response_builder import build_public_run_response
from app.config import get_settings
from app.main import app
from app.services.feedback_service import PlanFeedbackService


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_list_skills_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/agent/skills")
    assert response.status_code == 200
    skills = response.json()["skills"]
    assert len(skills) == 5
    assert "skill_id" not in skills[0]
    assert "display_name" in skills[0]


@pytest.mark.asyncio
async def test_run_agent_endpoint(script_user_input):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/run",
            json={"user_input": script_user_input, "trace_id": "api-test-001"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["completed"] is True
    assert data["trace_id"] == "api-test-001"
    assert "artifacts" not in data
    assert "pipeline" not in data
    assert "phases" in data
    assert data["plan"]["recommended"]["plan_id"] == "arterial_coordination"
    assert all("skill_id" not in item for item in data["phase_results"])


def test_public_run_response_strips_skill_ids():
    payload = build_public_run_response(
        {
            "trace_id": "t1",
            "completed": True,
            "diagnosis_ticket": {"intersection_name": "文化西路"},
            "artifacts": {
                "intent_understanding": {"spatial_scene": {"available": True}},
                "plan_generation": {"recommended": {"plan_id": "p1"}},
            },
            "results": [
                {"skill_id": "intent_understanding", "phase": "intent", "success": True},
            ],
        }
    )
    assert payload["phases"]["intent"]["spatial_scene"]["available"] is True
    assert payload["plan"]["recommended"]["plan_id"] == "p1"
    assert "skill_id" not in payload["phase_results"][0]


@pytest.mark.asyncio
async def test_plan_decision_endpoint(tmp_path: Path):
    feedback_path = tmp_path / "feedback.jsonl"
    get_settings.cache_clear()
    app.dependency_overrides.clear()

    from app.api import routes

    def override_feedback_service():
        return PlanFeedbackService(feedback_path)

    app.dependency_overrides[routes.get_feedback_service] = override_feedback_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/plan/decision",
            json={
                "trace_id": "api-test-001",
                "plan_id": "arterial_coordination",
                "decision": "reject",
                "rejection_reason": "下游排队仍偏高",
            },
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["decision"] == "reject"
    assert data["rejection_reason"] == "下游排队仍偏高"

    lines = feedback_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["trace_id"] == "api-test-001"
    assert record["plan_id"] == "arterial_coordination"
