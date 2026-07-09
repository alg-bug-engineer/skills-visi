"""PostgreSQL 投诉 DWD 图层读取。"""

from __future__ import annotations

import os
from typing import Any

from data.metric_reader import (
    METRIC_CATALOG,
    _dim_inter_qualified,
    _qident,
    _timing_schema,
    _to_float,
    _value_stats,
    parse_geom_center,
)

COMPLAINT_TABLE = "dwd_tfc_complaint_inter_issue"


def complaint_types_for_api() -> list[str]:
    return [
        "信号配时不合理",
        "左转掉头通行困难",
        "直行放行不足",
        "信号相位/放行顺序不合理",
        "车道设置与渠化问题",
        "信号设施遮挡或标识不清",
        "信号故障或运行异常",
        "施工与临时交通影响",
        "拥堵与通行效率低",
        "行人非机动车冲突",
        "监控执法相关诉求",
        "其他综合诉求",
    ]


def fetch_complaint_types(conn, *, stat_period: str = "2025") -> list[dict[str, Any]]:
    schema = _timing_schema()
    qualified = f"{_qident(schema)}.{_qident(COMPLAINT_TABLE)}"
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT complaint_type, SUM(complaint_count) AS total_count
            FROM {qualified}
            WHERE is_deleted = 0 AND stat_period = %s
            GROUP BY complaint_type
            ORDER BY total_count DESC
            """,
            (stat_period,),
        )
        rows = cur.fetchall()
    return [
        {
            "type": str(row["complaint_type"]),
            "count": int(row["total_count"] or 0),
        }
        for row in rows
    ]


def fetch_complaint_layer(
    conn,
    *,
    stat_period: str = "2025",
    complaint_type: str | None = None,
    inter_ids: list[str] | None = None,
) -> dict[str, Any]:
    """按路口聚合投诉条数，返回与 fetch_metric_layer 兼容的 GeoJSON 结构。"""
    schema = _timing_schema()
    qualified = f"{_qident(schema)}.{_qident(COMPLAINT_TABLE)}"
    cfg = METRIC_CATALOG["complaint_count"]

    params: list[Any] = [stat_period]
    type_filter = ""
    if complaint_type and complaint_type.strip() and complaint_type.strip() != "全部":
        type_filter = " AND c.complaint_type = %s"
        params.append(complaint_type.strip())

    inter_filter = ""
    if inter_ids:
        inter_filter = " AND c.inter_id = ANY(%s)"
        params.append(inter_ids)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT c.inter_id,
                   MAX(c.inter_name) AS inter_name,
                   SUM(c.complaint_count) AS metric_value,
                   STRING_AGG(DISTINCT c.complaint_type, '、' ORDER BY c.complaint_type) AS complaint_types,
                   STRING_AGG(c.core_problem_desc, E'\\n' ORDER BY c.complaint_count DESC) AS problem_descs,
                   MAX(d.geom_center::text) AS geom_center
            FROM {qualified} c
            JOIN {_dim_inter_qualified()} d ON d.inter_id::text = c.inter_id
            WHERE c.is_deleted = 0
              AND c.match_status = 'matched'
              AND c.inter_id IS NOT NULL
              AND btrim(c.inter_id) <> ''
              AND c.stat_period = %s
              AND d.geom_center IS NOT NULL
              {type_filter}
              {inter_filter}
            GROUP BY c.inter_id
            """,
            params,
        )
        agg_rows = cur.fetchall()

        cur.execute(
            f"""
            SELECT c.inter_id, c.complaint_type, SUM(c.complaint_count) AS cnt
            FROM {qualified} c
            WHERE c.is_deleted = 0
              AND c.match_status = 'matched'
              AND c.inter_id IS NOT NULL
              AND c.stat_period = %s
              {type_filter}
              {inter_filter}
            GROUP BY c.inter_id, c.complaint_type
            """,
            params,
        )
        breakdown_rows = cur.fetchall()

    breakdown_map: dict[str, list[dict[str, Any]]] = {}
    for row in breakdown_rows:
        inter_id = str(row.get("inter_id") or "").strip()
        if not inter_id:
            continue
        breakdown_map.setdefault(inter_id, []).append(
            {
                "type": str(row.get("complaint_type") or ""),
                "count": int(row.get("cnt") or 0),
            }
        )
    for items in breakdown_map.values():
        items.sort(key=lambda x: -x["count"])

    features: list[dict[str, Any]] = []
    value_numbers: list[float] = []

    for row in agg_rows:
        inter_id = str(row.get("inter_id") or "").strip()
        if not inter_id:
            continue
        center = parse_geom_center(row.get("geom_center"))
        if not center:
            continue
        lon, lat = center
        num = _to_float(row.get("metric_value"))
        if num is None:
            continue

        descs = str(row.get("problem_descs") or "").split("\n")
        core_desc = descs[0][:512] if descs else ""
        inter_name = str(row.get("inter_name") or "").strip()
        type_label = (
            complaint_type.strip()
            if complaint_type and complaint_type.strip() != "全部"
            else str(row.get("complaint_types") or "全部类型")
        )

        props: dict[str, Any] = {
            "interId": inter_id,
            "interName": inter_name,
            "centerLon": lon,
            "centerLat": lat,
            "metricId": "complaint_count",
            "metricLabel": cfg["label"],
            "value": round(num, 0),
            "valueLabel": f"{int(num)} 件",
            "valueType": "numeric",
            "statPeriod": stat_period,
            "complaintType": type_label,
            "coreProblemDesc": core_desc,
            "typeBreakdown": breakdown_map.get(inter_id, []),
            "layerKind": "complaint",
        }
        value_numbers.append(num)
        features.append(
            {
                "type": "Feature",
                "id": inter_id,
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props,
            }
        )

    stats = _value_stats(value_numbers)
    type_label = complaint_type.strip() if complaint_type and complaint_type.strip() else "全部"
    return {
        "type": "FeatureCollection",
        "metricId": "complaint_count",
        "metricLabel": f"{cfg['label']}（{type_label}）",
        "level": "complaint",
        "statPeriod": stat_period,
        "complaintType": type_label,
        "featureCount": len(features),
        "valueStats": stats,
        "features": features,
    }
