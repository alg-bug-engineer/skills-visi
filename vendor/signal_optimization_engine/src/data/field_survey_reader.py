"""PostgreSQL 交通组织调研 DWD 图层读取。"""

from __future__ import annotations

import json
from typing import Any

from preprocessing.field_survey.taxonomy import ISSUE_TYPES

from data.metric_reader import (
    METRIC_CATALOG,
    _dim_inter_qualified,
    _qident,
    _timing_schema,
    _to_float,
    _value_stats,
    parse_geom_center,
)

FIELD_SURVEY_TABLE = "dwd_tfc_field_survey_inter_issue"


def field_survey_issue_types_for_api() -> list[str]:
    return list(ISSUE_TYPES)


def fetch_field_survey_types(conn, *, report_batch: str = "jinan_20260609") -> list[dict[str, Any]]:
    schema = _timing_schema()
    qualified = f"{_qident(schema)}.{_qident(FIELD_SURVEY_TABLE)}"
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT issue_type, COUNT(*) AS total_count
            FROM {qualified}
            WHERE is_deleted = 0 AND report_batch = %s
            GROUP BY issue_type
            ORDER BY total_count DESC
            """,
            (report_batch,),
        )
        rows = cur.fetchall()
    return [
        {
            "type": str(row["issue_type"]),
            "count": int(row["total_count"] or 0),
        }
        for row in rows
    ]


def _image_entry_url(img: dict[str, Any]) -> str:
    for key in ("image_url", "local_url", "url"):
        val = str(img.get(key) or "").strip()
        if val:
            return val
    return ""


def _collect_images_from_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    images: list[dict[str, Any]] = []
    for row in rows:
        for img in parse_image_urls(row.get("image_urls")):
            if not isinstance(img, dict):
                continue
            url = _image_entry_url(img)
            if not url or url in seen:
                continue
            seen.add(url)
            images.append(
                {
                    "imageKey": str(img.get("image_key") or ""),
                    "url": url,
                    "caption": str(img.get("caption") or img.get("caption_text") or "").strip(),
                }
            )
    return images


def fetch_field_survey_layer(
    conn,
    *,
    report_batch: str = "jinan_20260609",
    issue_type: str | None = None,
    inter_ids: list[str] | None = None,
) -> dict[str, Any]:
    """按路口聚合调研问题条数，返回 GeoJSON FeatureCollection。"""
    schema = _timing_schema()
    qualified = f"{_qident(schema)}.{_qident(FIELD_SURVEY_TABLE)}"
    cfg = METRIC_CATALOG["field_survey_issue_cnt"]

    params: list[Any] = [report_batch]
    type_filter = ""
    if issue_type and issue_type.strip() and issue_type.strip() != "全部":
        type_filter = " AND s.issue_type = %s"
        params.append(issue_type.strip())

    inter_filter = ""
    if inter_ids:
        inter_filter = " AND s.inter_id = ANY(%s)"
        params.append(inter_ids)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT s.inter_id,
                   MAX(s.inter_name) AS inter_name,
                   MAX(s.inter_name_raw) AS inter_name_raw,
                   COUNT(*) AS metric_value,
                   STRING_AGG(DISTINCT s.issue_type, '、' ORDER BY s.issue_type) AS issue_types,
                   STRING_AGG(s.issue_desc, E'\\n' ORDER BY s.issue_seq) AS issue_descs,
                   MAX(d.geom_center::text) AS geom_center
            FROM {qualified} s
            JOIN {_dim_inter_qualified()} d ON d.inter_id::text = s.inter_id
            WHERE s.is_deleted = 0
              AND s.match_status = 'matched'
              AND s.inter_id IS NOT NULL
              AND btrim(s.inter_id) <> ''
              AND s.report_batch = %s
              AND d.geom_center IS NOT NULL
              {type_filter}
              {inter_filter}
            GROUP BY s.inter_id
            """,
            params,
        )
        agg_rows = cur.fetchall()

        cur.execute(
            f"""
            SELECT s.inter_id, s.issue_type, COUNT(*) AS cnt
            FROM {qualified} s
            WHERE s.is_deleted = 0
              AND s.match_status = 'matched'
              AND s.inter_id IS NOT NULL
              AND s.report_batch = %s
              {type_filter}
              {inter_filter}
            GROUP BY s.inter_id, s.issue_type
            """,
            params,
        )
        breakdown_rows = cur.fetchall()

        detail_params: list[Any] = [report_batch]
        if issue_type and issue_type.strip() and issue_type.strip() != "全部":
            detail_params.append(issue_type.strip())
        detail_inter_filter = ""
        if inter_ids:
            detail_inter_filter = " AND s.inter_id = ANY(%s)"
            detail_params.append(inter_ids)
        elif agg_rows:
            inter_id_list = [
                str(r.get("inter_id") or "").strip() for r in agg_rows if r.get("inter_id")
            ]
            if inter_id_list:
                detail_inter_filter = " AND s.inter_id = ANY(%s)"
                detail_params.append(inter_id_list)

        cur.execute(
            f"""
            SELECT s.inter_id, s.issue_type, s.issue_seq, s.issue_desc,
                   s.recommendation_text, s.image_urls
            FROM {qualified} s
            WHERE s.is_deleted = 0
              AND s.match_status = 'matched'
              AND s.inter_id IS NOT NULL
              AND s.report_batch = %s
              {type_filter}
              {detail_inter_filter}
            ORDER BY s.inter_id, s.issue_seq, s.issue_type
            """,
            detail_params,
        )
        detail_rows = cur.fetchall()

    issues_by_inter: dict[str, list[dict[str, Any]]] = {}
    images_by_inter: dict[str, list[dict[str, Any]]] = {}
    for row in detail_rows:
        inter_id = str(row.get("inter_id") or "").strip()
        if not inter_id:
            continue
        issue_images = _collect_images_from_rows([row])
        issues_by_inter.setdefault(inter_id, []).append(
            {
                "issueType": str(row.get("issue_type") or ""),
                "issueSeq": int(row.get("issue_seq") or 0),
                "issueDesc": str(row.get("issue_desc") or "").strip(),
                "recommendationText": str(row.get("recommendation_text") or "").strip(),
                "images": issue_images,
            }
        )
        if issue_images:
            bucket = images_by_inter.setdefault(inter_id, [])
            seen_urls = {item["url"] for item in bucket}
            for img in issue_images:
                if img["url"] not in seen_urls:
                    bucket.append(img)
                    seen_urls.add(img["url"])

    breakdown_map: dict[str, list[dict[str, Any]]] = {}
    for row in breakdown_rows:
        inter_id = str(row.get("inter_id") or "").strip()
        if not inter_id:
            continue
        breakdown_map.setdefault(inter_id, []).append(
            {
                "type": str(row.get("issue_type") or ""),
                "count": int(row.get("cnt") or 0),
            }
        )
    for items in breakdown_map.values():
        items.sort(key=lambda x: -x["count"])

    features: list[dict[str, Any]] = []
    value_numbers: list[float] = []
    type_label = issue_type.strip() if issue_type and issue_type.strip() else "全部"

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

        descs = str(row.get("issue_descs") or "").split("\n")
        issue_desc = descs[0][:512] if descs else ""
        inter_name = str(row.get("inter_name") or row.get("inter_name_raw") or "").strip()
        survey_images = images_by_inter.get(inter_id, [])
        survey_issues = issues_by_inter.get(inter_id, [])

        props: dict[str, Any] = {
            "interId": inter_id,
            "interName": inter_name,
            "centerLon": lon,
            "centerLat": lat,
            "metricId": "field_survey_issue_cnt",
            "metricLabel": cfg["label"],
            "value": round(num, 0),
            "valueLabel": f"{int(num)} 条",
            "valueType": "numeric",
            "reportBatch": report_batch,
            "issueType": type_label if type_label != "全部" else str(row.get("issue_types") or "全部"),
            "issueDesc": issue_desc,
            "typeBreakdown": breakdown_map.get(inter_id, []),
            "surveyImages": survey_images,
            "surveyIssues": survey_issues,
            "layerKind": "field_survey",
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
    return {
        "type": "FeatureCollection",
        "metricId": "field_survey_issue_cnt",
        "metricLabel": f"{cfg['label']}（{type_label}）",
        "level": "field_survey",
        "reportBatch": report_batch,
        "issueType": type_label,
        "featureCount": len(features),
        "valueStats": stats,
        "features": features,
    }


def parse_image_urls(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []
