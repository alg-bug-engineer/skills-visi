"""Round-time experience contrast for R3 (有经验 vs 无经验基线)."""

from __future__ import annotations

from typing import Any

_PACKAGE_LABELS = {
    "downstream_protection": "下游保护方案",
    "incremental_release": "小步释放方案",
    "arterial_coordination": "干线联控方案",
    "verification_plan": "先验核验方案",
}

_CAUSE_DIM_LABELS = {
    "demand": "交通需求压力",
    "supply": "通行供给不足",
    "control": "信号控制不当",
    "order": "交通秩序干扰",
    "event": "事件与阻塞",
    "coordination": "协调联动不足",
}

_MECHANISM_LABELS = {
    "downstream_blocked": "下游回堵",
    "local_release_insufficient": "本路口放行不足",
    "discharge_anomaly": "放行效率异常，待核验",
    "upstream_arrival_shock": "上游冲击",
    "evidence_insufficient": "证据不足，待补盲",
}


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _top_package(scores: dict[str, float]) -> str | None:
    if not scores:
        return None
    return max(scores, key=scores.get)


def _ref_from_experience(exp: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "user_experience",
        "record_id": exp.get("record_id"),
        "trace_id": exp.get("trace_id"),
        "label": _clean(exp.get("content")) or exp.get("record_id"),
    }


def _ref_from_case(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "case",
        "case_id": card.get("case_id"),
        "label": _clean(card.get("title")) or card.get("case_id"),
    }


def build_experience_contrast(
    *,
    cause: dict[str, Any] | None,
    diagnosis: dict[str, Any] | None,
    strategy: dict[str, Any] | None,
    ticket: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """基于本轮 pipeline 真实输出构建对照项；无法派生时 available=false。"""
    cause = cause or {}
    diagnosis = diagnosis or {}
    strategy = strategy or {}
    ticket = ticket or {}

    items: list[dict[str, Any]] = []
    package_scores = strategy.get("package_scores") if isinstance(strategy.get("package_scores"), dict) else {}
    baseline_pkg = _top_package({k: float(v) for k, v in package_scores.items() if v is not None})
    selected_pkg = _clean(strategy.get("strategy_package")) or baseline_pkg
    exp_refs = [r for r in (cause.get("user_experience_refs") or []) if isinstance(r, dict)]
    case_cards = [c for c in ((cause.get("case_cards") or {}).get("cards") or []) if isinstance(c, dict)]
    user_exps = [e for e in (ticket.get("user_experiences") or []) if isinstance(e, dict)]

    if baseline_pkg:
        baseline_label = _PACKAGE_LABELS.get(baseline_pkg, baseline_pkg)
        selected_label = _PACKAGE_LABELS.get(selected_pkg or "", selected_pkg or baseline_label)
        refs: list[dict[str, Any]] = []
        refs.extend(_ref_from_experience(r) for r in exp_refs[:3])
        refs.extend(_ref_from_case(c) for c in case_cards[:2])
        with_summary = selected_label
        if refs:
            with_summary = f"{selected_label}（参考 {len(refs)} 条经验/案例）"
        elif user_exps:
            with_summary = f"{selected_label}（含用户口述约束 {len(user_exps)} 条）"
        items.append(
            {
                "dimension": "策略选择",
                "without_experience": {
                    "summary": f"仅依赖实时指标评分 → {baseline_label}",
                    "source": "package_scores",
                },
                "with_experience": {
                    "summary": with_summary,
                    "refs": refs,
                    "source": "strategy_generation",
                },
            }
        )

    cause_analysis = cause.get("cause_analysis") if isinstance(cause.get("cause_analysis"), dict) else {}
    ranking = cause.get("cause_ranking") if isinstance(cause.get("cause_ranking"), list) else []
    scores = (cause.get("cause_scores") or {}).get("scores") if isinstance(cause.get("cause_scores"), dict) else {}
    if not isinstance(scores, dict):
        scores = cause.get("cause_scores") if isinstance(cause.get("cause_scores"), dict) else {}

    mechanism = (
        (diagnosis.get("overflow_mechanism") or {}).get("primary")
        or (cause.get("overflow_mechanism") or {}).get("primary")
    )
    primary = _MECHANISM_LABELS.get(str(mechanism)) if mechanism else None
    primary = primary or _clean(cause_analysis.get("primary_cause"))
    top_score_cause = None
    if scores:
        top_key = max(scores, key=lambda k: float(scores.get(k) or 0))
        top_score_cause = _CAUSE_DIM_LABELS.get(str(top_key), top_key)
    baseline_cause = top_score_cause or (
        ranking[0].get("cause") if ranking and isinstance(ranking[0], dict) else None
    )
    if baseline_cause in _CAUSE_DIM_LABELS:
        baseline_cause = _CAUSE_DIM_LABELS[str(baseline_cause)]

    decision = strategy.get("decision") if isinstance(strategy.get("decision"), dict) else {}
    if decision.get("decision_mode") == "verify_then_adjust":
        # 先验后调场景：策略对照应强调核验后再增绿，而非直接小步释放包装名
        if items and items[0].get("dimension") == "策略选择":
            items[0]["with_experience"] = {
                **(items[0].get("with_experience") or {}),
                "summary": "先验后调 → 核验通过后再小步增绿",
            }
            items[0]["without_experience"] = {
                "summary": "仅依赖实时指标可能直接小步释放",
                "source": "package_scores",
            }

    if primary or baseline_cause:
        diag_refs = [_ref_from_experience(r) for r in exp_refs if r.get("experience_type") == "diagnostic"][:3]
        items.append(
            {
                "dimension": "成因判断",
                "without_experience": {
                    "summary": _clean(baseline_cause) or "仅依赖六维评分最高项",
                    "source": "cause_scores",
                },
                "with_experience": {
                    "summary": primary or _clean(baseline_cause) or "—",
                    "refs": diag_refs,
                    "source": "cause_analysis",
                },
            }
        )
    else:
        diag_refs = [_ref_from_experience(r) for r in exp_refs if r.get("experience_type") == "diagnostic"][:3]

    strat = strategy.get("strategy") if isinstance(strategy.get("strategy"), dict) else {}
    hard = strat.get("hard_constraints") if isinstance(strat.get("hard_constraints"), list) else []
    quant = strat.get("quantitative_constraints") if isinstance(strat.get("quantitative_constraints"), dict) else {}
    quant_count = sum(1 for k in ("min_green_s", "max_green_s", "max_cycle_s") if quant.get(k) is not None)
    user_constraint_count = len(ticket.get("constraints") or []) + len(user_exps)

    if hard or quant_count:
        items.append(
            {
                "dimension": "治理护栏",
                "without_experience": {
                    "summary": f"量化护栏 {quant_count} 项（PG 配时真源）",
                    "source": "quantitative_constraints",
                },
                "with_experience": {
                    "summary": f"护栏 {len(hard)} 条（含用户约束 {user_constraint_count} 条）",
                    "refs": [_ref_from_experience(r) for r in exp_refs if r.get("experience_type") != "solution"][:2],
                    "source": "strategy.hard_constraints",
                },
            }
        )

    dd = diagnosis.get("downstream_diagnosis") if isinstance(diagnosis.get("downstream_diagnosis"), dict) else {}
    if dd.get("release_answer"):
        items.append(
            {
                "dimension": "下游承接",
                "without_experience": {
                    "summary": "仅看目标路口排队/饱和度指标",
                    "source": "diagnosis.metrics",
                },
                "with_experience": {
                    "summary": _clean(dd.get("release_answer")) or _clean(dd.get("narrative")) or "—",
                    "refs": diag_refs[:1] if exp_refs else [],
                    "source": "downstream_diagnosis",
                },
            }
        )

    available = len(items) >= 1
    return {
        "available": available,
        "reason": None if available else "本轮缺少可对照的 pipeline 输出",
        "items": items,
    }
