import json
from pathlib import Path

import pytest

from app.config import Settings
from app.data.intersection_registry import enrich_ticket, resolve_intersection
from app.runtime.skill_loader import load_skill_from_dir
from app.runtime.skill_types import SkillContext

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def signal_plan() -> dict:
    return json.loads((FIXTURES / "signal_plan_demo_wenhua_shunhua.json").read_text(encoding="utf-8"))


def test_resolve_intersection_by_name():
    record = resolve_intersection("文化西路与舜华路交叉口")
    assert record is not None
    assert record["inter_id"] == "demo_wenhua_shunhua"
    assert record["lng"] == pytest.approx(117.1208)


def test_enrich_ticket_adds_inter_id():
    ticket = enrich_ticket({"intersection_name": "文化西路与舜华路交叉口"})
    assert ticket["inter_id"] == "demo_wenhua_shunhua"
    assert "lng" in ticket


@pytest.mark.asyncio
async def test_intent_outputs_spatial_scene(script_user_input):
    skill = load_skill_from_dir(PROJECT_ROOT / "skills" / "intent-understanding")
    from app.llm.qwen import QwenClient

    context = SkillContext(trace_id="intent-scene", user_input=script_user_input)
    result = await skill.run(context, llm=QwenClient(Settings(llm_mock=True)))
    assert result.success is True
    scene = result.output["spatial_scene"]
    assert scene["available"] is True
    assert scene["target"]["inter_id"] == "demo_wenhua_shunhua"
    assert len(scene["recognition_steps"]) == 5


def test_guardrail_rejects_below_min_green(signal_plan):
    import importlib.util

    path = PROJECT_ROOT / "skills/plan-generation/scripts/validate_plan_guardrails.py"
    spec = importlib.util.spec_from_file_location("guardrails", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    bad_plan = {
        "rollback_condition": "回滚",
        "timing": {
            "cycle_s": 120,
            "phase_stage_timing_list": [
                {
                    "phase_stage_name": "东进口直行",
                    "green_time_s": 10,
                    "min_green_time_s": 18,
                    "max_green_time_s": 50,
                    "greenTime": 10,
                    "minGreenTime": 18,
                }
            ],
        },
    }
    errors = mod.validate_plan_guardrails(bad_plan, {"max_cycle_s": 150})
    assert any("最小绿" in e for e in errors)


def test_guardrail_rejects_over_max_cycle(signal_plan):
    import importlib.util

    path = PROJECT_ROOT / "skills/plan-generation/scripts/validate_plan_guardrails.py"
    spec = importlib.util.spec_from_file_location("guardrails", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    plan = {
        "cycle_s": 200,
        "rollback_condition": "回滚",
        "timing": {"cycle_s": 200, "phase_stage_timing_list": signal_plan["phase_stage_timing_list"]},
    }
    errors = mod.validate_plan_guardrails(plan, {"max_cycle_s": 150})
    assert any("周期" in e for e in errors)


def test_guardrail_allows_preexisting_over_max_to_move_toward_bound():
    import importlib.util

    path = PROJECT_ROOT / "skills/plan-generation/scripts/validate_plan_guardrails.py"
    spec = importlib.util.spec_from_file_location("guardrails", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    plan = {
        "rollback_condition": "异常时回滚",
        "timing": {
            "cycle_s": 150,
            "phase_stage_timing_list": [
                {
                    "phase_stage_name": "东西直行",
                    "green_time_s": 80,
                    "min_green_time_s": 7,
                    "max_green_time_s": 60,
                    "current_timing": {"green_time_s": 85},
                }
            ],
        },
    }

    errors = mod.validate_plan_guardrails(plan, {"max_cycle_s": 180})
    assert not any("最大绿" in e for e in errors)


def test_guardrail_rejects_preexisting_over_max_when_adjustment_worsens_it():
    import importlib.util

    path = PROJECT_ROOT / "skills/plan-generation/scripts/validate_plan_guardrails.py"
    spec = importlib.util.spec_from_file_location("guardrails", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    plan = {
        "rollback_condition": "异常时回滚",
        "timing": {
            "cycle_s": 150,
            "phase_stage_timing_list": [
                {
                    "phase_stage_name": "东西直行",
                    "green_time_s": 90,
                    "min_green_time_s": 7,
                    "max_green_time_s": 60,
                    "current_timing": {"green_time_s": 85},
                }
            ],
        },
    }

    errors = mod.validate_plan_guardrails(plan, {"max_cycle_s": 180})
    assert any("最大绿" in e for e in errors)


def test_build_candidates_produces_phase_timing(signal_plan, overflow_fixtures):
    import importlib.util

    def _load(name: str):
        path = PROJECT_ROOT / f"skills/plan-generation/scripts/{name}"
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    metrics, topology = overflow_fixtures
    build = _load("build_candidates.py")
    timing = _load("generate_timing_plan.py")
    adjust = _load("adjust_phase_timing.py")
    guard = _load("validate_plan_guardrails.py")

    diagnosis = {
        "downstream_diagnosis": {"primary_downstream": {"inter_name": "舜华路与工业南路交叉口"}},
        "arterial_analysis": {"need_upstream_metering": True},
        "downstream_trace": {"governance": {"downstream_blocked": True}},
        "flow_trace": {
            "entry_traces": [
                {
                    "upstream_inter_id": "up1",
                    "upstream_inter_name": "文化东路与舜华路交叉口",
                    "upstream_lng": 117.12,
                    "upstream_lat": 36.66,
                }
            ]
        },
        "downstream_metrics": {"queue_ratio": 0.89},
    }
    strategy = {"strategy_package": "arterial_coordination", "case_references": {"matched_count": 2}}
    ticket = {"direction": "东向西", "movement": "直行", "intersection_name": "文化西路与舜华路交叉口"}

    candidates, optimizer_engine = build.build_plan_candidates(
        strategy,
        ticket,
        diagnosis,
        signal=signal_plan,
        constraints={"max_cycle_s": 150},
        generate_timing_plan=timing.generate_timing_plan,
        adjust_phase_timing=adjust.adjust_phase_timing,
        build_strategy_instruction=adjust.build_strategy_instruction,
        validate_plan_guardrails=guard.validate_plan_guardrails,
    )
    assert len(candidates) == 3
    recommended = next(c for c in candidates if c["plan_id"] == "arterial_coordination")
    assert recommended["guardrail_pass"] is True
    assert recommended["timing"]["phase_stage_timing_list"]
    assert recommended["upstream_control"]["enabled"] is True
    assert optimizer_engine in (None, "signal_optimization_engine")
