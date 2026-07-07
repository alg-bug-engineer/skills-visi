import json
from pathlib import Path

from app.services.feedback_service import PlanFeedbackService


def test_accept_feedback_extended_schema(tmp_path: Path):
    feedback_path = tmp_path / "plan_feedback.jsonl"
    service = PlanFeedbackService(feedback_path)
    result = service.record_decision(
        trace_id="tr-accept",
        plan_id="arterial_coordination",
        decision="accept",
        plan_snapshot={"plan_id": "arterial_coordination"},
        diagnosis_ticket={
            "inter_id": "INT001",
            "problem_type": "排队溢出",
            "diagnosis_scope": ["目标路口", "下游承接"],
        },
        artifacts_summary={
            "cause_analysis": {"cause_analysis": {"primary_cause": "下游承接能力不足"}},
            "strategy_generation": {"strategy": {"recommended": ["上游控流+小步释放"]}},
            "data_analysis_diagnosis": {
                "overflow_verification": {"queue_ratio": 0.95, "risk_level": "high"},
                "metrics": {"saturation": 0.88, "direction": "东向西"},
            },
        },
    )
    assert result["ok"] is True
    assert result["fingerprint"]["problem_type"] == "排队溢出"
    assert result["tags"]["primary_cause"] == "下游承接能力不足"

    record = json.loads(feedback_path.read_text(encoding="utf-8").strip())
    assert record["retrieval"]["as_recommended_case"] is True
    assert record["inter_id"] == "INT001"


def test_reject_feedback_and_search_patterns(tmp_path: Path):
    feedback_path = tmp_path / "plan_feedback.jsonl"
    service = PlanFeedbackService(feedback_path)
    service.record_decision(
        trace_id="tr-reject",
        plan_id="aggressive_green",
        decision="reject",
        rejection_reason="单点加绿导致下游外溢加重",
        diagnosis_ticket={"inter_id": "INT001", "problem_type": "排队溢出"},
    )

    rejected = service.search_rejected_patterns(inter_id="INT001", problem_type="排队溢出")
    assert len(rejected) == 1
    assert rejected[0]["rejection_reason"] == "单点加绿导致下游外溢加重"

    accepted = service.search_accepted_plans(inter_id="INT001", problem_type="排队溢出")
    assert accepted == []


def test_record_decision_dedup_same_experience(tmp_path: Path):
    feedback_path = tmp_path / "plan_feedback.jsonl"
    service = PlanFeedbackService(feedback_path)
    ticket = {
        "inter_id": "INT001",
        "intersection_name": "经十路与转山西路路口",
        "problem_type": "排队溢出",
        "user_experiences": [
            {"experience_type": "cognitive", "content": "东向西排队溢出"},
        ],
    }
    kwargs = dict(
        trace_id="tr-1",
        plan_id="arterial_coordination",
        decision="accept",
        plan_snapshot={"plan_id": "arterial_coordination", "cycle_s": 42},
        diagnosis_ticket=ticket,
    )
    first = service.record_decision(**kwargs)
    # 不同 trace_id，但方案经验/诊断工单/用户经验一致 → 视为重复
    second = service.record_decision(**{**kwargs, "trace_id": "tr-2"})

    assert first["duplicate"] is False
    assert second["duplicate"] is True
    lines = feedback_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_record_decision_dedup_survives_restart(tmp_path: Path):
    feedback_path = tmp_path / "plan_feedback.jsonl"
    ticket = {"inter_id": "INT002", "problem_type": "排队溢出"}
    kwargs = dict(
        trace_id="tr-1",
        plan_id="p1",
        decision="accept",
        plan_snapshot={"plan_id": "p1"},
        diagnosis_ticket=ticket,
    )
    PlanFeedbackService(feedback_path).record_decision(**kwargs)
    # 新实例从文件读既有指纹去重
    again = PlanFeedbackService(feedback_path).record_decision(**{**kwargs, "trace_id": "tr-2"})
    assert again["duplicate"] is True
    lines = feedback_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
