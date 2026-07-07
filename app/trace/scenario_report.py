"""Build scene-cognition checklist summary for diagnosis output."""

from __future__ import annotations

from typing import Any


def build_scenario_report(
    checklist_queries: list[dict[str, Any]] | None,
    metrics: dict[str, Any] | None = None,
    *,
    ticket: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not checklist_queries:
        return {"available": False, "reason": "no_checklist"}

    issues: list[dict[str, Any]] = []
    for item in checklist_queries:
        issues.append(
            {
                "item_id": item.get("item_id"),
                "label": item.get("label") or item.get("item_id"),
                "status": item.get("status"),
                "summary": item.get("summary"),
                "table": item.get("table"),
            }
        )

    has_data = [item for item in issues if item.get("status") == "has_data"]
    no_data = [item for item in issues if item.get("status") == "no_data"]
    dimensions = _build_dimensions(metrics or {}, ticket or {}, has_data, no_data)

    return {
        "available": True,
        "dimensions": dimensions,
        "issues": issues,
        "summary": {
            "total": len(issues),
            "has_data": len(has_data),
            "no_data": len(no_data),
        },
    }


def checklist_data_gaps(scenario_report: dict[str, Any]) -> list[str]:
    if not scenario_report.get("available"):
        return []
    gaps: list[str] = []
    for issue in scenario_report.get("issues") or []:
        if issue.get("status") == "no_data":
            label = issue.get("label") or issue.get("item_id")
            gaps.append(f"{label}数据不足")
    return gaps


def _build_dimensions(
    metrics: dict[str, Any],
    ticket: dict[str, Any],
    has_data: list[dict[str, Any]],
    no_data: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    dimensions: list[dict[str, Any]] = []
    queue_ratio = metrics.get("queue_ratio")
    saturation = metrics.get("saturation")

    if queue_ratio is not None:
        status = "warning" if float(queue_ratio) >= 0.8 else "normal"
        dimensions.append(
            {
                "dimension": "demand",
                "status": status,
                "summary": f"目标方向排队比 {queue_ratio}",
            }
        )
    if saturation is not None:
        status = "warning" if float(saturation) >= 0.85 else "normal"
        dimensions.append(
            {
                "dimension": "capacity",
                "status": status,
                "summary": f"目标方向饱和度 {saturation}",
            }
        )

    if no_data:
        dimensions.append(
            {
                "dimension": "data_quality",
                "status": "gap",
                "summary": f"{len(no_data)} 项检查单数据缺失",
            }
        )
    elif has_data:
        dimensions.append(
            {
                "dimension": "data_quality",
                "status": "ok",
                "summary": f"检查单 {len(has_data)} 项有数据",
            }
        )

    direction = ticket.get("direction")
    if direction:
        dimensions.append(
            {
                "dimension": "spatial",
                "status": "ok",
                "summary": f"目标方向 {direction}{ticket.get('movement', '直行')}",
            }
        )
    return dimensions
