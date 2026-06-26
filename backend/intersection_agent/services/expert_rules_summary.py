"""Human-readable expert rule summaries for leadership demo narrative."""

from __future__ import annotations

from typing import Any

EXPERT_RULE_SUMMARIES: list[dict[str, str]] = [
    {
        "id": "EXP-FLOW-001",
        "title": "流量-配时匹配",
        "text": "高流量转向应获得与之匹配的有效绿灯占比；Spearman 失配或绿信比偏低时优先调整配时结构。",
        "checklist_ref": "flow_green_mismatch",
    },
    {
        "id": "EXP-IMB-001",
        "title": "进口服务失衡",
        "text": "失衡指数≥0.30 或转向饱和度极差≥0.60 且连续15分钟，说明绿信比分配与服务需求不匹配。",
        "checklist_ref": "service_imbalance",
    },
    {
        "id": "EXP-EMPTY-001",
        "title": "绿灯空放",
        "text": "分转向绿灯利用率连续15分钟低于0.60，存在明显空放，应压缩低利用相位绿灯。",
        "checklist_ref": "empty_green",
    },
    {
        "id": "EXP-SPILL-001",
        "title": "排队溢出",
        "text": "排队存储比≥0.80 或排队长度≥100m，进口存储空间不足，存在外溢与锁死风险。",
        "checklist_ref": "spillback",
    },
    {
        "id": "EXP-SAT-001",
        "title": "过饱和",
        "text": "路口或关键转向饱和度≥0.80，通行需求接近或超过当前配时服务能力。",
        "checklist_ref": "inter_evaluation",
    },
    {
        "id": "EXP-CYCLE-001",
        "title": "周期合理性",
        "text": "信号周期超过190秒或低于60秒，行人等待与相位清空均可能不满足要求。",
        "checklist_ref": "cycle_timing",
    },
    {
        "id": "EXP-COMPLAINT-001",
        "title": "民意交叉印证",
        "text": "投诉台账与运行数据同时指向问题时，应优先回应群众诉求并复核配时方案。",
        "checklist_ref": "public_complaint",
    },
]


def build_expert_rules_brief(
    flow_timing_governance: dict[str, Any] | None = None,
    *,
    max_items: int = 6,
) -> list[dict[str, str]]:
    """Return expert rules most relevant to triggered governance problems."""
    if not flow_timing_governance:
        return EXPERT_RULE_SUMMARIES[:max_items]

    triggered = {
        p.get("category")
        for p in (flow_timing_governance.get("problems") or [])
        if p.get("detected")
    }
    category_to_refs = {
        "saturation": {"inter_evaluation", "flow_green_mismatch"},
        "imbalance": {"service_imbalance", "flow_green_mismatch"},
        "empty_green": {"empty_green"},
        "spillback": {"spillback"},
    }
    wanted_refs: set[str] = set()
    for cat in triggered:
        wanted_refs.update(category_to_refs.get(str(cat), set()))

    selected = [
        item
        for item in EXPERT_RULE_SUMMARIES
        if item["checklist_ref"] in wanted_refs or not wanted_refs
    ]
    if not selected:
        selected = EXPERT_RULE_SUMMARIES
    return selected[:max_items]


def format_expert_rules_markdown(rules: list[dict[str, str]]) -> str:
    """Format expert rules as markdown bullet list."""
    if not rules:
        return ""
    lines = ["**一线经验依据**"]
    for rule in rules:
        lines.append(f"- {rule['title']}：{rule['text']}")
    return "\n".join(lines)
