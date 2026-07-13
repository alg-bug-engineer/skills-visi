import json
from pathlib import Path

import pytest

from app.services.case_library import CaseLibraryService
from app.services.case_tag_extractor import CaseTagExtractor

ARTERIAL_CASE = {
    "案例场景": "两路口相距约150m，南连城市快速路；高峰期排队溢出频发。",
    "交通问题诊断": "短间距叠加信号配时不合理，南北直行与左转相位顺序不当造成南口车流清空不及时；排队溢出频发。",
    "治理方案": "统一公共周期；设定绿波协调参数；上下游协调配时。",
    "预期效果": "晚高峰减少35分钟；拥堵指数下降。",
}

POINT_CASE = {
    "案例场景": "典型历史城区高密度路网中的关键瓶颈路口，东进口3条进口车道。",
    "交通问题诊断": "高峰左转通行能力不足引发排队溢出，信号配时优化收效甚微。",
    "治理方案": "渠化改造：将东进口原直行车道改为可变导向车道；东进口单口放行。",
    "预期效果": "左转车道饱和度由1.47降至0.90。",
}


@pytest.fixture
def library(tmp_path: Path) -> Path:
    path = tmp_path / "cases.jsonl"
    path.write_text(
        json.dumps(ARTERIAL_CASE, ensure_ascii=False)
        + "\n"
        + json.dumps(POINT_CASE, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return path


def test_extract_tags_covers_dimensions(library: Path):
    extractor = CaseTagExtractor()
    tags = extractor.extract_tags(ARTERIAL_CASE)
    assert "scope_type" in tags
    assert "arterial_coordination" in tags["scope_type"]
    assert "queue_overflow" in tags.get("problem_type", [])


def test_arterial_query_ranks_coordination_case_first(library: Path):
    service = CaseLibraryService(library)
    query_profile = {
        "problem_type": ["queue_overflow"],
        "scope_type": ["arterial_coordination"],
        "spatial_topology": ["downstream_constraint"],
    }
    result = service.search_case_cards(
        problem_type="排队溢出",
        query_profile=query_profile,
    )
    assert result["cards"]
    top = result["cards"][0]
    assert "绿波" in top["title"] or "150m" in top["title"] or "协调" in str(
        top.get("structured_tags")
    )


def test_point_query_ranks_channelization_case(library: Path):
    service = CaseLibraryService(library)
    query_profile = {
        "problem_type": ["queue_overflow"],
        "scope_type": ["point_intersection"],
        "lane_organization": ["variable_lane"],
    }
    result = service.search_case_cards(
        problem_type="排队溢出",
        query_profile=query_profile,
    )
    assert result["cards"]
    top = result["cards"][0]
    tags = top.get("structured_tags") or {}
    flat = " ".join(" ".join(v) for v in tags.values())
    assert "可变" in flat or "点位" in flat or "渠化" in flat


def test_build_query_profile_from_diagnosis():
    extractor = CaseTagExtractor()
    profile = extractor.build_query_profile(
        ticket={"problem_type": "排队溢出", "period": "晚高峰"},
        diagnosis={
            "arterial_coordination_needed": True,
            "overflow_verification": {"verified": True},
            "downstream_diagnosis": {"scenario": "saturated"},
        },
    )
    assert "queue_overflow" in profile.get("problem_type", [])
    assert "arterial_coordination" in profile.get("scope_type", [])
    assert "evening_peak" in profile.get("time_period", [])


def test_search_case_cards_structured_fields(library: Path):
    service = CaseLibraryService(library)
    result = service.search_case_cards(problem_type="排队溢出")
    assert result["matched_count"] >= 1
    card = result["cards"][0]
    assert card["structured_tags"]
    assert len(card["similarity_dimensions"]) >= 1
    assert card["help_summary"]
    assert card["transferable_actions"]
    assert card["caveats"]
    assert card["similarity_tier"] in ("high", "matched")
