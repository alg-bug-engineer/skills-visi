"""需求 34：护栏周期硬约束与推荐聚合。"""

import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_guardrails():
    path = PROJECT_ROOT / "skills/plan-generation/scripts/validate_plan_guardrails.py"
    spec = importlib.util.spec_from_file_location("guardrails", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_guardrail_rejects_190_over_180():
    mod = _load_guardrails()
    plan = {
        "cycle_s": 190,
        "rollback_condition": "回滚",
        "timing": {
            "cycle_s": 190,
            "phase_stage_timing_list": [
                {"phase_stage_name": "南直", "greenTime": 40, "minGreenTime": 14, "maxGreenTime": 60}
            ],
        },
        # 即使引擎声称更大上限，也不能旁路产品硬约束
        "planType": "single_point",
        "meta": {"max_cycle_s": 220},
    }
    errors = mod.validate_plan_guardrails(plan, {"max_cycle_s": 180})
    assert any("周期" in e and "180" in e for e in errors)


def test_guardrail_requires_max_cycle_constraint():
    mod = _load_guardrails()
    plan = {
        "cycle_s": 190,
        "rollback_condition": "回滚",
        "timing": {"cycle_s": 190, "phase_stage_timing_list": [{"greenTime": 30, "minGreenTime": 14}]},
    }
    errors = mod.validate_plan_guardrails(plan, {})
    assert any("缺少周期上限" in e for e in errors)
