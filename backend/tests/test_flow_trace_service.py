"""Tests for upstream flow-trace analysis (one-hop lock + source-pattern classify).

TC: docs/plans/2026-06-29-流量溯源接入问题诊断-开发计划.md §5.1
"""

import asyncio

from intersection_agent.models.domain import NluResult, TimePeriod
from intersection_agent.services.flow_trace_service import (
    FlowTraceService,
    build_entry_traces,
    build_problem_turn_trace,
    classify_sources,
    governance_hints_from_entries,
    governance_hints_from_trace,
    lock_one_hop,
    movement_label,
    period_type_from_label,
    select_problem_entries,
    select_problem_turns,
)


def _row(f_dir8, turn, cor_id, cor_dir8, cor_turn, cov, name="路口X"):
    return {
        "f_dir8_no": f_dir8, "turn_dir_no": turn,
        "cor_inter_id": cor_id, "cor_f_dir8_no": cor_dir8, "cor_turn_dir_no": cor_turn,
        "flow_share_ratio": cov, "cor_inter_name": name,
    }


def test_movement_and_period_labels():
    assert movement_label(0, 2) == "北进口直行"
    assert movement_label(2, 1) == "东进口左转"
    assert period_type_from_label("晚高峰") == "EVENING_PEAK"
    assert period_type_from_label("早高峰") == "MORNING_PEAK"
    assert period_type_from_label(None) == "OFF_PEAK"


def test_one_hop_lock_keeps_max_per_bearing():
    """TC one_hop_lock：同方位 90/77/48 只保留 90。"""
    rows = [
        _row(0, 2, "A1", 0, 2, 90.5),
        _row(0, 2, "A2", 0, 2, 76.7),
        _row(0, 2, "A3", 0, 2, 47.7),
        _row(0, 2, "B1", 6, 2, 32.0),
    ]
    grouped = lock_one_hop(rows)
    nodes = grouped[(0, 2)]
    # 两个方位(0,2)与(6,2)各保留一跳
    assert len(nodes) == 2
    assert nodes[0]["coverage"] == 90.5
    assert nodes[0]["cor_inter_id"] == "A1"


def test_classify_single_corridor():
    """TC single_corridor：top1 高且显著领先。"""
    nodes = [{"coverage": 90.0}, {"coverage": 30.0}]
    assert classify_sources(nodes, coverage_high=70, gap_significant=25) == "single_corridor"


def test_classify_multi_corridor():
    """TC multi_corridor：两方位均强、差距小。"""
    nodes = [{"coverage": 100.0}, {"coverage": 80.0}]
    assert classify_sources(nodes, coverage_high=70, gap_significant=25) == "multi_corridor"


def test_classify_local():
    """TC local：均低于阈值。"""
    nodes = [{"coverage": 50.0}, {"coverage": 30.0}]
    assert classify_sources(nodes, coverage_high=70, gap_significant=25) == "local"


def test_build_entry_traces_normalizes_100_vehicles():
    """进口道一跳：上一路口左/直/右归一化为 100 辆模型。"""
    rows = [
        _row(2, 1, "U1", 3, 2, 81.8, name="岔口"),
        _row(2, 2, "U1", 3, 2, 18.2, name="岔口"),
        _row(2, 1, "U2", 2, 2, 40.0, name="二跳"),
    ]
    grouped = lock_one_hop(rows)
    by_turn = [
        {"dir8_code": 2, "turn_dir_no": 1, "turn_saturation": 1.73},
        {"dir8_code": 2, "turn_dir_no": 2, "turn_saturation": 0.5},
    ]
    entries = build_entry_traces(grouped, [2], by_turn)
    assert len(entries) == 1
    e = entries[0]
    assert e["entry"] == "东进口"
    assert e["upstream_inter_name"] == "岔口"
    assert e["vehicles_base"] == 100
    total_veh = sum(m["vehicles_of_100"] for m in e["upstream_movements"])
    assert 98 <= total_veh <= 102
    assert "100辆" in e["narrative"]
    hints = governance_hints_from_entries(entries)
    assert hints and hints[0]["coverage"] >= 50


def test_select_problem_entries_by_entry_saturation():
    by_turn = [
        {"dir8_code": 2, "turn_saturation": 1.2},
        {"dir8_code": 4, "turn_saturation": 0.5},
    ]
    assert select_problem_entries(by_turn, trigger_saturation=0.9) == [2]


def test_build_trace_and_hints():
    rows = [
        _row(2, 1, "U1", 3, 2, 81.8, name="岔口"),
        _row(2, 1, "U2", 2, 2, 40.0, name="二跳"),
    ]
    grouped = lock_one_hop(rows)
    problem_turns = [{"dir8_code": 2, "turn_dir_no": 1, "turn_saturation": 1.73}]
    turns = build_problem_turn_trace(
        grouped, problem_turns, coverage_high=70, gap_significant=25, top_sources=3
    )
    assert len(turns) == 1
    t = turns[0]
    assert t["entry"] == "东进口" and t["turn"] == "左转"
    assert t["source_pattern"] == "single_corridor"
    assert t["dominant_feed"]["inter_name"] == "岔口"
    assert t["dominant_feed"]["path_coverage"] == 81.8

    hints = governance_hints_from_trace(turns)
    assert hints[0]["type"] == "upstream_coordination"
    assert hints[0]["inter_name"] == "岔口"


def test_select_problem_turns_filters_by_saturation():
    by_turn = [
        {"label": "东左转", "dir8_code": 2, "turn_dir_no": 1, "turn_saturation": 1.2},
        {"label": "南右转", "dir8_code": 4, "turn_dir_no": 3, "turn_saturation": 0.5},
        {"label": "缺编码", "turn_saturation": 1.0},
    ]
    res = select_problem_turns(by_turn, None, trigger_saturation=0.9)
    assert len(res) == 1
    assert res[0]["dir8_code"] == 2


def test_service_not_triggered_without_high_saturation():
    svc = FlowTraceService()
    nlu = NluResult(
        intersection="x", time_period=TimePeriod(start="16:00", end="18:00", label="晚高峰"),
        directions=["东西向"], problem_type="congestion",
    )
    payload = {"granularity": {"by_turn": [
        {"label": "东左转", "dir8_code": 2, "turn_dir_no": 1, "turn_saturation": 0.5},
    ]}}
    res = asyncio.run(svc.build("x", nlu, data_payload=payload))
    assert res["available"] is False
    assert res["reason"] == "not_triggered"


def test_service_mock_db_builds_trace(monkeypatch):
    """MOCK_DB 下应产出可用 flow_trace（empty 用例的反面）。"""
    from intersection_agent.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "mock_db", True, raising=False)
    svc = FlowTraceService(settings=settings)
    nlu = NluResult(
        intersection="x", time_period=TimePeriod(start="16:00", end="18:00", label="晚高峰"),
        directions=["东西向"], problem_type="congestion",
    )
    payload = {"granularity": {"by_turn": [
        {"label": "东左转", "dir8_code": 2, "turn_dir_no": 1, "turn_saturation": 1.2},
    ]}}
    res = asyncio.run(svc.build("x", nlu, data_payload=payload))
    assert res["available"] is True
    assert res["entry_traces"]
    assert res["problem_turns"]
    assert res["problem_turns"][0]["source_pattern"] == "single_corridor"
