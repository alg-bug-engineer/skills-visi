"""五类溢出机制确定性判别（不经 LLM）。"""

from app.decision.overflow_mechanism import classify_overflow_mechanism


def test_downstream_blocked_wins_first():
    out = classify_overflow_mechanism(
        downstream_state={"decision": "blocked"},
        target_queue_ratio=0.97,
        target_saturation=0.9,
        target_green_utilization=0.9,
        upstream_arrival_intense=True,
    )
    assert out["primary"] == "downstream_blocked"
    assert out["status"] in {"confirmed", "supported", "hypothesis"}


def test_unknown_downstream_is_evidence_insufficient():
    out = classify_overflow_mechanism(
        downstream_state={"decision": "unknown"},
        target_queue_ratio=0.97,
        target_saturation=0.55,
        target_green_utilization=0.27,
    )
    assert out["primary"] == "evidence_insufficient"


def test_case_a_discharge_anomaly():
    """Case A：下游 slack + 高排队 + 低绿灯利用 → discharge_anomaly。"""
    out = classify_overflow_mechanism(
        downstream_state={"decision": "slack", "confidence": 0.72},
        target_queue_ratio=0.9731,
        target_saturation=0.55,
        target_green_utilization=0.27,
        upstream_arrival_intense=False,
    )
    assert out["primary"] == "discharge_anomaly"
    assert out["status"] == "hypothesis"
    assert any("绿灯" in e or "利用" in e for e in (out.get("supporting_evidence") or []))
    missing = " ".join(out.get("missing_evidence") or [])
    assert "核验" in missing or "队列" in missing or "检测" in missing


def test_local_release_insufficient_high_util():
    out = classify_overflow_mechanism(
        downstream_state={"decision": "slack"},
        target_queue_ratio=0.95,
        target_saturation=0.88,
        target_green_utilization=0.9,
        green_end_queue_remains=True,
    )
    assert out["primary"] == "local_release_insufficient"


def test_upstream_arrival_shock_when_intense_and_not_local_or_discharge():
    out = classify_overflow_mechanism(
        downstream_state={"decision": "slack"},
        target_queue_ratio=0.95,
        target_saturation=0.7,
        target_green_utilization=0.7,
        upstream_arrival_intense=True,
    )
    assert out["primary"] == "upstream_arrival_shock"


def test_slack_must_not_classify_as_downstream_blocked():
    out = classify_overflow_mechanism(
        downstream_state={"decision": "slack"},
        target_queue_ratio=0.97,
        target_saturation=0.55,
        target_green_utilization=0.27,
    )
    assert out["primary"] != "downstream_blocked"
