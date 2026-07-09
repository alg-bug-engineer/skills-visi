"""PostgreSQL 人工调查 DWD 图层读取。"""

from __future__ import annotations

from typing import Any

from preprocessing.manual_survey.taxonomy import SURVEY_PROBLEM_TYPES, TIME_PERIODS

from data.metric_reader import (
    METRIC_CATALOG,
    _dim_inter_qualified,
    _qident,
    _timing_schema,
    _to_float,
    _value_stats,
    parse_geom_center,
)

MANUAL_SURVEY_TABLE = "dwd_ctl_inter_manual_survey_issue"

PROBLEM_TYPE_COLORS: dict[str, str] = {
    "空放": "#d62728",
    "溢出": "#ff7f0e",
    "人车冲突": "#e377c2",
    "过饱和": "#9467bd",
    "失衡": "#8c564b",
    "车车冲突": "#bcbd22",
    "机非冲突": "#17becf",
    "行人闯红灯": "#aec7e8",
    "车道利用率低": "#c5b0d5",
    "变道干扰": "#ff9896",
    "出口临停": "#98df8a",
}


def manual_survey_problem_types_for_api() -> list[str]:
    return list(SURVEY_PROBLEM_TYPES)


def manual_survey_time_periods_for_api() -> list[str]:
    return list(TIME_PERIODS)


def fetch_manual_survey_types(conn, *, survey_batch: str = "jinan_2025") -> list[dict[str, Any]]:
    schema = _timing_schema()
    qualified = f"{_qident(schema)}.{_qident(MANUAL_SURVEY_TABLE)}"
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT problem_type, SUM(issue_record_cnt) AS total_count
            FROM {qualified}
            WHERE is_deleted = 0 AND survey_batch = %s
            GROUP BY problem_type
            ORDER BY total_count DESC
            """,
            (survey_batch,),
        )
        rows = cur.fetchall()
    return [
        {
            "type": str(row["problem_type"]),
            "count": int(row["total_count"] or 0),
        }
        for row in rows
    ]


def _resolve_coords(
    row: dict[str, Any],
    geom_center: Any,
) -> tuple[float, float] | None:
    center = parse_geom_center(geom_center)
    if center:
        return center
    lon = _to_float(row.get("survey_lon"))
    lat = _to_float(row.get("survey_lat"))
    if lon is not None and lat is not None:
        return lon, lat
    return None


def fetch_manual_survey_layer(
    conn,
    *,
    survey_batch: str = "jinan_2025",
    time_period: str | None = None,
    problem_type: str | None = None,
    inter_ids: list[str] | None = None,
) -> dict[str, Any]:
    """按路口聚合调查问题记录数，返回 GeoJSON FeatureCollection。"""
    schema = _timing_schema()
    qualified = f"{_qident(schema)}.{_qident(MANUAL_SURVEY_TABLE)}"
    cfg = METRIC_CATALOG["manual_survey_issue_cnt"]

    params: list[Any] = [survey_batch]
    time_filter = ""
    if time_period and time_period.strip() and time_period.strip() != "全部":
        time_filter = " AND s.time_period = %s"
        params.append(time_period.strip())

    type_filter = ""
    if problem_type and problem_type.strip() and problem_type.strip() != "全部":
        type_filter = " AND s.problem_type = %s"
        params.append(problem_type.strip())

    inter_filter = ""
    if inter_ids:
        inter_filter = " AND s.inter_id = ANY(%s)"
        params.append(inter_ids)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT s.inter_id,
                   s.source_key,
                   MAX(s.inter_name) AS inter_name,
                   MAX(s.inter_name_raw) AS inter_name_raw,
                   SUM(s.issue_record_cnt) AS metric_value,
                   STRING_AGG(DISTINCT s.time_period, '、' ORDER BY s.time_period) AS time_periods,
                   STRING_AGG(DISTINCT s.problem_type, '、' ORDER BY s.problem_type) AS problem_types,
                   STRING_AGG(s.problem_desc, E'\\n' ORDER BY s.issue_record_cnt DESC) AS problem_descs,
                   MAX(s.survey_lon) AS survey_lon,
                   MAX(s.survey_lat) AS survey_lat,
                   MAX(s.match_status) AS match_status,
                   MAX(d.geom_center::text) AS geom_center
            FROM {qualified} s
            LEFT JOIN {_dim_inter_qualified()} d ON d.inter_id::text = s.inter_id
            WHERE s.is_deleted = 0
              AND s.survey_batch = %s
              AND (s.inter_id IS NOT NULL AND btrim(s.inter_id) <> '' OR s.survey_lon IS NOT NULL)
              {time_filter}
              {type_filter}
              {inter_filter}
            GROUP BY s.inter_id, s.source_key
            """,
            params,
        )
        agg_rows = cur.fetchall()

        cur.execute(
            f"""
            SELECT s.inter_id, s.source_key, s.problem_type, SUM(s.issue_record_cnt) AS cnt
            FROM {qualified} s
            WHERE s.is_deleted = 0
              AND s.survey_batch = %s
              {time_filter}
              {type_filter}
              {inter_filter}
            GROUP BY s.inter_id, s.source_key, s.problem_type
            """,
            params,
        )
        breakdown_rows = cur.fetchall()

        # 时段分布
        period_params: list[Any] = [survey_batch]
        period_time_filter = ""
        if time_period and time_period.strip() and time_period.strip() != "全部":
            period_time_filter = " AND s.time_period = %s"
            period_params.append(time_period.strip())
        period_type_filter = ""
        if problem_type and problem_type.strip() and problem_type.strip() != "全部":
            period_type_filter = " AND s.problem_type = %s"
            period_params.append(problem_type.strip())
        if inter_ids:
            period_params.append(inter_ids)

        cur.execute(
            f"""
            SELECT s.inter_id, s.source_key, s.time_period, SUM(s.issue_record_cnt) AS cnt
            FROM {qualified} s
            WHERE s.is_deleted = 0
              AND s.survey_batch = %s
              {period_time_filter}
              {period_type_filter}
              {inter_filter}
            GROUP BY s.inter_id, s.source_key, s.time_period
            """,
            period_params,
        )
        period_breakdown_rows = cur.fetchall()

    breakdown_map: dict[str, list[dict[str, Any]]] = {}
    for row in breakdown_rows:
        key = _feature_key(row)
        if not key:
            continue
        breakdown_map.setdefault(key, []).append(
            {
                "type": str(row.get("problem_type") or ""),
                "count": int(row.get("cnt") or 0),
            }
        )
    for items in breakdown_map.values():
        items.sort(key=lambda x: -x["count"])

    period_map: dict[str, list[dict[str, Any]]] = {}
    for row in period_breakdown_rows:
        key = _feature_key(row)
        if not key:
            continue
        period_map.setdefault(key, []).append(
            {
                "period": str(row.get("time_period") or ""),
                "count": int(row.get("cnt") or 0),
            }
        )
    for items in period_map.values():
        items.sort(key=lambda x: -x["count"])

    features: list[dict[str, Any]] = []
    value_numbers: list[float] = []

    type_label = (
        problem_type.strip()
        if problem_type and problem_type.strip() != "全部"
        else "全部"
    )
    period_label = (
        time_period.strip()
        if time_period and time_period.strip() != "全部"
        else "全部时段"
    )

    for row in agg_rows:
        feature_key = _feature_key(row)
        if not feature_key:
            continue
        coords = _resolve_coords(row, row.get("geom_center"))
        if not coords:
            continue
        lon, lat = coords
        num = _to_float(row.get("metric_value"))
        if num is None:
            continue

        inter_id = str(row.get("inter_id") or "").strip() or None
        inter_name = str(row.get("inter_name") or row.get("inter_name_raw") or "").strip()
        descs = str(row.get("problem_descs") or "").split("\n")
        problem_desc = descs[0][:512] if descs else ""

        dominant_type = ""
        type_breakdown = breakdown_map.get(feature_key, [])
        if type_breakdown:
            dominant_type = type_breakdown[0]["type"]

        point_color = None
        if type_label != "全部":
            point_color = PROBLEM_TYPE_COLORS.get(type_label)
        elif dominant_type:
            point_color = PROBLEM_TYPE_COLORS.get(dominant_type)

        props: dict[str, Any] = {
            "interId": inter_id or feature_key,
            "interName": inter_name,
            "centerLon": lon,
            "centerLat": lat,
            "metricId": "manual_survey_issue_cnt",
            "metricLabel": cfg["label"],
            "value": round(num, 0),
            "valueLabel": f"{int(num)} 条",
            "valueType": "numeric",
            "surveyBatch": survey_batch,
            "timePeriod": period_label,
            "problemType": type_label if type_label != "全部" else str(row.get("problem_types") or "全部"),
            "problemDesc": problem_desc,
            "typeBreakdown": type_breakdown,
            "periodBreakdown": period_map.get(feature_key, []),
            "matchStatus": str(row.get("match_status") or ""),
            "layerKind": "manual_survey",
        }
        if point_color:
            props["color"] = point_color

        value_numbers.append(num)
        features.append(
            {
                "type": "Feature",
                "id": feature_key,
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props,
            }
        )

    stats = _value_stats(value_numbers)
    return {
        "type": "FeatureCollection",
        "metricId": "manual_survey_issue_cnt",
        "metricLabel": f"{cfg['label']}（{period_label} · {type_label}）",
        "level": "manual_survey",
        "surveyBatch": survey_batch,
        "timePeriod": period_label,
        "problemType": type_label,
        "featureCount": len(features),
        "valueStats": stats,
        "features": features,
    }


def _feature_key(row: dict[str, Any]) -> str:
    inter_id = str(row.get("inter_id") or "").strip()
    if inter_id:
        return inter_id
    return str(row.get("source_key") or "").strip()
