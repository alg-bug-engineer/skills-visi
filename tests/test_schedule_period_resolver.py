"""时段解析：用户表达 → schedule target_periods + period_plan_no。"""

from app.data.schedule_period_resolver import (
    extract_schedule_periods,
    parse_explicit_period_key,
    resolve_timing_period,
)


SCHEDULE_ROWS = [
    {
        "week_day_no": 5,
        "day_plan_no": "1",
        "period_seq_no": 1,
        "start_time": "00:00:00",
        "end_time": "06:00:00",
        "period_plan_no": "1",
    },
    {
        "week_day_no": 5,
        "day_plan_no": "1",
        "period_seq_no": 2,
        "start_time": "06:00:00",
        "end_time": "07:00:00",
        "period_plan_no": "2",
    },
    {
        "week_day_no": 5,
        "day_plan_no": "1",
        "period_seq_no": 3,
        "start_time": "07:00:00",
        "end_time": "09:00:00",
        "period_plan_no": "3",
    },
    {
        "week_day_no": 5,
        "day_plan_no": "1",
        "period_seq_no": 4,
        "start_time": "17:00:00",
        "end_time": "19:00:00",
        "period_plan_no": "5",
    },
]


def test_parse_explicit_period_key():
    assert parse_explicit_period_key("17:30-18:30") == "17:30-18:30"
    assert parse_explicit_period_key("07:00–09:00") == "07:00-09:00"


def test_extract_schedule_periods():
    periods = extract_schedule_periods(SCHEDULE_ROWS, day_of_week=5)
    keys = [item["key"] for item in periods]
    assert "06:00-07:00" in keys
    assert "07:00-09:00" in keys
    assert periods[1]["plan_no"] == "2"


def test_resolve_explicit_time_range():
    ticket = {"time_range": "17:30-18:30", "period": "晚高峰"}
    resolved = resolve_timing_period(ticket, SCHEDULE_ROWS, day_of_week=5)
    assert resolved["ok"] is True
    assert resolved["target_periods"] == ["17:00-19:00"]
    assert resolved["flow_window"] == "17:30-18:30"
    assert resolved["match_method"] == "explicit_time_range_schedule_overlap"
    assert resolved["period_plan_no"] == "5"


def test_resolve_morning_peak_label():
    ticket = {"period": "早高峰", "time_range": ""}
    resolved = resolve_timing_period(ticket, SCHEDULE_ROWS, day_of_week=5)
    assert resolved["ok"] is True
    assert resolved["target_periods"] == ["07:00-09:00"]
    assert resolved["period_plan_no"] == "3"
    assert resolved["match_method"] == "peak_label"


def test_resolve_evening_peak_synonym():
    ticket = {"period": "傍晚", "time_range": ""}
    resolved = resolve_timing_period(ticket, SCHEDULE_ROWS, day_of_week=5)
    assert resolved["target_periods"] == ["17:00-19:00"]
    assert resolved["period_plan_no"] == "5"


def test_prepare_signal_for_ticket_switches_plan():
    from app.data.schedule_period_resolver import prepare_signal_for_ticket

    pg_raw = {
        "schedule_cfg": [
            {
                "week_day_no": 5,
                "day_plan_no": "1",
                "period_seq_no": 1,
                "start_time": "07:00:00",
                "end_time": "08:30:00",
                "period_plan_no": 18,
            }
        ],
        "plan": [
            {
                "plan_no": 2,
                "plan_name": "方案2",
                "cycle_len_sec": 143,
                "stage_no": 1,
                "stage_seq_no": 1,
                "green_sec": 23,
                "yellow_sec": 3,
                "all_red_sec": 2,
                "min_green_sec": 15,
                "max_green_sec": 60,
            },
            {
                "plan_no": 18,
                "plan_name": "方案18",
                "cycle_len_sec": 150,
                "stage_no": 1,
                "stage_seq_no": 1,
                "green_sec": 40,
                "yellow_sec": 3,
                "all_red_sec": 2,
                "min_green_sec": 20,
                "max_green_sec": 70,
            },
            {
                "plan_no": 18,
                "plan_name": "方案18",
                "cycle_len_sec": 150,
                "stage_no": 3,
                "stage_seq_no": 2,
                "green_sec": 55,
                "yellow_sec": 3,
                "all_red_sec": 2,
                "min_green_sec": 20,
                "max_green_sec": 70,
            },
        ],
        "turn_flow": [{"link_id": "L1", "turn_dir_no": 2, "step_index": 90, "turn_flow_total": 800, "lane_count": 2}],
        "turn_saturation": [],
        "signal_lane_mapping": [
            {"plan_no": 18, "stage_no": 1, "link_id": "L1", "turn_dir_no": 2},
            {"plan_no": 18, "stage_no": 3, "link_id": "L1", "turn_dir_no": 2},
        ],
        "channelization": [{"link_id": "L1", "link_role": "entrance", "dir8_code": 4}],
        "stage_motor_flow": [],
        "min_green": [],
    }
    signal = {"inter_id": "X", "plan_no": 2, "current_cycle_s": 143}
    ticket = {"period": "早高峰", "time_range": "07:30-07:50"}
    rebuilt, resolved = prepare_signal_for_ticket(signal, ticket, pg_raw, day_of_week=5)
    assert resolved["period_plan_no"] == "18"
    assert rebuilt["plan_no"] == "18"
    assert len(rebuilt.get("phase_stage_timing_list") or []) == 2
