"""ticket_nlu_schema：方向/时段 NLU 约束与 flow_correlate 映射。"""

from app.data.ticket_nlu_schema import (
    infer_diagnosis_period_type,
    normalize_ticket_period,
    normalize_travel_direction,
    resolve_correlate_period,
    resolve_period_label,
)


def test_normalize_travel_direction_colloquial():
    assert normalize_travel_direction("由南向北") == "南向北"
    assert normalize_travel_direction("由南向北直行") == "南向北"
    assert normalize_travel_direction("东向西") == "东向西"


def test_resolve_period_label_and_db_code():
    assert resolve_period_label("早上七点半") == "早高峰"
    assert resolve_period_label("晚高峰时段") == "晚高峰"
    assert resolve_period_label("白平峰") == "平峰"
    assert resolve_correlate_period("早高峰") == "MORNING_PEAK"
    assert resolve_correlate_period("EVENING_PEAK") == "EVENING_PEAK"


def test_infer_diagnosis_period_from_time_range():
    ticket = {"time_range": "07:30-07:50"}
    assert infer_diagnosis_period_type(ticket) == "MORNING_PEAK"
    ticket = {"period": "晚高峰", "time_range": "18:00-18:30"}
    assert infer_diagnosis_period_type(ticket) == "EVENING_PEAK"


def test_normalize_ticket_period():
    assert normalize_ticket_period("早高峰时段") == "早高峰"
    assert normalize_ticket_period("午平峰") == "平峰"
