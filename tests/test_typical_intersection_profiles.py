"""典型路口取数配置与策略解析测试。"""

from __future__ import annotations

import json
from pathlib import Path

from app.data.pg_adapters import metrics_for_diagnosis
from app.data.typical_intersection_profiles import (
    clear_typical_profile_cache,
    metric_options_from_profile,
    resolve_typical_profile,
)


def test_resolve_typical_profiles_for_configured_movements():
    clear_typical_profile_cache()
    west_through = resolve_typical_profile(
        {
            "inter_id": "011wwe28fty00001",
            "direction": "西进口",
            "movement": "直行",
        }
    )
    assert west_through is not None
    assert west_through["id"] == "point_kunshun_aotixi_west_through"
    assert west_through["target_queue_field"] == "queue_len_max"

    west_left = resolve_typical_profile(
        {
            "inter_id": "011wwe28fty00001",
            "direction": "西向东",
            "movement": "左转",
        }
    )
    assert west_left is not None
    assert west_left["id"] == "point_kunshun_aotixi_west_left"

    # Case E：会展西直（与 frontend manifest / live fixture 一致）
    huizhan_west = resolve_typical_profile(
        {
            "inter_id": "011wwe29jbf00001",
            "direction": "西向东",
            "movement": "直行",
        }
    )
    assert huizhan_west is not None
    assert huizhan_west["id"] == "point_huizhan_aotizhong_west_through"
    assert huizhan_west["target_selection"] == "cross_week_peak"
    assert huizhan_west["downstream_selection"] == "cross_week_mean"

    # 旧东直配置不得再命中，避免与 Case E 西直演示冲突
    assert (
        resolve_typical_profile(
            {
                "inter_id": "011wwe29jbf00001",
                "direction": "东进口",
                "movement": "直行",
            }
        )
        is None
    )

    line = resolve_typical_profile(
        {
            "inter_id": "011wwe22xn400001",
            "direction": "东进口",
            "movement": "直行",
        }
    )
    assert line is not None
    assert line["opt_type"] == "TYPE2_LINE"
    assert line["downstream_peak_disclose_field"] == "queue_len_max"


def test_case_a_keeps_project_fixed_logic():
    clear_typical_profile_cache()
    case_a = resolve_typical_profile(
        {
            "inter_id": "011wwe28f7c00001",
            "intersection_name": "解放东路与齐川路路口",
            "direction": "北进口",
            "movement": "直行",
        }
    )
    assert case_a is None
    opts = metric_options_from_profile(case_a)
    assert opts["use_typical_policy"] is False
    assert opts["target_queue_field"] == "queue_len_avg"
    assert opts["target_selection"] == "cross_week_peak"
    assert opts["downstream_selection"] == "cross_week_mean"


def test_unconfigured_intersection_uses_fixed_defaults():
    clear_typical_profile_cache()
    opts = metric_options_from_profile(
        resolve_typical_profile(
            {
                "inter_id": "unknown_inter",
                "direction": "东进口",
                "movement": "直行",
            }
        )
    )
    assert opts["use_typical_policy"] is False
    assert opts["downstream_approach_queue_avg"] is False
    assert opts["target_selection"] == "cross_week_peak"
    assert opts["downstream_selection"] == "cross_week_mean"


def test_metric_options_expose_selection_policy():
    clear_typical_profile_cache()
    opts = metric_options_from_profile(
        resolve_typical_profile(
            {
                "inter_id": "011wwe293wd00001",
                "direction": "北进口",
                "movement": "直行",
            }
        )
    )
    assert opts["use_typical_policy"] is True
    assert opts["typical_profile_id"] == "line_caoshanling_north_through"
    assert opts["target_selection"] == "cross_week_peak"
    assert opts["downstream_selection"] == "cross_week_mean"
    assert opts["target_queue_field"] == "queue_len_max"


def test_metrics_for_diagnosis_respects_queue_len_max_policy():
    """典型策略注入 queue_len_max 后，诊断队列取该字段峰值。"""
    pg_metrics = {
        "metric_selection_policy": "cross_week_movement_peak",
        "target_queue_field": "queue_len_max",
        "selected_day_of_week": 3,
        "selected_movement_queue_peak_m": 108.0,
        "typical_profile_id": "point_kunshun_aotixi_west_through",
        "turn_perf_detail": [
            {
                "f_dir_8": 6,
                "turn_dir_no": 2,
                "queue_len_avg": 54.8,
                "queue_len_max": 108.0,
                "step_index": 210,
            },
            {
                "f_dir_8": 6,
                "turn_dir_no": 2,
                "queue_len_avg": 40.0,
                "queue_len_max": 90.0,
                "step_index": 211,
            },
        ],
        "turn_saturation_detail": [
            {"dir8_code": 6, "turn_dir_no": 2, "turn_saturation": 1.28},
        ],
        "adjacent_inter_spacing_detail": [
            {"dir8_code": 6, "spacing_m": 112.76, "version_id": "20260501"},
        ],
    }
    scope = {
        "adjacent_inter_spacing_detail": pg_metrics["adjacent_inter_spacing_detail"],
    }
    out = metrics_for_diagnosis(
        pg_metrics,
        {"direction": "西进口", "movement": "直行"},
        scope=scope,
    )
    assert out["queue_length_m"] == 108.0
    assert out["storage_length_m"] == 112.76
    assert abs(out["queue_length_m"] / out["storage_length_m"] - 0.9578) < 0.001
    assert out["target_queue_field"] == "queue_len_max"
    assert out["typical_profile_id"] == "point_kunshun_aotixi_west_through"


def test_typical_intersections_json_lists_expected_ids():
    path = Path(__file__).resolve().parents[1] / "data" / "typical_intersections.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    ids = {p["id"] for p in catalog["profiles"]}
    assert "point_kunshun_aotixi_west_through" in ids
    assert "point_kunshun_aotixi_west_left" in ids
    assert "point_huizhan_aotizhong_west_through" in ids
    assert "point_huizhan_aotizhong_east_through" not in ids
    assert "line_aotizhong_jingshi_east_through" not in ids
    assert "line_caoshanling_north_through" in ids
    assert "line_caoshanling_south_left" in ids
    assert "line_lvyou_zhuanshanxi_east_through" in ids
    # Case A 明确不写入覆盖 profile
    assert "case_a" not in "".join(ids).lower()
    assert "28f7c00001" not in json.dumps(catalog["profiles"])
    # Case E 筛查锚点必须含下游排队
    by_id = {p["id"]: p for p in catalog["profiles"]}
    anchor = by_id["point_huizhan_aotizhong_west_through"]["metrics"]["screening_anchor"]
    assert float(anchor["queue_ratio"]) >= 0.8
    assert anchor.get("downstream_queue_length_m") is not None


def test_frontend_manifest_metric_profiles_align_with_catalog():
    """演示 case 声明的 metric_profile_id 必须在取数配置中可解析。"""
    root = Path(__file__).resolve().parents[1]
    catalog = json.loads((root / "data" / "typical_intersections.json").read_text(encoding="utf-8"))
    profile_ids = {p["id"] for p in catalog["profiles"]}
    manifest = json.loads(
        (root / "frontend" / "src" / "mock" / "cases" / "manifest.json").read_text(encoding="utf-8")
    )
    declared = {
        c["id"]: c["metric_profile_id"]
        for c in manifest["cases"]
        if c.get("metric_profile_id")
    }
    assert declared["case_c"] == "line_caoshanling_north_through"
    assert "case_d" not in declared
    assert declared["case_e"] == "point_huizhan_aotizhong_west_through"
    assert declared["case_f"] == "line_lvyou_zhuanshanxi_east_through"
    for case_id, profile_id in declared.items():
        assert profile_id in profile_ids, f"{case_id} → {profile_id} 不在 typical_intersections.json"


def test_screening_anchor_requires_downstream_queue():
    """筛查锚点缺下游排队时必须拒绝，防止无排队 Case 混入典型清单。"""
    from app.data.typical_intersection_profiles import (
        normalize_screening_anchor,
        validate_typical_profiles,
    )

    assert (
        normalize_screening_anchor(
            {
                "queue_length_m": 150.4,
                "storage_length_m": 116.2,
                "queue_ratio": 1.2943,
                "case_id": "no-down-queue",
            }
        )
        is None
    )
    ok = normalize_screening_anchor(
        {
            "queue_length_m": 210.4,
            "storage_length_m": 194.1,
            "queue_ratio": 1.084,
            "downstream_queue_length_m": 4.6,
            "downstream_storage_length_m": 396.5,
            "downstream_queue_ratio": 0.012,
        }
    )
    assert ok is not None
    assert ok["downstream_queue_length_m"] == 4.6
    assert validate_typical_profiles() == []


def test_screening_anchor_overrides_window_metrics_for_overflow_cases():
    """筛查尖峰溢流优先于晚高峰周型剖面，避免 healthy 误判。"""
    import importlib.util
    from pathlib import Path

    from app.data.typical_intersection_profiles import apply_screening_anchor_to_metrics

    root = Path(__file__).resolve().parents[1]
    path = root / "skills" / "data-analysis-diagnosis" / "scripts" / "analyze_overflow.py"
    spec = importlib.util.spec_from_file_location("analyze_overflow_screening", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)

    clear_typical_profile_cache()
    case_e = resolve_typical_profile(
        {
            "inter_id": "011wwe29jbf00001",
            "direction": "西进口",
            "movement": "直行",
        }
    )
    assert case_e is not None
    assert case_e["id"] == "point_huizhan_aotizhong_west_through"
    opts = metric_options_from_profile(case_e)
    anchor = opts["screening_anchor"]
    assert anchor is not None
    assert float(anchor["queue_ratio"]) >= 0.8
    assert anchor.get("downstream_queue_length_m") is not None

    window_metrics = {
        "queue_length_m": 88.0,
        "storage_length_m": 194.14,
        "saturation": None,
        "saturation_rate": None,
        "volume_vph": 800.0,
        "capacity_vph": 1200.0,
        "green_utilization": 0.5,
    }
    merged = apply_screening_anchor_to_metrics(window_metrics, anchor)
    assert merged["queue_length_m"] == anchor["queue_length_m"]
    assert merged["storage_length_m"] == anchor["storage_length_m"]
    assert merged["metric_selection_policy"] == "screening_event_anchor"

    out = mod.analyze_overflow(
        merged,
        {
            "intersection_name": "会展路与奥体中路路口",
            "direction": "西进口",
            "movement": "直行",
        },
    )
    assert out["healthy"] is False
    assert out["problem_confirmed"] is True
    assert out["overflow_verification"]["risk_level"] == "high"
    assert abs(float(out["metrics"]["queue_ratio"]) - float(anchor["queue_ratio"])) < 0.01


def test_healthy_requires_known_saturation():
    """饱和度缺失时不得因 (sat or 0) 被判健康。"""
    import importlib.util
    from pathlib import Path

    from app.metrics.traffic import assess_overflow_risk

    root = Path(__file__).resolve().parents[1]
    path = root / "skills" / "data-analysis-diagnosis" / "scripts" / "analyze_overflow.py"
    spec = importlib.util.spec_from_file_location("analyze_overflow_healthy", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)

    out = mod.analyze_overflow(
        {
            "queue_length_m": 35.6,
            "storage_length_m": 116.18,
            "saturation": None,
            "volume_vph": 0,
            "capacity_vph": 0,
            "green_utilization": 0.4,
        },
        {
            "intersection_name": "奥体中路与经十路路口",
            "direction": "东进口",
            "movement": "直行",
        },
    )
    assert out["overflow_verification"]["risk_level"] == "low"
    assert out["healthy"] is False
    assert assess_overflow_risk(0.3)["risk_level"] == "low"


def test_load_movement_metrics_respects_selection_policy(monkeypatch):
    """target/downstream selection 必须真正分支到 peak/mean 加载器。"""
    from app.data import pg_adapters

    calls: list[str] = []

    def _peak(**kwargs):
        calls.append(f"peak:{kwargs.get('queue_field')}")
        return {"ok": True, "via": "peak", **kwargs}

    def _mean(**kwargs):
        calls.append(f"mean:{kwargs.get('queue_field')}:{kwargs.get('peak_disclose_field')}")
        return {"ok": True, "via": "mean", **kwargs}

    monkeypatch.setattr(pg_adapters, "load_cross_week_peak_movement_metrics", _peak)
    monkeypatch.setattr(pg_adapters, "load_cross_week_mean_movement_metrics", _mean)

    peak_out = pg_adapters.load_movement_metrics_by_selection(
        inter_id="x",
        direction="西进口",
        movement="直行",
        time_range="17:00-19:00",
        selection="cross_week_peak",
        queue_field="queue_len_max",
    )
    mean_out = pg_adapters.load_movement_metrics_by_selection(
        inter_id="x",
        direction="西进口",
        movement="直行",
        time_range="17:00-19:00",
        selection="cross_week_mean",
        queue_field="queue_len_avg",
        peak_disclose_field="queue_len_max",
    )
    assert peak_out["via"] == "peak"
    assert mean_out["via"] == "mean"
    assert calls == ["peak:queue_len_max", "mean:queue_len_avg:queue_len_max"]
