"""trace_approach.resolve_trace_approach 单进口道选择。"""
from intersection_agent.utils.trace_approach import resolve_trace_approach


def _by_turn(rows):
    return rows


def test_turn_specific_west_left():
    rows = [
        {"dir8_code": 0, "turn_saturation": 0.95},
        {"dir8_code": 6, "turn_saturation": 1.1},
    ]
    d8, turn, label = resolve_trace_approach(["西左转", "北进口"], rows)
    assert d8 == 6
    assert turn == 1
    assert label == "西进口"


def test_specific_approach_west():
    rows = [
        {"dir8_code": 0, "turn_saturation": 0.95},
        {"dir8_code": 6, "turn_saturation": 0.40},
    ]
    d8, turn, label = resolve_trace_approach(["西进口"], rows)
    assert d8 == 6
    assert turn is None
    assert label == "西进口"


def test_direction_group_east_west_picks_east_only():
    rows = [
        {"dir8_code": 2, "turn_saturation": 0.88},
        {"dir8_code": 6, "turn_saturation": 0.99},
    ]
    d8, turn, label = resolve_trace_approach(["东西向"], rows)
    assert d8 == 2
    assert label == "东进口"


def test_direction_group_north_south_picks_north():
    rows = [
        {"dir8_code": 0, "turn_saturation": 0.91},
        {"dir8_code": 4, "turn_saturation": 0.95},
    ]
    d8, _, label = resolve_trace_approach(["南北向"], rows)
    assert d8 == 0
    assert label == "北进口"


def test_no_direction_picks_top_saturated():
    rows = [
        {"dir8_code": 0, "turn_saturation": 0.91},
        {"dir8_code": 2, "turn_saturation": 0.98},
    ]
    d8, _, label = resolve_trace_approach([], rows)
    assert d8 == 2
    assert label == "东进口"


def test_no_saturated_returns_none():
    rows = [{"dir8_code": 2, "turn_saturation": 0.5}]
    assert resolve_trace_approach([], rows) == (None, None, None)
