"""路口案例全量呈现：跨路口 accepted/risk + 固化 skill join + 去重。"""

from __future__ import annotations

from typing import Any


class _FakeCaseLibrary:
    def search_case_cards(self, *, problem_type: str, limit: int) -> dict[str, Any]:
        return {"cards": []}


class _FakeFeedback:
    def __init__(self, accepted: list[dict], rejected: list[dict]) -> None:
        self._accepted = accepted
        self._rejected = rejected

    def search_accepted_plans(self, *, inter_id=None, problem_type=None, limit=5):
        return list(self._accepted)[:limit]

    def search_rejected_patterns(self, *, inter_id=None, problem_type=None, limit=5):
        return list(self._rejected)[:limit]


class _FakeSkillService:
    def __init__(self, skills: list[dict]) -> None:
        self._skills = skills

    def list_skills(self) -> list[dict]:
        return list(self._skills)


def _make_service(**kwargs):
    from app.services.cases_catalog_service import CasesCatalogService

    return CasesCatalogService(**kwargs)


def test_recommended_join_skill_download():
    accepted = [
        {
            "trace_id": "t1",
            "plan_id": "plan_dp",
            "inter_id": "INT_A",
            "intersection_name": "经十路与转山西路路口",
            "time_period": "早高峰",
            "tags": {"strategy_applied": "干线联控", "primary_cause": "下游受阻"},
        }
    ]
    skills = [
        {
            "skill_id": "skill-INT_A-早高峰",
            "inter_id": "INT_A",
            "time_period_label": "06:10-06:30",
            "download_url": "/api/v1/agent/skills/skill-INT_A-早高峰/download",
            "tags": {"match": {"inter_id": "INT_A", "time_period": "早高峰"}},
        }
    ]
    service = _make_service(
        case_service=_FakeCaseLibrary(),
        feedback_service=_FakeFeedback(accepted, []),
        skill_service=_FakeSkillService(skills),
    )
    result = service.list_cases(category="recommended", limit=50)
    assert result["total"] == 1
    case = result["cases"][0]
    assert case["category"] == "recommended"
    assert case["inter_id"] == "INT_A"
    assert case["skill"]["skill_id"] == "skill-INT_A-早高峰"
    assert case["skill"]["download_url"].endswith("/download")


def test_recommended_dedup_same_inter_strategy_period():
    accepted = [
        {
            "trace_id": "t1",
            "plan_id": "plan_dp",
            "inter_id": "INT_A",
            "time_period": "早高峰",
            "tags": {"strategy_applied": "干线联控"},
        },
        {
            "trace_id": "t2",
            "plan_id": "plan_dp",
            "inter_id": "INT_A",
            "time_period": "早高峰",
            "tags": {"strategy_applied": "干线联控"},
        },
    ]
    service = _make_service(
        case_service=_FakeCaseLibrary(),
        feedback_service=_FakeFeedback(accepted, []),
    )
    result = service.list_cases(category="recommended", limit=50)
    assert result["total"] == 1


def test_recommended_without_skill_service_has_null_skill():
    accepted = [
        {
            "trace_id": "t1",
            "plan_id": "plan_dp",
            "inter_id": "INT_B",
            "time_period": "晚高峰",
            "tags": {"strategy_applied": "下游保护"},
        }
    ]
    service = _make_service(
        case_service=_FakeCaseLibrary(),
        feedback_service=_FakeFeedback(accepted, []),
    )
    result = service.list_cases(category="recommended", limit=50)
    assert result["cases"][0]["skill"] is None
