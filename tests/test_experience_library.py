import json
from pathlib import Path

from app.services.experience_library import ExperienceLibraryService


def _write_samples(path: Path) -> None:
    samples = [
        {
            "record_id": "ue_1",
            "trace_id": "tr-a",
            "experience_type": "diagnostic",
            "content": "附近有学校下午接送导致拥堵",
            "tags": {
                "inter_id": "INT001",
                "intersection_name": "文化西路与舜华路交叉口",
                "cause_dimension": "event",
                "cause_keywords": ["学校", "接送"],
                "related_poi": ["学校"],
            },
        },
        {
            "record_id": "ue_2",
            "trace_id": "tr-b",
            "experience_type": "solution",
            "content": "应该增加绿灯时间",
            "tags": {
                "inter_id": "INT001",
                "intersection_name": "文化西路与舜华路交叉口",
                "strategy_action": "加绿",
            },
        },
    ]
    with path.open("w", encoding="utf-8") as handle:
        for item in samples:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def test_search_diagnostic_by_school_keyword(tmp_path: Path):
    lib_path = tmp_path / "user_experience.jsonl"
    _write_samples(lib_path)
    service = ExperienceLibraryService(lib_path)

    hits = service.search_diagnostic(
        inter_id="INT001",
        keywords=["学校"],
        limit=5,
    )
    assert len(hits) == 1
    assert hits[0]["record_id"] == "ue_1"
    assert hits[0]["score"] > 0


def test_search_solution_by_strategy_action(tmp_path: Path):
    lib_path = tmp_path / "user_experience.jsonl"
    _write_samples(lib_path)
    service = ExperienceLibraryService(lib_path)

    hits = service.search_solution(inter_id="INT001", strategy_action="加绿", limit=3)
    assert len(hits) == 1
    assert hits[0]["tags"]["strategy_action"] == "加绿"


def test_list_all_grouped_returns_full_history(tmp_path: Path):
    """全量呈现：按类型分组返回所有历史经验（非检索/非打分）。"""
    lib_path = tmp_path / "user_experience.jsonl"
    _write_samples(lib_path)
    service = ExperienceLibraryService(lib_path)

    grouped = service.list_all_grouped()
    assert len(grouped["diagnostic"]) == 1
    assert len(grouped["solution"]) == 1
    assert len(grouped["cognitive"]) == 0
    # 补齐路口绑定字段
    assert grouped["diagnostic"][0]["inter_id"] == "INT001"
    assert grouped["diagnostic"][0]["intersection_name"] == "文化西路与舜华路交叉口"


def test_list_all_dedups_identical_records(tmp_path: Path):
    """读时按内容指纹去重，容错历史重复行。"""
    lib_path = tmp_path / "user_experience.jsonl"
    dup = {
        "record_id": "ue_dup",
        "recorded_at": "2026-07-01T00:00:00+00:00",
        "experience_type": "cognitive",
        "content": "南向北直行早高峰排队溢出",
        "source_span": "南向北直行早高峰排队溢出",
        "tags": {"inter_id": "INT9", "problem_type": "排队溢出"},
    }
    with lib_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(dup, ensure_ascii=False) + "\n")
        handle.write(json.dumps({**dup, "record_id": "ue_dup2"}, ensure_ascii=False) + "\n")

    service = ExperienceLibraryService(lib_path)
    items = service.list_all(experience_type="cognitive")
    assert len(items) == 1
