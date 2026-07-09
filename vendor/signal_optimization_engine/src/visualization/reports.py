"""Dependency-light HTML reports for optimization plans."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def render_plan_html(plan: dict[str, Any]) -> str:
    """Render an optimization plan as a standalone HTML report."""
    title = _plan_title(plan)
    sections = [_summary_section(plan)]
    if _is_intersection_plan(plan):
        sections.append(_intersection_section(plan))
    elif plan.get("plan_type") == "corridor_coordination":
        sections.append(_corridor_section(plan))
    elif plan.get("plan_type") == "region_optimization":
        sections.append(_region_section(plan))
    sections.append(_raw_json_section(plan))
    body = "\n".join(sections)
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
    table {{ width:100%; border-collapse:collapse; }}
    th,td {{ padding:10px 12px; border-bottom:1px solid #18375d; text-align:left; vertical-align:top; }}
    th {{ color:#8fb3d9; font-weight:600; width:220px; }}
    .bar {{ display:inline-block; height:12px; border-radius:6px; background:#34d399; min-width:2px; }}
    .muted {{ color:#8aa3bd; }}
    pre {{ margin:0; padding:14px 16px; white-space:pre-wrap; color:#d8e7f8; overflow:auto; }}
  </style>
</head>
<body>
  <header><h1>{html.escape(title)}</h1></header>
  <main>{body}</main>
</body>
</html>
"""


def write_plan_html(plan: dict[str, Any], output_path: str | Path) -> None:
    """Write a standalone HTML report."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_plan_html(plan), encoding="utf-8")


def _plan_title(plan: dict[str, Any]) -> str:
    if _is_intersection_plan(plan):
        return f"路口优化方案 - {plan.get('intersectionId', 'UNKNOWN')}"
    if plan.get("plan_type") == "corridor_coordination":
        return f"干线协调方案 - {plan.get('corridor_id', 'UNKNOWN')}"
    if plan.get("plan_type") == "region_optimization":
        return f"区域优化方案 - {plan.get('region_id', 'UNKNOWN')}"
    return "信号优化方案"


def _summary_section(plan: dict[str, Any]) -> str:
    rows = []
    for key, value in _summary_items(plan):
        rows.append(f"<tr><th>{html.escape(key)}</th><td>{html.escape(str(value))}</td></tr>")
    return f"<section><h2>概要</h2><table>{''.join(rows)}</table></section>"


def _summary_items(plan: dict[str, Any]) -> list[tuple[str, Any]]:
    if _is_intersection_plan(plan):
        return [
            ("层级", "路口优化"),
            ("路口 ID", plan.get("intersectionId", "")),
            ("周期", plan.get("cycleTime", "")),
            ("阶段数", len(plan.get("phaseStageTimingList") or [])),
            ("求解器", (plan.get("meta") or {}).get("solver", "")),
        ]
    if plan.get("plan_type") == "corridor_coordination":
        c = plan.get("coordination") or {}
        return [
            ("层级", "干线优化"),
            ("干线 ID", plan.get("corridor_id", "")),
            ("周期", c.get("cycle_s", "")),
            ("带宽", c.get("bandwidth_s", "")),
            ("总延误", c.get("total_delay_s", "")),
            ("节点数", len(c.get("nodes") or [])),
        ]
    if plan.get("plan_type") == "region_optimization":
        k = plan.get("kpis") or {}
        return [
            ("层级", "区域优化"),
            ("区域 ID", plan.get("region_id", "")),
            ("干线数", k.get("corridor_count", 0)),
            ("独立路口数", k.get("standalone_intersection_count", 0)),
            ("平均干线带宽", k.get("avg_corridor_bandwidth_s", 0)),
            ("总干线延误", k.get("total_corridor_delay_s", 0)),
        ]
    return [("层级", plan.get("plan_type", "unknown"))]


def _intersection_section(plan: dict[str, Any]) -> str:
    rows = []
    cycle = max(float(plan.get("cycleTime") or 1), 1.0)
    for stage in plan.get("phaseStageTimingList") or []:
        green = float(stage.get("greenTime") or 0)
        width = max(2, min(100, green / cycle * 100))
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(stage.get('phaseStageName') or stage.get('phaseStageId')))}</td>"
            f"<td>{green:g}s</td>"
            f"<td><span class='bar' style='width:{width:.1f}%'></span></td>"
            f"<td>{html.escape(str(stage.get('phaseSaturation', '')))}</td>"
            "</tr>"
        )
    return (
        "<section><h2>阶段配时</h2><table>"
        "<tr><th>阶段</th><th>绿灯</th><th>绿信比</th><th>饱和度</th></tr>"
        f"{''.join(rows)}</table></section>"
    )


def _corridor_section(plan: dict[str, Any]) -> str:
    rows = []
    for node in (plan.get("coordination") or {}).get("nodes") or []:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(node.get('intersection_id', '')))}</td>"
            f"<td>{html.escape(str(node.get('offset_s', '')))}</td>"
            f"<td>{html.escape(str(node.get('coordinated_green_s', '')))}</td>"
            f"<td>{html.escape(str(node.get('green_ratio', '')))}</td>"
            f"<td>{html.escape(str(node.get('webster_delay_s', '')))}</td>"
            "</tr>"
        )
    return (
        "<section><h2>干线节点</h2><table>"
        "<tr><th>路口</th><th>相位差(s)</th><th>协调绿(s)</th><th>绿信比</th><th>延误(s)</th></tr>"
        f"{''.join(rows)}</table></section>"
    )


def _region_section(plan: dict[str, Any]) -> str:
    return (
        "<section><h2>区域组成</h2><table>"
        f"<tr><th>干线方案</th><td>{len(plan.get('corridor_plans') or [])}</td></tr>"
        f"<tr><th>独立路口方案</th><td>{len(plan.get('intersection_plans') or [])}</td></tr>"
        "</table></section>"
    )


def _raw_json_section(plan: dict[str, Any]) -> str:
    text = json.dumps(plan, ensure_ascii=False, indent=2)
    return f"<section><h2>原始结果</h2><pre>{html.escape(text)}</pre></section>"


def _is_intersection_plan(plan: dict[str, Any]) -> bool:
    return plan.get("planType") == "single_point" or plan.get("plan_type") == "single_point"
