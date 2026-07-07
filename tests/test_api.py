import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import app


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
