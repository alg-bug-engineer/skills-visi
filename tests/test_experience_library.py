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
