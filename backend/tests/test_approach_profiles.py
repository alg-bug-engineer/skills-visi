"""approach_profiles：把 by_turn 聚合成四进口道 profile。"""
from intersection_agent.services.data_fetcher import aggregate_approach_profiles


def test_aggregate_keeps_max_turn_sat_per_dir8():
    by_turn = [
        {"dir8_code": 0, "turn_dir_no": 2, "turn_saturation": 0.95, "green_utilization": 0.38},
        {"dir8_code": 0, "turn_dir_no": 1, "turn_saturation": 0.60, "green_utilization": 0.70},
        {"dir8_code": 4, "turn_dir_no": 2, "turn_saturation": 0.50, "green_utilization": 0.80},
    ]
    profiles = aggregate_approach_profiles(by_turn, by_approach=[])
    north = next(p for p in profiles if p["dir8_code"] == 0)
    assert north["turn_saturation_max"] == 0.95
    assert north["green_util_min"] == 0.38
    assert {p["dir8_code"] for p in profiles} == {0, 4}
