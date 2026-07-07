import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_cases_list_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/agent/cases", params={"problem_type": "排队溢出", "limit": 5})
    assert response.status_code == 200
    data = response.json()
    assert "cases" in data
    assert data["total"] >= 0
    if data["cases"]:
        assert data["cases"][0]["category"] in {"textbook", "recommended", "risk"}


@pytest.mark.asyncio
async def test_cases_filter_category():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/agent/cases", params={"category": "textbook", "limit": 3})
    assert response.status_code == 200
    data = response.json()
    assert all(item["category"] == "textbook" for item in data["cases"])
