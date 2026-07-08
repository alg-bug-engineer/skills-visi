from __future__ import annotations

from typing import Any


def select_strategy_package(cause: dict[str, Any], diagnosis: dict[str, Any]) -> str:
    if cause.get("arterial_coordination_needed") or diagnosis.get("arterial_analysis", {}).get(
        "need_upstream_metering"
    ):
        return "arterial_coordination"
    governance = diagnosis.get("downstream_trace", {}).get("governance", {})
    if governance.get("downstream_blocked"):
        return "downstream_protection"
    bottleneck = diagnosis.get("bottleneck_analysis", {})
    if bottleneck.get("bottleneck_type") == "local_release":
        return "incremental_release"
    return "downstream_protection"


def extract_case_lessons(cause: dict[str, Any]) -> dict[str, Any]:
    cases = cause.get("similar_cases", [])
    return {
        "failure_lesson": "单点加绿后下游排队继续增长" if cases else None,
        "success_lesson": "上游控流+目标小步释放+下游保护后外溢风险下降" if cases else None,
        "matched_count": len(cases),
    }


# 行业场景（expert_knowledge.md 的 19 个场景之一）按策略方案的最佳匹配映射。
# 属「派生」映射：无精确场景分类器时按治理方案给出保守候选，供前端参考依据 chip 定位。
_SCENE_BY_PACKAGE = {
    "arterial_coordination": "主干道干线绿波协调",
    "downstream_protection": "短间距相邻路口协同控制",
    "incremental_release": "一般路口优化",
}


def build_reference_basis(
    cause: dict[str, Any],
    ticket: dict[str, Any],
    *,
    strategy_package: str | None = None,
) -> dict[str, Any]:
    """治理策略「参考依据」字段：行业场景标签 + 路口案例 id（可点击定位）。

    - ``industry_scene``: 按策略方案派生到 expert_knowledge 19 场景之一，缺依据则 None（不编造）。
    - ``intersection_case_ids``: 汇总 cause.case_cards.cards[].case_id 与目标路口 inter_id，去重、去空。
    """
    case_ids: list[str] = []

    def _push(value: Any) -> None:
        text = str(value or "").strip()
        if text and text not in case_ids:
            case_ids.append(text)

    _push((ticket or {}).get("inter_id"))
    for card in ((cause or {}).get("case_cards") or {}).get("cards") or []:
        if isinstance(card, dict):
            _push(card.get("case_id"))

    industry_scene = _SCENE_BY_PACKAGE.get(strategy_package) if strategy_package else None
    return {"industry_scene": industry_scene, "intersection_case_ids": case_ids}
