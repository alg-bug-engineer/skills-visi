"""Corridor pick resolver tests."""

from intersection_agent.services.corridor_pick_resolver import resolve_corridor_pick

RANKED = [
    {"inter_id": "1", "inter_name": "奥体西路与经十路路口", "rank": 1, "has_data": True},
    {"inter_id": "2", "inter_name": "奥体西路与龙奥北路路口", "rank": 2, "has_data": True},
    {"inter_id": "3", "inter_name": "坤顺路与奥体西路路口", "rank": 3, "has_data": True},
]


def test_pick_by_abbreviated_junction():
    picked = resolve_corridor_pick("奥体西与经十路", RANKED)
    assert picked is not None
    assert picked["inter_id"] == "1"


def test_pick_by_full_junction_name():
    picked = resolve_corridor_pick("奥体西路与经十路", RANKED)
    assert picked is not None
    assert picked["inter_id"] == "1"


def test_pick_by_inter_id():
    picked = resolve_corridor_pick("", RANKED, inter_id="2")
    assert picked is not None
    assert picked["inter_id"] == "2"


def test_pick_by_rank_phrase():
    picked = resolve_corridor_pick("第二个", RANKED)
    assert picked is not None
    assert picked["inter_id"] == "2"
