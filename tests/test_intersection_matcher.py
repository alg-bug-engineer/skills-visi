import pytest

from app.data.intersection_matcher import (
    generate_name_variants,
    match_intersection,
    score_candidate,
)
from app.data.pg_adapters import parse_time_step_range


def test_generate_name_variants_reversed_order():
    variants = generate_name_variants("文化西路与舜华路路口")
    assert "舜华路与文化西路路口" in variants
    assert "文化西路与舜华路" in variants


def test_score_candidate_reversed_roads():
    score = score_candidate(
        query_terms=["舜华路与文化西路"],
        user_input="舜华路和文化西路这个口排队很长",
        candidate={"inter_name": "文化西路与舜华路路口"},
    )
    assert score >= 0.85


def test_match_intersection_fixture_registry():
    result = match_intersection(
        primary_name="文化西路与舜华路交叉口",
        user_input="文化西路舜华路路口溢出",
    )
    assert result["matched"] is True
    assert result["inter_id"] == "demo_wenhua_shunhua"


def test_parse_time_step_range():
    lo, hi = parse_time_step_range("17:30-18:30")
    assert lo == 17 * 12 + 30 // 5
    assert hi == 18 * 12 + 30 // 5
    assert lo < hi


def test_filter_rows_by_step_range():
    from app.data.load_intersection_from_pg import _filter_rows_by_step_range

    rows = [
        {"step_index": 200, "value": 1},
        {"step_index": 210, "value": 2},
        {"step_index": 220, "value": 3},
    ]
    filtered = _filter_rows_by_step_range(rows, 210, 210)
    assert len(filtered) == 1
    assert filtered[0]["value"] == 2
