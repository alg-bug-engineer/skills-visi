"""动作包：三类对外方案，禁止演示性文案。"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load():
    path = (
        Path(__file__).resolve().parents[1]
        / "skills"
        / "strategy-generation"
        / "scripts"
        / "build_action_package.py"
    )
    spec = importlib.util.spec_from_file_location("build_action_package", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_verify_then_adjust_emits_three_schemes_with_phase_deltas():
    mod = _load()
    package = mod.build_action_package(
        diagnosis={
            "overflow_mechanism": {"primary": "discharge_anomaly"},
            "downstream_state": {
                "decision": "slack",
                "direct_downstream_inter_name": "永绥路与齐音路路口",
            },
            "scenario_report": {
                "issues": [
                    {
                        "item_id": "adjacent_spacing",
                        "summary": "道路等级 城市次干道/城市主干道",
                    }
                ]
            },
        },
        strategy={
            "decision": {"decision_mode": "verify_then_adjust"},
            "strategy": {
                "target_intersection": {
                    "inter_name": "解放东路与齐川路路口",
                    "direction": "北向南",
                    "movement": "直行",
                }
            },
        },
        ticket={
            "intersection_name": "解放东路与齐川路路口",
            "direction": "北向南",
            "movement": "直行",
        },
    )
    assert package["available"] is True
    schemes = package["schemes"]
    assert schemes["signal_control"]
    assert any("+5s" in (a.get("action") or "") for a in schemes["signal_control"])
    assert any("−5s" in (a.get("action") or "") or "-5s" in (a.get("action") or "") for a in schemes["signal_control"])
    assert schemes["organization"]
    assert schemes["management"]
    # 禁止演示性文案残留
    blob = str(package)
    assert "分析亮点" not in blob
    assert "道路等级画像" not in blob


def test_enrich_signal_control_uses_real_phase_names():
    mod = _load()
    package = mod.build_action_package(
        diagnosis={"overflow_mechanism": {"primary": "discharge_anomaly"}},
        strategy={"decision": {"decision_mode": "verify_then_adjust"}},
        ticket={"intersection_name": "测试路口", "direction": "北向南", "movement": "直行"},
    )
    enriched = mod.enrich_signal_control_from_timing(
        package,
        {
            "cycle_delta_s": 0,
            "phase_stage_timing_list": [
                {
                    "phase_stage_id": "7",
                    "phase_stage_name": "北直",
                    "green_delta_s": 5,
                },
                {
                    "phase_stage_id": "1",
                    "phase_stage_name": "西直、东直",
                    "green_delta_s": -5,
                },
            ],
        },
    )
    actions = [a["action"] for a in enriched["schemes"]["signal_control"] if a.get("kind") == "timing"]
    assert any("阶段7" in a and "+5s" in a for a in actions)
    assert any("阶段1" in a and "-5s" in a for a in actions)


def test_evidence_insufficient_keeps_current_timing_without_plus_five_preview():
    mod = _load()
    package = mod.build_action_package(
        diagnosis={"overflow_mechanism": {"primary": "evidence_insufficient"}},
        strategy={"decision": {"decision_mode": "verification_required"}},
        ticket={"intersection_name": "解放东路与奥体中路路口", "movement": "直行"},
    )

    actions = [row.get("action") or "" for row in package["schemes"]["signal_control"]]
    assert any("保持现状配时" in action for action in actions)
    assert not any("+5s" in action or "-5s" in action or "−5s" in action for action in actions)
    assert not any("试验 5 周期" in action for action in actions)


def test_small_road_organization_and_management():
    mod = _load()
    package = mod.build_action_package(
        diagnosis={
            "overflow_mechanism": {"primary": "discharge_anomaly"},
            "scenario_report": {
                "issues": [
                    {"item_id": "adjacent_spacing", "summary": "道路等级 小路/城市普通道路"}
                ]
            },
        },
        strategy={"decision": {"decision_mode": "verify_then_adjust"}},
        ticket={"intersection_name": "测试小路路口", "direction": "东向西", "movement": "直行"},
    )
    assert package["road_profile"]["is_small_road_context"] is True
    assert any("可变导向" in (a.get("action") or "") for a in package["schemes"]["organization"])
    assert any("违停" in (a.get("action") or "") for a in package["schemes"]["management"])
