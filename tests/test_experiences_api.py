import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_experiences_endpoint_returns_grouped():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/agent/experiences")
    assert response.status_code == 200
    data = response.json()
    assert "experiences" in data
    grouped = data["experiences"]
    for key in ("cognitive", "diagnostic", "solution"):
        assert key in grouped
        assert isinstance(grouped[key], list)
    assert data["total"] == sum(len(grouped[k]) for k in grouped)


@pytest.mark.asyncio
async def test_experiences_endpoint_filter_by_type():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/agent/experiences", params={"experience_type": "cognitive"}
        )
    assert response.status_code == 200
    data = response.json()
    assert set(data["experiences"].keys()) == {"cognitive"}
    for item in data["experiences"]["cognitive"]:
        assert item["experience_type"] == "cognitive"
