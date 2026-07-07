import importlib.util
from pathlib import Path

import pytest

from app.trace.downstream_trace import assess_downstream_capacity
from app.trace.intersection_profile import build_intersection_profile
from app.trace.topology import exit_dir8_for_turn, resolve_dir8_turn


def _load_skill_script(name: str):
    path = (
        Path(__file__).resolve().parent.parent
        / "skills"
        / "data-analysis-diagnosis"
        / "scripts"
        / name
    )
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_analyze = _load_skill_script("analyze_overflow.py")
_demo_topo = _load_skill_script("demo_topology.py")
analyze_overflow = _analyze.analyze_overflow
build_demo_topology = _demo_topo.build_demo_topology


def test_exit_dir8_for_turn():
    assert exit_dir8_for_turn(2, 2) == 6
    assert exit_dir8_for_turn(6, 1) == 0


def test_resolve_dir8_turn():
    assert resolve_dir8_turn("东向西", "直行") == (2, 2)


def test_downstream_capacity_blocked():
    result = assess_downstream_capacity(saturation=0.92, queue_ratio=0.88)
    assert result["blocked"] is True
    assert result["can_release"] is False


def test_build_intersection_profile():
    profile = build_intersection_profile(
        {
            "inter_id": "t1",
            "inter_name": "测试路口",
            "queue_length_m": 180,
            "storage_length_m": 200,
            "volume_vph": 1600,
            "capacity_vph": 1700,
            "green_utilization": 0.9,
        }
    )
    assert profile["metrics"]["queue_storage_ratio_max"] == pytest.approx(0.9)
    assert profile["remaining_storage_m"] == 20


def test_analyze_overflow_with_topology():
    ticket = {
        "intersection_name": "文化西路与舜华路交叉口",
        "direction": "东向西",
        "movement": "直行",
    }
    topology = build_demo_topology(ticket)
    result = analyze_overflow(
        {
            "queue_length_m": 185,
            "storage_length_m": 200,
            "volume_vph": 1680,
            "capacity_vph": 1750,
            "green_utilization": 0.88,
            "stop_count": 2.4,
            "avg_delay_s": 78,
            "time_series_trend": "持续上升",
        },
        ticket,
        topology=topology,
    )

    assert result["downstream_trace"]["available"] is True
    assert result["flow_trace"]["available"] is True
    assert len(result["downstream_trace"]["adjacent_intersections"]) == 1
    downstream = result["downstream_trace"]["adjacent_intersections"][0]
    assert downstream["inter_name"] == "舜华路与工业南路交叉口"
    assert "metrics" in downstream
    assert "by_turn" in downstream
    assert result["flow_trace"]["entry_traces"][0]["upstream_inter_name"]
    assert result["arterial_analysis"]["need_upstream_metering"] is True
    assert result["downstream_diagnosis"]["release_answer"] == "下游接不住"
    assert result["downstream_diagnosis"]["scenario"] == "high_demand_downstream_blocked"
    assert result["map_scenes"]["downstream_trace_map"]["available"] is True
    assert result["map_scenes"]["arterial_analysis"]["entry_traces"]
