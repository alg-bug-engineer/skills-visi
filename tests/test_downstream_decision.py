"""下游承接状态唯一真源：blocked | slack | unknown。"""

from app.trace.downstream_decision import decide_downstream_state


def test_unknown_when_queue_and_saturation_missing():
    out = decide_downstream_state(saturation=None, queue_ratio=None)
    assert out["decision"] == "unknown"
    assert out["blocked"] is False
    assert out["unknown"] is True
    assert out["can_release"] is None
    assert "downstream_queue_and_saturation_unavailable" in out["reasons"]


def test_blocked_when_queue_ratio_high():
    out = decide_downstream_state(saturation=0.4, queue_ratio=0.91)
    assert out["decision"] == "blocked"
    assert out["blocked"] is True
    assert out["unknown"] is False
    assert out["can_release"] is False


def test_blocked_when_saturation_high():
    out = decide_downstream_state(saturation=0.86, queue_ratio=0.2)
    assert out["decision"] == "blocked"
    assert out["blocked"] is True


def test_slack_case_a_downstream():
    """Case A：下游排队约 0.01、饱和度缺失 → slack，不得判 blocked。"""
    out = decide_downstream_state(
        saturation=None,
        queue_ratio=0.01,
        remaining_storage_m=115.0,
        direct_downstream_inter_id="011wwe28f5f00001",
        direct_downstream_inter_name="永绥路与齐音路路口",
        missing_metrics=["saturation", "green_utilization"],
    )
    assert out["decision"] == "slack"
    assert out["blocked"] is False
    assert out["unknown"] is False
    assert out["can_release"] is True
    assert out["direct_downstream_inter_id"] == "011wwe28f5f00001"
    assert out["queue_ratio"] == 0.01
    assert out["remaining_storage_m"] == 115.0
    assert "saturation" in out["missing_metrics"]
    assert out["confidence"] < 1.0  # 缺指标时不得装成绝对确定


def test_slack_must_not_use_接不住_language_tags():
    out = decide_downstream_state(saturation=0.3, queue_ratio=0.2)
    assert out["decision"] == "slack"
    assert out["release_guard"] == "downstream_has_slack"
    assert "接不住" not in "".join(out.get("reasons") or [])
