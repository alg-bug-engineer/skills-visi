"""路口分层（problem_band）与试点评分（pilot_score）。

口径集中在此处 + 单元测试覆盖，避免散落各处。分层依据单路口完整诊断结果
（见 ``diagnose_one``）：

- **工程可解**：饱和度持续 ≥ 过饱和阈值，或信控改善上限低 —— 配时救不了，别浪费投入。
- **配时可解**：检出失衡 / 空放 / 绿灯利用率低 / 相位问题，且未达过饱和、信控改善上限高 —— 试点首选。
- **无明显问题**：无显著问题且饱和度适中。
- **数据不足**：该时段缺运行数据（``has_data=False``），单独标注，不参与排序。
"""

from __future__ import annotations

from typing import Any

ENGINEERING = "工程可解"
TIMING = "配时可解"
NO_PROBLEM = "无明显问题"
INSUFFICIENT = "数据不足"

_SEVERITY_WEIGHT = {"high": 1.0, "medium": 0.6, "low": 0.3, "none": 0.0}
_CEILING_WEIGHT = {"high": 1.0, "medium": 0.6, "low": 0.2}


def classify_problem_band(diag: dict[str, Any], thresholds: dict[str, Any]) -> str:
    """返回 ``diag`` 的 problem_band。"""
    if not diag.get("has_data"):
        return INSUFFICIENT

    sat = (diag.get("metrics") or {}).get("saturation_max")
    over = float((thresholds.get("saturation") or {}).get("oversaturation", 0.90))
    ceiling = diag.get("control_improvement_ceiling")
    has_issues = bool(diag.get("top_issues"))

    # 过饱和或信控改善上限低 → 工程可解（配时无效）。过饱和优先。
    if (sat is not None and sat >= over) or ceiling == "low":
        return ENGINEERING

    # 检出信控可解问题，且未过饱和 → 配时可解。
    if has_issues:
        return TIMING

    return NO_PROBLEM


def pilot_score(diag: dict[str, Any], band: str) -> float | None:
    """试点推荐分：仅对 ``配时可解`` 计算。

    ``severity_weight × ceiling_weight × data_confidence``，
    随 severity 与 control_improvement_ceiling 单调上升，数据质量差则打折。
    """
    if band != TIMING:
        return None

    severity_w = _SEVERITY_WEIGHT.get(diag.get("severity", "none"), 0.0)
    ceiling_w = _CEILING_WEIGHT.get(diag.get("control_improvement_ceiling", "medium"), 0.6)

    tags = diag.get("data_quality_tags") or []
    data_confidence = max(0.3, 1.0 - 0.2 * len(tags))

    score = severity_w * ceiling_w * data_confidence
    return round(score * 100, 2)
