"""需求13-步骤5：问题常发性/周期性派生 + 治理策略「参考依据」字段。

- Part A: analyze_overflow 输出 diagnosis["problem_regularity"] = {recurring, periodic, basis}，
  为「派生」定性（非实测）；无依据时降级为 {recurring:null, periodic:null, basis:"数据不足"}，不抛异常。
- Part B: 策略阶段暴露 strategy["reference_basis"] = {industry_scene, intersection_case_ids}，
  case_id 取自 cause.case_cards + 目标路口 inter_id（去重），industry_scene 可派生时给出、否则 null。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_analyze_overflow():
    script = (
        REPO_ROOT / "skills" / "data-analysis-diagnosis" / "scripts" / "analyze_overflow.py"
    )
    spec = importlib.util.spec_from_file_location("analyze_overflow", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_select_package():
    script = REPO_ROOT / "skills" / "strategy-generation" / "scripts" / "select_package.py"
    spec = importlib.util.spec_from_file_location("select_package", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Part A: problem_regularity
# ---------------------------------------------------------------------------


def test_regularity_high_pressure_known_period_and_day():
    module = _load_analyze_overflow()
    result = module.derive_problem_regularity(
        saturation=1.80,
        queue_ratio=1.1,
        period="周三 晚高峰（17:00-19:00）",
        day_of_week=3,
        flow_correlate=[{"period_type": "EVENING_PEAK", "day_of_week": "周三"}],
    )
    assert result["recurring"], "高压 + 已知高峰时段应派生常发性描述"
    assert "1.80" in result["recurring"]
    assert result["periodic"], "已知星期几应派生周期性描述"
    assert "周三" in result["periodic"]
    # basis 必须明确是「派生 / 规律」而非实测
    assert any(kw in result["basis"] for kw in ("派生", "规律"))
    assert result["basis"] != "数据不足"


def test_regularity_missing_inputs_degrades_gracefully():
    module = _load_analyze_overflow()
    result = module.derive_problem_regularity(
        saturation=None,
        queue_ratio=None,
        period=None,
        day_of_week=None,
        flow_correlate=None,
    )
    assert result == {"recurring": None, "periodic": None, "basis": "数据不足"}


def test_regularity_low_pressure_no_recurring():
    module = _load_analyze_overflow()
    result = module.derive_problem_regularity(
        saturation=0.4,
        queue_ratio=0.2,
        period="晚高峰",
        day_of_week=None,
    )
    # 压力不高 → 无常发性；无星期几 → 无周期性
    assert result["recurring"] is None
    assert result["periodic"] is None
    assert result["basis"] == "数据不足"


def test_regularity_exposed_in_analyze_overflow_output():
    module = _load_analyze_overflow()
    metrics_input = json.loads((FIXTURES / "overflow_metrics.json").read_text(encoding="utf-8"))
    ticket = {
        "intersection_name": "文化西路与舜华路交叉口",
        "direction": "东向西",
        "movement": "直行",
        "period": "周三 晚高峰",
    }
    output = module.analyze_overflow(
        metrics_input,
        ticket,
        topology=None,
        pg_raw={},
        signal={},
        scope={},
        task_metrics={},
    )
    assert "problem_regularity" in output
    reg = output["problem_regularity"]
    assert set(reg.keys()) == {"recurring", "periodic", "basis"}
    # 已知星期几 → periodic 非空
    assert reg["periodic"] and "周三" in reg["periodic"]


# ---------------------------------------------------------------------------
# Part B: reference_basis
# ---------------------------------------------------------------------------


def test_reference_basis_collects_case_ids_and_scene():
    module = _load_select_package()
    cause = {
        "case_cards": {
            "cards": [
                {"case_id": "011wwe28ctu00001"},
                {"case_id": "011wwe289qc00001"},
                {"case_id": "011wwe28ctu00001"},  # 重复应去重
            ]
        }
    }
    ticket = {"inter_id": "011wwe28ctu00001"}
    basis = module.build_reference_basis(
        cause, ticket, strategy_package="arterial_coordination"
    )
    assert "intersection_case_ids" in basis
    ids = basis["intersection_case_ids"]
    assert "011wwe28ctu00001" in ids
    assert "011wwe289qc00001" in ids
    assert len(ids) == len(set(ids)), "case_id 应去重"
    # 干线联控 → 可派生行业场景
    assert basis["industry_scene"]


def test_reference_basis_empty_when_no_cases():
    module = _load_select_package()
    basis = module.build_reference_basis({}, {}, strategy_package=None)
    assert basis["intersection_case_ids"] == []
    assert basis["industry_scene"] is None
