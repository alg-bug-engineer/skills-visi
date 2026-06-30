from intersection_agent.services.upstream_governance_trace_service import is_governable


PROFILES_FULL = [{"dir8_code": d, "turn_saturation_max": 0.95, "green_util_min": 0.6}
                 for d in (0, 2, 4, 6)]
PROFILES_SLACK = [
    {"dir8_code": 0, "turn_saturation_max": 0.95, "green_util_min": 0.6},
    {"dir8_code": 2, "turn_saturation_max": 0.70, "green_util_min": 0.6},  # 未饱和
    {"dir8_code": 4, "turn_saturation_max": 0.95, "green_util_min": 0.6},
    {"dir8_code": 6, "turn_saturation_max": 0.95, "green_util_min": 0.6},
]
PROFILES_EMPTY_GREEN = [
    {"dir8_code": 0, "turn_saturation_max": 0.95, "green_util_min": 0.40},  # 空槽
    {"dir8_code": 2, "turn_saturation_max": 0.95, "green_util_min": 0.6},
    {"dir8_code": 4, "turn_saturation_max": 0.95, "green_util_min": 0.6},
    {"dir8_code": 6, "turn_saturation_max": 0.95, "green_util_min": 0.6},
]


def test_full_saturation_not_governable():
    assert is_governable(PROFILES_FULL, full_sat=0.85, green_util=0.5) is False


def test_has_slack_direction_is_governable():
    assert is_governable(PROFILES_SLACK, full_sat=0.85, green_util=0.5) is True


def test_empty_green_makes_governable():
    assert is_governable(PROFILES_EMPTY_GREEN, full_sat=0.85, green_util=0.5) is True
