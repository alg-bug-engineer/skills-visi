import json
from pathlib import Path

from app.services.case_library import CaseLibraryService


def test_search_case_cards_structured_fields(tmp_path: Path):
    library = tmp_path / "cases.jsonl"
    library.write_text(
        json.dumps(
            {
                "案例场景": "晚高峰排队溢出，下游节点高饱和",
                "交通问题诊断": "排队溢出 下游承接不足",
                "治理方案": "上下游协调配时与防溢流相位保护",
                "预期效果": "排队长度下降30%",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    service = CaseLibraryService(library)
    result = service.search_case_cards(problem_type="排队溢出")

    assert result["matched_count"] >= 1
    assert result["cards"]
    card = result["cards"][0]
    assert len(card["similarity_dimensions"]) >= 1
    assert card["structured_tags"]
    assert card["help_summary"]
    assert card["transferable_actions"]
    assert card["caveats"]
    assert card["similarity_tier"] in ("high", "matched")
