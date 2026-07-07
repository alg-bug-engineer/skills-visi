import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import app
from app.services.intersection_load_service import IntersectionLoadService


@pytest.mark.asyncio
async def test_intersection_load_without_pg():
    service = IntersectionLoadService(Settings(pg_dsn=""))
    result = service.load(intersection_name="文化西路与舜华路交叉口")
    assert result["ok"] is False
    assert result["reason"] == "pg_dsn_not_configured"


@pytest.mark.asyncio
async def test_intersection_load_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/intersection/load",
            json={"intersection_name": "文化西路与舜华路交叉口", "time_range": "18:10-18:30"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["reason"] in ("pg_dsn_not_configured", "pg_load_failed")


def test_build_agent_task_from_fixtures(overflow_fixtures):
    metrics, topology = overflow_fixtures
    loaded = {
        "ok": True,
        "task": {"metrics": metrics, "signal": {"cycle_s": 120}},
        "raw": {
            "inter": {
                "inter_id": "demo_wenhua_shunhua",
                "inter_name": "文化西路与舜华路交叉口",
                "lng": 117.12,
                "lat": 36.65,
            }
        },
        "checklist_queries": [
            {
                "item_id": "turn_flow",
                "label": "转向流量",
                "status": "has_data",
                "summary": "有数据",
            }
        ],
    }
    ticket = {
        "intersection_name": "文化西路与舜华路交叉口",
        "direction": "东向西",
        "movement": "直行",
    }
    service = IntersectionLoadService(Settings())
    task = service._build_agent_task(loaded, ticket)
    assert task["diagnosis_ticket"]["inter_id"] == "demo_wenhua_shunhua"
    assert task["topology"]
    assert task["metrics"]
    assert task["checklist_queries"]
