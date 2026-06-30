"""经验库聚合接口 /experience/library 测试。"""

import pytest

from intersection_agent.stores.intersection_profile_store import IntersectionProfileStore


def _seed_profile(inter_id: str = "inter_001") -> None:
    store = IntersectionProfileStore()
    store.add_cognition(inter_id, text="下午四点常堵", status="verified", source="data")
    store.add_diagnosis(
        inter_id, cause="旁边小学放学", dimension="event", source="user", confidence=0.6
    )
    store.add_solution_ref(
        inter_id, skill_id="skill_x", qualitative="绿灯多给点", quantified="东进口绿灯 +8s"
    )


@pytest.mark.asyncio
async def test_experience_library_returns_three_buckets(client, skill_dir_path):
    _seed_profile()
    resp = await client.get("/api/v1/experience/library", params={"inter_id": "inter_001"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["inter_id"] == "inter_001"
    assert len(body["cognition"]) == 1
    assert body["cognition"][0]["status"] == "verified"
    assert len(body["diagnosis"]) == 1
    assert body["diagnosis"][0]["dimension"] == "event"
    assert len(body["solution"]) == 1
    assert body["solution"][0]["quantified"] == "东进口绿灯 +8s"


@pytest.mark.asyncio
async def test_experience_library_aggregates_all_when_no_inter_id(client, skill_dir_path):
    _seed_profile("inter_001")
    _seed_profile("inter_002")
    resp = await client.get("/api/v1/experience/library")
    assert resp.status_code == 200
    body = resp.json()
    assert body["inter_id"] is None
    assert len(body["cognition"]) == 2
    assert len(body["solution"]) == 2


@pytest.mark.asyncio
async def test_experience_library_empty_profile(client, skill_dir_path):
    resp = await client.get("/api/v1/experience/library", params={"inter_id": "nope"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["cognition"] == []
    assert body["diagnosis"] == []
    assert body["solution"] == []


def test_cognition_dedup_upgrades_status(skill_dir_path):
    """同一问题重复写入只保留 1 条，且高状态覆盖低状态（数据验证升级）。"""
    store = IntersectionProfileStore()
    store.add_cognition("inter_001", text="下午四点常堵", status="data_doubt", source="user")
    # 归一化后同一文本（标点/空白差异），数据复核命中升级为 verified。
    store.add_cognition(
        "inter_001", text="下午四点，常堵。", status="verified", source="data"
    )
    profile = store.load("inter_001")
    assert len(profile.cognition) == 1
    assert profile.cognition[0].status == "verified"


def test_diagnosis_dedup_keeps_higher_confidence(skill_dir_path):
    """同 cause+dimension 重复写入只保留 1 条，且保留高 confidence。"""
    store = IntersectionProfileStore()
    store.add_diagnosis(
        "inter_001", cause="旁边小学放学", dimension="event", source="user", confidence=0.4
    )
    store.add_diagnosis(
        "inter_001", cause="旁边小学放学", dimension="event", source="data", confidence=0.8
    )
    profile = store.load("inter_001")
    assert len(profile.diagnosis) == 1
    assert profile.diagnosis[0].confidence == 0.8
    assert profile.diagnosis[0].source == "data"


def test_solution_dedup_updates_latest(skill_dir_path):
    """同 skill_id+量化公式重复写入只保留 1 条，并更新为最新内容。"""
    store = IntersectionProfileStore()
    store.add_solution_ref(
        "inter_001", skill_id="skill_x", qualitative="绿灯多给", quantified="东进口绿灯 +8s"
    )
    store.add_solution_ref(
        "inter_001", skill_id="skill_x", qualitative="按需放行", quantified="东进口绿灯 +8s"
    )
    profile = store.load("inter_001")
    assert len(profile.solution_ref) == 1
    assert profile.solution_ref[0].qualitative == "按需放行"
