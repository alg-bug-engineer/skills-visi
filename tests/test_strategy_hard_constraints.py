"""需求 20·R5：红线补齐量化约束（最小绿/最大绿/最大周期），非纯定性。"""

import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    path = PROJECT_ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_PROFILE = _load("profile", "skills/strategy-generation/scripts/build_strategy_profile.py")

_CAUSE = {"cause_scores": {"scores": {"event": 0.5}, "primary_dimension": "event"}}
_DIAG = {"downstream_trace": {"governance": {"downstream_blocked": True}}}


def test_hard_constraints_include_quantitative_from_signal():
    signal = {
        "current_cycle_s": 120,
        "phase_stage_timing_list": [
            {"min_green_time_s": 15, "max_green_time_s": 60},
            {"min_green_time_s": 12, "max_green_time_s": 45},
        ],
    }
    constraints = {"max_cycle_s": 150}
    profile = _PROFILE.build_strategy_profile(
        _CAUSE, _DIAG, {}, signal=signal, constraints=constraints
    )
    red = profile["strategy"]["hard_constraints"]
    text = " ".join(red)
    assert "最小绿不得低于 12s" in text
    assert "绿灯不得超过 60s" in text
    assert "周期不得超过 150s" in text
    detail = profile["strategy"]["quantitative_constraints"]
    assert detail["min_green_s"] == 12
    assert detail["max_green_s"] == 60
    assert detail["max_cycle_s"] == 150
    assert detail["source"] == "pg_signal_plan"


def test_hard_constraints_degrade_when_no_signal():
    profile = _PROFILE.build_strategy_profile(_CAUSE, _DIAG, {})
    detail = profile["strategy"]["quantitative_constraints"]
    # 无真实配时不编造数值，标记缺失并保留定性红线
    assert detail["source"] == "unavailable"
    assert "all" in detail["missing"]
    assert any("最小绿" in c for c in profile["strategy"]["hard_constraints"])


def test_llm_list_fields_returned_as_string_are_normalized():
    """LLM 偶发把数组字段返回成字符串，不应抛 TypeError（回归：str + list）。"""
    signal = {"phase_stage_timing_list": [{"min_green_time_s": 15, "max_green_time_s": 60}]}
    llm_strategy = {
        "hard_constraints": "下游排队比超阈值时禁止继续增大目标方向放行",
        "principles": "防溢流优先",
        "not_recommended": "单点激进加绿",
        "recommended": "上游控流 + 目标小步释放",
    }
    profile = _PROFILE.build_strategy_profile(_CAUSE, _DIAG, llm_strategy, signal=signal)
    strategy = profile["strategy"]
    # 字符串被归一为单元素列表，且量化红线仍被拼接在后
    assert isinstance(strategy["hard_constraints"], list)
    assert "下游排队比超阈值时禁止继续增大目标方向放行" in strategy["hard_constraints"]
    assert any("最小绿" in c for c in strategy["hard_constraints"])
    assert strategy["principles"] == ["防溢流优先"]
    assert strategy["not_recommended"] == ["单点激进加绿"]
    assert strategy["recommended"] == ["上游控流 + 目标小步释放"]


def test_llm_empty_list_fields_fall_back_to_defaults():
    profile = _PROFILE.build_strategy_profile(
        _CAUSE, _DIAG, {"hard_constraints": [], "principles": "", "recommended": None}
    )
    strategy = profile["strategy"]
    assert any("最小绿" in c for c in strategy["hard_constraints"])
    assert strategy["principles"]  # 回退到内置默认
    assert strategy["recommended"]
