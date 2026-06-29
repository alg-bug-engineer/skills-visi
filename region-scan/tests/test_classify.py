"""Task 3.1 / 3.2 — problem_band 分层与 pilot_score 试点评分。"""

from region_scan.classify import classify_problem_band, pilot_score

THRESHOLDS = {"saturation": {"oversaturation": 0.90, "high": 0.80}}


def _diag(**over):
    base = {
        "has_data": True,
        "metrics": {"saturation_max": 0.7, "unbalance_index": 0.2, "green_utilization": 0.6},
        "top_issues": [],
        "severity": "none",
        "control_improvement_ceiling": "medium",
        "data_quality_tags": [],
    }
    base.update(over)
    return base


def test_oversaturated_is_engineering():
    diag = _diag(
        metrics={"saturation_max": 1.05, "unbalance_index": 0.2, "green_utilization": 0.5},
        top_issues=["饱和度"],
        severity="high",
        control_improvement_ceiling="low",
    )
    assert classify_problem_band(diag, THRESHOLDS) == "工程可解"


def test_high_imbalance_not_saturated_is_timing():
    diag = _diag(
        metrics={"saturation_max": 0.75, "unbalance_index": 0.45, "green_utilization": 0.5},
        top_issues=["失衡", "绿灯空放"],
        severity="medium",
        control_improvement_ceiling="high",
    )
    assert classify_problem_band(diag, THRESHOLDS) == "配时可解"


def test_smooth_is_no_problem():
    diag = _diag(
        metrics={"saturation_max": 0.5, "unbalance_index": 0.1, "green_utilization": 0.7},
        top_issues=[],
        severity="none",
        control_improvement_ceiling="medium",
    )
    assert classify_problem_band(diag, THRESHOLDS) == "无明显问题"


def test_no_data_is_insufficient():
    diag = _diag(has_data=False)
    assert classify_problem_band(diag, THRESHOLDS) == "数据不足"


# ---- Task 3.2 pilot_score ----


def test_pilot_score_only_for_timing_band():
    timing = _diag(
        metrics={"saturation_max": 0.75, "unbalance_index": 0.45, "green_utilization": 0.5},
        top_issues=["失衡"],
        severity="medium",
        control_improvement_ceiling="high",
    )
    assert pilot_score(timing, "配时可解") is not None and pilot_score(timing, "配时可解") > 0
    # 其余分层不计分
    assert pilot_score(timing, "工程可解") is None
    assert pilot_score(timing, "无明显问题") is None
    assert pilot_score(timing, "数据不足") is None


def test_pilot_score_monotonic_in_severity_and_ceiling():
    low = _diag(top_issues=["失衡"], severity="low", control_improvement_ceiling="medium")
    mid = _diag(top_issues=["失衡"], severity="medium", control_improvement_ceiling="high")
    high = _diag(top_issues=["失衡"], severity="high", control_improvement_ceiling="high")
    s_low = pilot_score(low, "配时可解")
    s_mid = pilot_score(mid, "配时可解")
    s_high = pilot_score(high, "配时可解")
    assert s_low < s_mid < s_high


def test_pilot_score_drops_with_data_quality_tags():
    clean = _diag(top_issues=["失衡"], severity="high", control_improvement_ceiling="high")
    noisy = _diag(
        top_issues=["失衡"],
        severity="high",
        control_improvement_ceiling="high",
        data_quality_tags=["missing_dws_coverage"],
    )
    assert pilot_score(noisy, "配时可解") < pilot_score(clean, "配时可解")
