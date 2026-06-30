"""案例库浏览接口 /cases/industry 与 /cases/intersections 测试。"""

import pytest

from intersection_agent.stores.intersection_profile_store import IntersectionProfileStore


@pytest.mark.asyncio
async def test_industry_cases_returns_scenarios(client, skill_dir_path):
    resp = await client.get("/api/v1/cases/industry")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list) and len(body) == 19
    sample = next(s for s in body if s["scenario_id"] == "arterial_green_wave")
    assert sample["problems"]
    prob = sample["problems"][0]
    assert "occurrence" in prob
    sol = prob["solutions"][0]
    assert "representative_cases" in sol


@pytest.mark.asyncio
async def test_industry_cases_filter_by_query(client, skill_dir_path):
    resp = await client.get("/api/v1/cases/industry", params={"q": "学校"})
    assert resp.status_code == 200
    body = resp.json()
    ids = {s["scenario_id"] for s in body}
    assert "school_zone" in ids
    # 过滤后应明显少于全部
    assert len(body) < 19


def _seed_full_case(inter_id: str) -> None:
    store = IntersectionProfileStore()
    store.add_cognition(inter_id, text="早高峰空放", status="verified", source="data")
    store.add_diagnosis(
        inter_id, cause="附近学校放学", dimension="event", source="user", confidence=0.6
    )
    store.add_solution_ref(
        inter_id, skill_id="skill_x", qualitative="压缩空放", quantified="东进口绿灯 -6s"
    )


def _seed_cognition_only(inter_id: str) -> None:
    IntersectionProfileStore().add_cognition(
        inter_id, text="只有认知没有方案", status="data_doubt", source="user"
    )


@pytest.mark.asyncio
async def test_intersection_cases_only_with_solution(client, skill_dir_path):
    _seed_full_case("inter_full")
    _seed_cognition_only("inter_partial")
    resp = await client.get("/api/v1/cases/intersections")
    assert resp.status_code == 200
    body = resp.json()
    ids = {c["inter_id"] for c in body}
    assert "inter_full" in ids
    assert "inter_partial" not in ids
    case = next(c for c in body if c["inter_id"] == "inter_full")
    assert case["cognition"] and case["diagnosis"] and case["solutions"]
    assert case["solutions"][0]["quantified"] == "东进口绿灯 -6s"


@pytest.mark.asyncio
async def test_intersection_cases_empty(client, skill_dir_path):
    resp = await client.get("/api/v1/cases/intersections")
    assert resp.status_code == 200
    assert resp.json() == []
