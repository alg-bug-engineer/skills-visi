"""Build rule-based and LLM-ready diagnosis summary from checklist + issues."""

from __future__ import annotations

from typing import Any

CAUSE_LABELS = {
    "supply": "供给/渠化",
    "demand": "需求",
    "control": "信控",
    "order": "秩序",
    "event": "事件",
    "data_quality": "数据质量",
}

CATEGORY_LABELS = {
    "static": "静态短板",
    "dynamic": "动态信控",
    "special": "特殊需求",
    "summary": "成因汇总",
}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def build_diagnosis_insights(
    diagnosis: dict[str, Any],
    checklist_queries: list[dict[str, Any]] | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structured insights for LLM summary."""
    items = checklist_queries or []
    triggered = [item for item in items if item.get("triggered")]
    passed = [item for item in items if item.get("status") == "passed"]
    no_data = [item for item in items if item.get("status") == "no_data"]

    issues = diagnosis.get("issues") or []
    top_issues = [issue for issue in issues if issue.get("issue_code") != "stable"][:5]
    cause_scores = diagnosis.get("cause_scores") or {}
    top_cause = max(cause_scores.items(), key=lambda x: x[1]) if cause_scores else ("control", 0.0)

    static_triggered = [item for item in triggered if item.get("category") == "static"]
    dynamic_triggered = [item for item in triggered if item.get("category") == "dynamic"]

    supply = (profile or {}).get("supply_profile") or {}
    name = str(supply.get("name") or "该路口")
    profile_facts = (profile or {}).get("evidence_chain") or []
    metrics_facts = ((profile or {}).get("metrics_insights") or {}).get("facts") or []

    facts: list[str] = []
    facts.append(f"共检查 {len(items)} 项，命中 {len(triggered)} 项，通过 {len(passed)} 项，数据不足 {len(no_data)} 项。")
    if static_triggered:
        facts.append("静态短板：" + "；".join(item.get("summary", item.get("label", "")) for item in static_triggered[:3]))
    if dynamic_triggered:
        facts.append("动态问题：" + "；".join(item.get("summary", item.get("label", "")) for item in dynamic_triggered[:3]))
    if top_issues:
        facts.append(
            "优先问题：" + "、".join(
                f"{issue.get('name')}({issue.get('severity')})" for issue in top_issues[:3]
            )
        )
    if cause_scores:
        facts.append(
            f"主因维度 {CAUSE_LABELS.get(top_cause[0], top_cause[0])} 贡献 {top_cause[1]:.0%}。"
        )
    facts.append(
        f"信控改善上限 {diagnosis.get('control_improvement_ceiling', '-')}，"
        f"问题来源 {diagnosis.get('problem_source', '-')}，场景类型 {diagnosis.get('scene_type', profile.get('scene_type') if profile else '-')}。"
    )
    for ref in profile_facts[:3]:
        text = ref.get("text")
        if text:
            facts.append(f"画像证据：{text}")
    for fact in metrics_facts[:2]:
        text = fact.get("text") if isinstance(fact, dict) else str(fact)
        if text:
            facts.append(f"时序洞察：{text}")

    return {
        "intersection_name": name,
        "checklist_stats": {
            "total": len(items),
            "triggered": len(triggered),
            "passed": len(passed),
            "no_data": len(no_data),
        },
        "triggered_items": [
            {
                "item_id": item.get("item_id"),
                "label": item.get("label"),
                "category": item.get("category"),
                "summary": item.get("summary"),
                "issue_codes": item.get("issue_codes") or [],
            }
            for item in triggered
        ],
        "top_issues": [
            {
                "issue_code": issue.get("issue_code"),
                "name": issue.get("name"),
                "severity": issue.get("severity"),
                "score": issue.get("score"),
                "root_cause": issue.get("root_cause"),
                "control_leverage": issue.get("control_leverage"),
            }
            for issue in top_issues
        ],
        "cause_scores": cause_scores,
        "problem_source": diagnosis.get("problem_source"),
        "control_improvement_ceiling": diagnosis.get("control_improvement_ceiling"),
        "scene_type": diagnosis.get("scene_type") or (profile or {}).get("scene_type"),
        "profile_evidence_refs": profile_facts[:8],
        "uncertainty": diagnosis.get("uncertainty") or [],
        "facts": facts,
    }


def build_template_diagnosis_summary(
    diagnosis: dict[str, Any],
    checklist_queries: list[dict[str, Any]] | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rule-based narrative when LLM is unavailable."""
    insights = build_diagnosis_insights(diagnosis, checklist_queries, profile)
    name = insights.get("intersection_name") or "该路口"
    facts = insights.get("facts") or []
    highlights: list[dict[str, str]] = []

    triggered = insights.get("triggered_items") or []
    static_items = [item for item in triggered if item.get("category") == "static"]
    dynamic_items = [item for item in triggered if item.get("category") == "dynamic"]
    special_items = [item for item in triggered if item.get("category") == "special"]

    if static_items:
        highlights.append({
            "topic": "静态短板",
            "text": "；".join(item.get("summary") or item.get("label", "") for item in static_items[:3]),
        })
    if dynamic_items:
        highlights.append({
            "topic": "动态信控",
            "text": "；".join(item.get("summary") or item.get("label", "") for item in dynamic_items[:3]),
        })
    if special_items:
        highlights.append({
            "topic": "特殊需求",
            "text": "；".join(item.get("summary") or item.get("label", "") for item in special_items[:2]),
        })

    cause_scores = insights.get("cause_scores") or {}
    if cause_scores:
        ordered = sorted(cause_scores.items(), key=lambda x: -x[1])[:3]
        highlights.append({
            "topic": "成因评分",
            "text": "、".join(f"{CAUSE_LABELS.get(k, k)} {v:.0%}" for k, v in ordered),
        })

    top_issues = insights.get("top_issues") or []
    if top_issues:
        highlights.append({
            "topic": "优先治理",
            "text": "；".join(
                f"{issue.get('name')}（{issue.get('control_leverage')} 杠杆）"
                for issue in top_issues[:3]
            ),
        })

    if not triggered and top_issues and top_issues[0].get("issue_code") == "stable":
        narrative = f"{name}运行基本稳定，检查单未命中显著静态或动态问题。"
    elif facts:
        narrative = f"{name}问题诊断结论：" + " ".join(facts)
    else:
        narrative = f"{name}缺少足够画像证据，建议先完成场景认知并补采关键指标。"

    uncertainty = list(insights.get("uncertainty") or [])
    no_data_count = (insights.get("checklist_stats") or {}).get("no_data", 0)
    if no_data_count >= 3:
        uncertainty.append(f"{no_data_count} 项检查因数据不足无法判定，诊断置信度受限。")

    return {
        "source": "template",
        "narrative": narrative,
        "highlights": highlights[:6],
        "diagnosis_insights": insights,
        "uncertainty": uncertainty,
    }


def summarize_diagnosis(
    diagnosis: dict[str, Any],
    checklist_queries: list[dict[str, Any]] | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Public entry: structured insights plus template summary."""
    summary = build_template_diagnosis_summary(diagnosis, checklist_queries, profile)
    return {
        "diagnosis_insights": summary["diagnosis_insights"],
        "diagnosis_summary": summary,
    }
