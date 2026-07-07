import json
from pathlib import Path

import pytest

from app.config import PROJECT_ROOT, Settings
from app.llm.qwen import QwenClient
from app.runtime.skill_loader import load_skill_from_dir
from app.runtime.skill_types import SkillContext
from app.services.experience_library import ExperienceLibraryService
from app.services.feedback_service import PlanFeedbackService


@pytest.mark.asyncio
async def test_plan_generation_includes_experience_and_feedback_refs(tmp_path: Path, overflow_fixtures):
    metrics, topology = overflow_fixtures
    exp_path = tmp_path / "user_experience.jsonl"
    feedback_path = tmp_path / "plan_feedback.jsonl"

    exp_path.write_text(
        json.dumps(
            {
                "record_id": "ue_sol",
                "trace_id": "tr-s",
                "experience_type": "solution",
                "content": "应该增加绿灯时间",
                "tags": {
                    "intersection_name": "文化西路与舜华路交叉口",
                    "strategy_action": "加绿",
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    feedback = PlanFeedbackService(feedback_path)
    feedback.record_decision(
        trace_id="tr-accepted",
        plan_id="aggressive_green",
        decision="reject",
        rejection_reason="单点加绿风险过高",
        diagnosis_ticket={
            "inter_id": topology.get("target_inter_id"),
            "intersection_name": "文化西路与舜华路交叉口",
            "problem_type": "排队溢出",
        },
    )
    feedback.record_decision(
        trace_id="tr-accepted-2",
        plan_id="arterial_coordination",
        decision="accept",
        diagnosis_ticket={
            "inter_id": topology.get("target_inter_id"),
            "intersection_name": "文化西路与舜华路交叉口",
            "problem_type": "排队溢出",
        },
        artifacts_summary={
            "data_analysis_diagnosis": {"metrics": metrics, "topology": topology},
        },
    )

    plan_skill = load_skill_from_dir(PROJECT_ROOT / "skills" / "plan-generation")
    context = SkillContext(
        trace_id="plan-exp-001",
        user_input="test",
        task={
            "diagnosis_ticket": {
                "inter_id": topology.get("target_inter_id"),
                "intersection_name": "文化西路与舜华路交叉口",
                "problem_type": "排队溢出",
                "direction": "东向西",
            },
            "topology": topology,
            "signal_plan": json.loads(
                (PROJECT_ROOT / "tests" / "fixtures" / "signal_plan_demo_wenhua_shunhua.json").read_text(
                    encoding="utf-8"
                )
            ),
        },
    )
    context.artifacts["strategy_generation"] = {
        "strategy_package": "arterial_coordination",
        "strategy": {"recommended": ["上游控流+小步释放"]},
    }
    context.artifacts["data_analysis_diagnosis"] = {
        "metrics": metrics,
        "topology": topology,
        "overflow_verification": {"risk_level": "high", "queue_ratio": 0.95},
    }

    result = await plan_skill.run(
        context,
        llm=QwenClient(Settings(llm_mock=True, allow_demo_fallback=True)),
        experience_library=ExperienceLibraryService(exp_path),
        feedback_service=feedback,
        settings=Settings(llm_mock=True, allow_demo_fallback=True),
    )
    assert result.success is True
    assert len(result.output["user_solution_refs"]) >= 1
    assert len(result.output["rejected_plan_avoidance"]) >= 1
    if result.output.get("accepted_plan_refs"):
        assert result.output["accepted_plan_refs"][0]["trace_id"]
