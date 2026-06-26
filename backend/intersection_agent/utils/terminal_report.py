"""Terminal-friendly evidence and constraint report formatting."""

from __future__ import annotations

from typing import Any


def format_evidence_report(
    evidence: dict[str, Any] | None,
    constraints: dict[str, Any] | None = None,
) -> str:
    """Render a human-readable evidence block for CLI / debug logs."""
    if not evidence:
        return "（无问题验证证据）"

    width = 50
    lines: list[str] = [
        "═" * width,
        f" 问题验证证据 · {evidence.get('intersection', '—')} · {evidence.get('time_label', '—')}",
        "═" * width,
    ]

    chronic = evidence.get("chronic") or {}
    if chronic.get("verdict"):
        tag = "✓" if chronic.get("is_chronic") else "·"
        lines.append(f"【常发性】{chronic['verdict']} {tag}")

    dow = evidence.get("dow_pattern") or {}
    if dow.get("verdict"):
        lines.append(f"【星期规律】{dow['verdict']}")

    metrics = evidence.get("metrics") or {}
    thresholds = evidence.get("thresholds_used") or {}
    lines.append("【运行指标】")
    if metrics.get("avg_delay_s") is not None:
        lines.append(
            f"  平均停车/延误  {metrics['avg_delay_s']} s"
            f"    (阈值 {thresholds.get('excess_delay_s', 60)}s)"
        )
    if metrics.get("delay_index") is not None:
        lines.append(f"  延误指数        {metrics['delay_index']}")
    if metrics.get("avg_queue_m") is not None:
        lines.append(
            f"  平均排队        {metrics['avg_queue_m']} m"
            f"    (长排队 {thresholds.get('long_queue_m', 100)}m)"
        )
    if metrics.get("max_queue_m") is not None:
        lines.append(f"  最大排队        {metrics['max_queue_m']} m")
    if metrics.get("saturation_rate") is not None:
        lines.append(
            f"  饱和度          {float(metrics['saturation_rate']):.0%}"
            f"    (高饱和 {thresholds.get('saturation_high', 0.8):.0%})"
        )
    if metrics.get("spillback_risk_max") is not None:
        lines.append(
            f"  溢流风险(估)    {metrics['spillback_risk_max']:.2f}"
            f"    (阈值 {thresholds.get('queue_storage_ratio_high', 0.8):.2f})"
        )

    by_dir = evidence.get("by_direction") or []
    if by_dir:
        lines.append("【分方向】")
        for item in by_dir:
            focus = " *" if item.get("focused") else ""
            sat = item.get("saturation")
            q = item.get("avg_queue_m")
            parts = [item.get("group", "—") + focus]
            if sat is not None:
                parts.append(f"饱和 {sat:.0%}")
            if q is not None:
                parts.append(f"排队 {q}m")
            lines.append("  " + "，".join(parts))

    if evidence.get("coverage_warning"):
        lines.append(f"⚠ {evidence['coverage_warning']}")

    if constraints:
        lines.append("【用户约束量化】")
        lines.append(f"  原文: {constraints.get('raw_text', '—')}")
        if constraints.get("protected_directions"):
            lines.append(
                "  保护方向: "
                + "、".join(constraints.get("protected_directions") or [])
            )
        lines.append(f"  {constraints.get('narrative', '')}")
        for item in constraints.get("constraints") or []:
            lines.append(
                f"  → {item.get('scope')} {item.get('metric')} "
                f"{item.get('operator')} {item.get('value')} "
                f"(baseline {item.get('baseline')})"
            )

    lines.append("═" * width)
    return "\n".join(lines)


def format_evidence_summary_markdown(evidence: dict[str, Any] | None) -> str:
    """Short markdown block for chat diagnosis confirmation."""
    if not evidence:
        return ""

    lines: list[str] = ["**问题验证（数据支撑）**"]
    if evidence.get("summary"):
        lines.append(str(evidence["summary"]))

    metrics = evidence.get("metrics") or {}
    detail_bits: list[str] = []
    if metrics.get("saturation_rate") is not None:
        detail_bits.append(f"饱和度 {float(metrics['saturation_rate']):.0%}")
    if metrics.get("avg_delay_s") is not None:
        detail_bits.append(f"平均停车 {metrics['avg_delay_s']}s")
    if metrics.get("avg_queue_m") is not None:
        detail_bits.append(f"平均排队 {metrics['avg_queue_m']}m")
    if metrics.get("max_queue_m") is not None:
        detail_bits.append(f"最大排队 {metrics['max_queue_m']}m")
    if detail_bits:
        lines.append("📊 " + "，".join(detail_bits))

    chronic = evidence.get("chronic") or {}
    if chronic.get("is_chronic"):
        lines.append(
            f"📅 常发性：近{chronic.get('window_days', 7)}日中有"
            f"{chronic.get('congested_days', '—')}日该时段超标"
        )

    dow = evidence.get("dow_pattern") or {}
    if dow.get("dow_label") and dow.get("hit_rate") is not None:
        lines.append(
            f"🗓 {dow['dow_label']}命中率 {float(dow['hit_rate']):.0%}"
            f"（{dow.get('hit_days')}/{dow.get('total_days')} 日）"
        )

    by_dir = evidence.get("by_direction") or []
    focused = [d for d in by_dir if d.get("focused")]
    if focused:
        dir_bits = []
        for item in focused:
            bit = item.get("group", "")
            if item.get("saturation") is not None:
                bit += f" 饱和{item['saturation']:.0%}"
            if item.get("avg_queue_m") is not None:
                bit += f" 排队{item['avg_queue_m']}m"
            dir_bits.append(bit.strip())
        if dir_bits:
            lines.append("🧭 关注方向：" + "；".join(dir_bits))

    if evidence.get("coverage_warning"):
        lines.append(f"⚠ {evidence['coverage_warning']}")

    return "\n".join(lines)
