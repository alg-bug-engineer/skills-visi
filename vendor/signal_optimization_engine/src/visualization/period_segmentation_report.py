"""HTML report for automatic timing-period segmentation."""

from __future__ import annotations

import html
import json
import math
from pathlib import Path
from typing import Any

DIR_COLORS = {
    0: "#3b82f6",
    1: "#06b6d4",
    2: "#10b981",
    3: "#84cc16",
    4: "#f59e0b",
    5: "#ef4444",
    6: "#8b5cf6",
    7: "#ec4899",
}
TURN_DASH = {"left": "7 4", "through": "", "right": "2 4", "approach": ""}
TURN_LABELS = {"left": "左转", "through": "直行", "right": "右转", "approach": "关键车道"}
FLOW_LAYER_STYLES = {
    "criticalVph": {"label": "原始", "opacity": 0.38, "width": 1.0, "dash": "inherit"},
    "smoothPass1Vph": {"label": "一次平滑", "opacity": 0.62, "width": 1.25, "dash": "4 3"},
    "smoothPass2Vph": {"label": "二次平滑", "opacity": 0.78, "width": 1.45, "dash": "3 2"},
    "smoothPass3Vph": {"label": "三次平滑", "opacity": 0.95, "width": 1.7, "dash": ""},
}
FLOW_LAYER_ORDER = ("criticalVph", "smoothPass1Vph", "smoothPass2Vph", "smoothPass3Vph")
PERIOD_COLORS = [
    "#38bdf8",
    "#34d399",
    "#a78bfa",
    "#fbbf24",
    "#fb7185",
    "#2dd4bf",
    "#818cf8",
    "#f472b6",
    "#4ade80",
    "#60a5fa",
    "#c084fc",
    "#facc15",
    "#22d3ee",
    "#f87171",
    "#a3e635",
]
MINUTES_PER_DAY = 24 * 60


def build_flow_chart_svg(flow_chart: dict[str, Any]) -> str:
    """SVG flow curves without period bands."""
    if not flow_chart:
        return ""
    return _build_overlay_chart_svg(flow_chart, [])


def build_flow_series_legend_html(flow_chart: dict[str, Any]) -> str:
    """HTML legend for critical-lane flow series with direction/turn labels."""
    items: list[str] = []
    for series in flow_chart.get("series") or []:
        color = DIR_COLORS.get(int(series.get("dir8Code") or 0), "#94a3b8")
        turn = str(series.get("turn") or "through")
        dash = TURN_DASH.get(turn, "")
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        label = html.escape(str(series.get("label") or _series_display_label(series)))
        turn_hint = html.escape(TURN_LABELS.get(turn, turn))
        items.append(
            '<span class="period-chip">'
            f'<svg width="28" height="10" viewBox="0 0 28 10" aria-hidden="true">'
            f'<line x1="0" y1="5" x2="28" y2="5" stroke="{color}" stroke-width="2.2" '
            f'opacity="0.9"{dash_attr}/></svg>'
            f"<span>{label}</span>"
            f'<span style="color:#64748b;">· {turn_hint}</span>'
            "</span>"
        )
    if not items:
        return ""
    return f'<div class="legend">{"".join(items)}</div>'


def _series_display_label(series: dict[str, Any]) -> str:
    dir_name = str(series.get("dirName") or "")
    turn_name = str(series.get("turnName") or series.get("turn") or "")
    if dir_name and not str(turn_name).startswith(dir_name):
        return f"{dir_name}{turn_name}"
    return turn_name or dir_name or "关键车道"


def build_segmentation_chart_svg(result: dict[str, Any]) -> str:
    """SVG flow curves with automatic period overlay bands."""
    flow_chart = result.get("flowChart") or {}
    periods = result.get("periods") or []
    if not flow_chart:
        return ""
    return _build_overlay_chart_svg(flow_chart, periods)


def render_period_segmentation_html(result: dict[str, Any]) -> str:
    title = _title(result)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif; background:#071426; color:#e5eefb; }}
    header {{ padding:20px 28px; background:#0d2340; border-bottom:1px solid #1c426b; }}
    h1 {{ margin:0; color:#4fd1ff; font-size:22px; }}
    main {{ padding:22px 28px; }}
    section {{ margin:0 0 18px; background:#0d1f38; border:1px solid #1c426b; border-radius:10px; overflow:hidden; }}
    h2 {{ margin:0; padding:12px 16px; font-size:16px; color:#93e5ff; background:#102a4a; }}
    .section-body {{ padding:14px 16px; }}
    table {{ width:100%; border-collapse:collapse; }}
    th,td {{ padding:10px 12px; border-bottom:1px solid #18375d; text-align:left; vertical-align:top; }}
    th {{ color:#8fb3d9; font-weight:600; }}
    .ok {{ color:#34d399; font-weight:700; }}
    .muted {{ color:#8aa3bd; font-size:12px; line-height:1.6; }}
    .bar-wrap {{ width:120px; height:10px; background:#132b49; border-radius:999px; display:inline-block; overflow:hidden; }}
    .bar {{ display:block; height:10px; background:#34d399; }}
    .chart-wrap {{ background:#08192d; border:1px solid #18375d; border-radius:8px; padding:8px; }}
    .legend {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }}
    .legend-item {{ display:inline-flex; align-items:center; gap:6px; font-size:11px; color:#b8cce4; }}
    .legend-swatch {{ width:14px; height:14px; border-radius:3px; border:1px solid rgba(255,255,255,.15); }}
    .period-chip {{ display:inline-flex; align-items:center; gap:6px; padding:3px 8px; border-radius:999px; font-size:11px; background:#102a4a; border:1px solid #1c426b; }}
    pre {{ margin:0; padding:14px 16px; white-space:pre-wrap; color:#d8e7f8; overflow:auto; }}
  </style>
</head>
<body>
  <header><h1>{html.escape(title)}</h1></header>
  <main>
    {_summary_section(result)}
    {_chart_section(result)}
    {_period_section(result)}
    {_pair_section(result)}
    {_baseline_section(result)}
    {_raw_json_section(result)}
  </main>
</body>
</html>
"""


def write_period_segmentation_html(result: dict[str, Any], output_path: str | Path) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_period_segmentation_html(result), encoding="utf-8")


def _title(result: dict[str, Any]) -> str:
    name = result.get("interName") or result.get("interId") or "UNKNOWN"
    flow_label = _flow_source_label(result)
    return f"配时时段自动划分测试报告 - {name} {flow_label}".strip()


def _flow_source_label(result: dict[str, Any]) -> str:
    meta = result.get("flowDateMeta") or {}
    if meta.get("profileMode"):
        labels = "、".join(label for label in (meta.get("weekdayLabels") or []) if label)
        return labels or "历史均值"
    date = result.get("date") or ""
    return str(date)


def _summary_section(result: dict[str, Any]) -> str:
    quality = result.get("dataQuality") or {}
    constraints = result.get("constraints") or {}
    meta = result.get("flowDateMeta") or {}
    rows = [
        ("路口", f"{result.get('interName') or ''} ({result.get('interId') or ''})"),
        ("流量来源", _flow_source_table(meta)),
        ("日期类型", _weekday_label(meta)),
        ("序列类型", "车道簇" if result.get("seriesKind") == "laneGroupSeries" else "转向"),
        ("时段数", result.get("periodCount", "")),
        ("平均类内流量标准差", _fmt(constraints.get("avgIntraFlowStd")) + " veh/h"),
        ("平均类内相似度", _score(constraints.get("avgIntraSimilarity"))),
        ("平均类间差异度", _fmt(constraints.get("avgInterDissimilarity"))),
        ("数据完整率", _percent(quality.get("completeRate"))),
        ("观测槽位", f"{quality.get('observedSlotCount', 0)} / {quality.get('totalSlotCount', 0)}"),
        ("转向/车道组数量", quality.get("movementCount", 0)),
    ]
    html_rows = "".join(
        f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>"
        for key, value in rows
    )
    checks = "".join(
        f"<tr><th>{html.escape(_constraint_name(key))}</th><td>{_status(value) if isinstance(value, bool) else html.escape(str(value))}</td></tr>"
        for key, value in constraints.items()
        if key not in {"avgIntraSimilarity", "avgInterDissimilarity", "avgIntraFlowStd"}
    )
    return (
        "<section><h2>概要</h2><table>"
        f"{html_rows}"
        f"{checks}"
        "</table></section>"
    )


def _chart_section(result: dict[str, Any]) -> str:
    flow_chart = result.get("flowChart") or {}
    periods = result.get("periods") or []
    if not flow_chart or not periods:
        return ""
    svg = _build_overlay_chart_svg(flow_chart, periods)
    legend = _period_legend_html(periods)
    meta = result.get("flowDateMeta") or {}
    hint = (
        f"{_flow_source_table(meta)} · {_weekday_label(meta)} · "
        f"{flow_chart.get('intervalMinutes', 5)} 分钟粒度 · veh/h"
    )
    return (
        "<section><h2>流量曲线与时段划分</h2>"
        '<div class="section-body">'
        f'<div class="muted">{html.escape(hint)}</div>'
        f'<div class="chart-wrap">{svg}</div>'
        f"{build_flow_series_legend_html(flow_chart)}"
        f"{legend}"
        '<div class="muted" style="margin-top:8px;">'
        "每个转向可通过右上角 Tab 切换原始 / 一至三次平滑曲线（15 分钟居中滑动平均）；"
        "实线=直行，长虚线=左转/掉头。背景色带为自动划分时段。"
        "</div></div></section>"
    )


def _series_vph_values(series: dict[str, Any]) -> list[Any]:
    values: list[Any] = []
    for key in FLOW_LAYER_ORDER:
        values.extend(series.get(key) or [])
    if not values:
        values = series.get("totalVph") or []
    return values


def _chart_y_limits(flow_chart: dict[str, Any]) -> tuple[float, float]:
    """Y-axis limits based on displayed series only (exclude aggregate sum)."""
    values: list[float] = []
    for series in flow_chart.get("series") or []:
        for value in _series_vph_values(series):
            if value is not None:
                values.append(float(value))
    if not values:
        return 0.0, 100.0
    peak = max(values)
    if peak <= 0:
        return 0.0, 100.0
    padded = peak * 1.08
    y_step = _nice_step(padded / 4)
    ymax = math.ceil(padded / y_step) * y_step
    return 0.0, ymax


def chart_payload_y_max(flow_chart: dict[str, Any]) -> float:
    return _chart_y_limits(flow_chart)[1]


def chart_x_axis_tick_plan(slot_minutes: int) -> tuple[int, int, int]:
    """Return minor / medium / label tick spacing in slots (one slot = slot_minutes)."""
    slot_minutes = max(1, int(slot_minutes or 5))
    minor_every = 1
    medium_every = max(1, round(30 / slot_minutes))
    label_every = max(1, round(60 / slot_minutes))
    return minor_every, medium_every, label_every


def _build_overlay_chart_svg(flow_chart: dict[str, Any], periods: list[dict[str, Any]]) -> str:
    width, height = 980, 420
    left, right, top, bottom = 56, 18, 28, 34
    plot_w = width - left - right
    plot_h = height - top - bottom
    slot_minutes = int(flow_chart.get("intervalMinutes") or 5)
    slot_count = len(flow_chart.get("times") or []) or 288

    _, ymax = _chart_y_limits(flow_chart)
    y_step = _nice_step(ymax / 4)

    def x_of_slot(slot: float) -> float:
        return left + min(1.0, max(0.0, slot / slot_count)) * plot_w

    def x_of_minutes(minutes: float) -> float:
        return left + min(1.0, max(0.0, minutes / MINUTES_PER_DAY)) * plot_w

    def y_of(value: float) -> float:
        return top + (1.0 - value / ymax) * plot_h

    parts: list[str] = [
        f'<svg viewBox="0 0 {width} {height}" style="width:100%;height:auto;display:block;">'
    ]

    for idx, period in enumerate(periods):
        start_slot = int(period.get("startSlot") or 0)
        end_slot = int(period.get("endSlot") or slot_count)
        start_min = start_slot * slot_minutes
        end_min = end_slot * slot_minutes
        color = PERIOD_COLORS[idx % len(PERIOD_COLORS)]
        x1 = x_of_minutes(start_min)
        x2 = x_of_minutes(end_min)
        band_w = max(1.0, x2 - x1)
        parts.append(
            f'<rect x="{x1:.1f}" y="{top}" width="{band_w:.1f}" height="{plot_h:.1f}" '
            f'fill="{color}" opacity="0.16" />'
        )
        parts.append(
            f'<line x1="{x2:.1f}" y1="{top}" x2="{x2:.1f}" y2="{top + plot_h}" '
            f'stroke="{color}" stroke-width="1.5" opacity="0.85" />'
        )
        if band_w >= 36:
            label_x = x1 + band_w / 2
            parts.append(
                f'<text x="{label_x:.1f}" y="{top + 14}" font-size="10" fill="{color}" '
                f'text-anchor="middle" font-weight="600">P{idx + 1}</text>'
            )
            parts.append(
                f'<text x="{label_x:.1f}" y="{top + 26}" font-size="9" fill="#cbd5e1" '
                f'text-anchor="middle">{html.escape(str(period.get("startTime")))}-'
                f'{html.escape(str(period.get("endTime")))}</text>'
            )

    for value in range(0, int(ymax) + 1, int(y_step)):
        y = y_of(float(value))
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="#1e3a5f" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{left - 8}" y="{y + 3.5}" font-size="10" fill="#8aa3bd" text-anchor="end">{value}</text>'
        )

    minor_every, medium_every, label_every = chart_x_axis_tick_plan(slot_minutes)
    times = flow_chart.get("times") or []
    axis_base = top + plot_h
    for slot in range(0, slot_count, minor_every):
        x = x_of_slot(slot)
        if slot % label_every == 0:
            tick_h = 5
            stroke = "#94a3b8"
            label = times[slot] if slot < len(times) else _slot_index_to_time(slot, slot_minutes)
            parts.append(
                f'<line x1="{x:.1f}" y1="{axis_base}" x2="{x:.1f}" y2="{axis_base + tick_h}" '
                f'stroke="{stroke}" stroke-width="1"/>'
            )
            parts.append(
                f'<text x="{x:.1f}" y="{axis_base + 18}" font-size="9" fill="#8aa3bd" '
                f'text-anchor="middle">{html.escape(str(label))}</text>'
            )
        elif slot % medium_every == 0:
            parts.append(
                f'<line x1="{x:.1f}" y1="{axis_base}" x2="{x:.1f}" y2="{axis_base + 4}" '
                f'stroke="#475569" stroke-width="1"/>'
            )
        else:
            parts.append(
                f'<line x1="{x:.1f}" y1="{axis_base}" x2="{x:.1f}" y2="{axis_base + 2}" '
                f'stroke="#1e3a5f" stroke-width="1" opacity="0.85"/>'
            )

    parts.append(
        f'<line x1="{left}" y1="{top + plot_h}" x2="{width - right}" y2="{top + plot_h}" stroke="#64748b"/>'
    )
    parts.append(
        f'<text x="{left - 28}" y="{top + plot_h / 2}" font-size="10" fill="#8aa3bd" transform="rotate(-90 {left - 28},{top + plot_h / 2})" text-anchor="middle">veh/h</text>'
    )
    parts.append(f'<g id="flowSeriesGroup" data-y-max="{ymax:.6f}"></g>')
    parts.append("</svg>")
    return "".join(parts)


def _series_path(
    values: list[Any],
    x_of_slot,
    y_of,
    slot_count: int,
) -> str:
    chunks: list[str] = []
    pen = False
    for slot in range(min(slot_count, len(values))):
        value = values[slot]
        if value is None:
            pen = False
            continue
        cmd = "L" if pen else "M"
        chunks.append(f"{cmd}{x_of_slot(slot):.1f},{y_of(float(value)):.1f}")
        pen = True
    return "".join(chunks)


def _period_legend_html(periods: list[dict[str, Any]]) -> str:
    items = []
    for idx, period in enumerate(periods):
        color = PERIOD_COLORS[idx % len(PERIOD_COLORS)]
        label = f"P{idx + 1} {period.get('startTime')}-{period.get('endTime')}"
        items.append(
            f'<span class="period-chip">'
            f'<span class="legend-swatch" style="background:{color};"></span>'
            f"{html.escape(label)}"
            f"</span>"
        )
    return f'<div class="legend">{"".join(items)}</div>'


def _period_section(result: dict[str, Any]) -> str:
    rows = []
    for idx, period in enumerate(result.get("periods") or [], start=1):
        flow_std = float(period.get("intraFlowStd") or 0)
        similarity = float(period.get("intraSimilarity") or 0)
        color = PERIOD_COLORS[(idx - 1) % len(PERIOD_COLORS)]
        dominant = "，".join(
            f"{item.get('movement')} {item.get('meanVph')}vph"
            for item in period.get("dominantMovements") or []
        )
        rows.append(
            "<tr>"
            f'<td><span class="legend-swatch" style="background:{color};"></span> {idx}</td>'
            f"<td>{html.escape(str(period.get('startTime')))}-{html.escape(str(period.get('endTime')))}</td>"
            f"<td>{period.get('durationMinutes')} 分钟</td>"
            f"<td><b>{flow_std:g}</b> veh/h</td>"
            f"<td>{_similarity_bar(similarity)} {_score(similarity)}</td>"
            f"<td>{period.get('cohesion')}</td>"
            f"<td>{period.get('structureL1')}</td>"
            f"<td>{period.get('meanTotalVph')} / {period.get('peakTotalVph')}</td>"
            f"<td>{html.escape(dominant)}</td>"
            "</tr>"
        )
    return (
        "<section><h2>自动划分时段明细</h2><table>"
        "<tr><th>#</th><th>时段</th><th>时长</th><th>类内流量标准差</th><th>类内相似度</th><th>凝聚度</th>"
        "<th>结构 L1</th><th>总流量均值/峰值</th><th>主导流向</th></tr>"
        f"{''.join(rows)}</table></section>"
    )


def _pair_section(result: dict[str, Any]) -> str:
    rows = []
    for item in result.get("adjacentPairs") or []:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('boundaryTime')))}</td>"
            f"<td>{html.escape(str(item.get('leftPeriod')))}</td>"
            f"<td>{html.escape(str(item.get('rightPeriod')))}</td>"
            f"<td>{_fmt(item.get('interDissimilarity'))}</td>"
            "</tr>"
        )
    if not rows:
        return ""
    return (
        "<section><h2>相邻时段类间差异</h2><table>"
        "<tr><th>边界</th><th>左时段</th><th>右时段</th><th>差异度</th></tr>"
        f"{''.join(rows)}</table></section>"
    )


def _baseline_section(result: dict[str, Any]) -> str:
    baseline = result.get("baseline") or {}
    rows = []
    for period in baseline.get("periods") or []:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(period.get('startTime')))}-{html.escape(str(period.get('endTime')))}</td>"
            f"<td>{period.get('intraFlowStd')} veh/h</td>"
            f"<td>{_score(period.get('intraSimilarity'))}</td>"
            f"<td>{period.get('intraCost')}</td>"
            "</tr>"
        )
    return (
        "<section><h2>固定四时段基线对比</h2><table>"
        f"<tr><th>平均类内流量标准差</th><td colspan='3'>{_fmt(baseline.get('avgIntraFlowStd'))} veh/h</td></tr>"
        f"<tr><th>平均类内相似度</th><td colspan='3'>{_score(baseline.get('avgIntraSimilarity'))}</td></tr>"
        f"<tr><th>平均类间差异度</th><td colspan='3'>{_fmt(baseline.get('avgInterDissimilarity'))}</td></tr>"
        "<tr><th>时段</th><th>类内流量标准差</th><th>类内相似度</th><th>类内代价</th></tr>"
        f"{''.join(rows)}</table></section>"
    )


def _raw_json_section(result: dict[str, Any]) -> str:
    payload = dict(result)
    payload.pop("flowChart", None)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return f"<section><h2>原始结果</h2><pre>{html.escape(text)}</pre></section>"


def _slot_index_to_time(slot: int, slot_minutes: int) -> str:
    minutes = slot * max(1, int(slot_minutes))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _nice_step(raw: float) -> float:
    if raw <= 0:
        return 25.0
    power = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 2.5, 5, 10):
        if raw <= mult * power:
            return mult * power
    return 10 * power


def _similarity_bar(value: float) -> str:
    width = max(0.0, min(100.0, value * 100.0))
    return f"<span class='bar-wrap'><span class='bar' style='width:{width:.1f}%'></span></span>"


def _status(value: Any) -> str:
    ok = bool(value)
    return f"<span class='{'ok' if ok else 'bad'}'>{'通过' if ok else '未通过'}</span>"


def _percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return ""


def _score(value: Any) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return ""


def _fmt(value: Any) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return ""


def _weekday_label(meta: dict[str, Any]) -> str:
    labels = [label for label in (meta.get("weekdayLabels") or []) if label]
    if labels:
        return "、".join(labels)
    if meta.get("profileMode"):
        return "历史均值 profile"
    return str(meta.get("date") or "")


def _flow_source_table(meta: dict[str, Any]) -> str:
    if meta.get("profileMode"):
        return "MySQL dws_lane_flow_5min_mm 历史均值"
    return "PostgreSQL 原始 5 分钟车道流量"


def _constraint_name(key: str) -> str:
    return {
        "periodCountWithinRange": "时段数 3-15",
        "minDurationSatisfied": "最小时长不少于 15 分钟",
        "continuousCoverage": "全天连续覆盖",
    }.get(key, key)
