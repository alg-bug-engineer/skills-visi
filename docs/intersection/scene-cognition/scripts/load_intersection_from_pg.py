"""Load intersection static and dynamic context from PostgreSQL for scene cognition.

Maps checklist items in docs/算法设计文档/交通智能体问题检查单-0614.docx to tables
described in docs/reference/PG_DATABASE_SCHEMA.md.
"""

from __future__ import annotations

import importlib.util
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

DIR8_LABELS = {
    0: "南向北",
    1: "西南→东北",
    2: "西向东",
    3: "西北→东南",
    4: "北向南",
    5: "东北→西南",
    6: "东向西",
    7: "东南→西北",
}

TURN_DIR_LABELS = {0: "方向聚合", 1: "左转", 2: "直行", 3: "右转", 4: "掉头"}
FLOW_CORRELATE_DAY_LABELS = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}
DIR8_APPROACH_LABELS = {
    0: "北",
    1: "东北",
    2: "东",
    3: "东南",
    4: "南",
    5: "西南",
    6: "西",
    7: "西北",
}
FLOW_TYPE_TURN_LABELS = {1: "直", 2: "左", 3: "右", 4: "掉"}

# PG 宽表 turn_move 编码：11=直行，12=左转，13=右转（dwd_tfc_rltn_wide_inter_ft_lane）
TURN_MOVE_STRAIGHT_CODES = frozenset({"11"})
TURN_MOVE_LEFT_CODES = frozenset({"12", "21", "22", "32"})
TURN_MOVE_RIGHT_CODES = frozenset({"13", "23"})

ROAD_LEVEL_LABELS = {
    "41000": "高速公路",
    "42000": "国道",
    "43000": "城市快速路",
    "44000": "城市主干道",
    "45000": "城市次干道",
    "47000": "城市普通道路",
    "51000": "省道",
    "52000": "县道",
    "53000": "乡道",
    "54000": "县乡村内部道路",
    "49": "小路",
}

ROAD_LEVEL_RANK = {
    "41000": 5,
    "43000": 5,
    "42000": 4,
    "44000": 4,
    "51000": 3,
    "45000": 3,
    "52000": 2,
    "47000": 2,
    "53000": 1,
    "54000": 1,
    "49": 1,
}

ROAD_LEVEL_GROUPS = {
    "41000": "快速路/高速",
    "43000": "快速路/高速",
    "42000": "主干路",
    "44000": "主干路",
    "51000": "次干路",
    "45000": "次干路",
    "52000": "支路",
    "47000": "支路",
    "53000": "支路",
    "54000": "支路",
    "49": "支路",
}

ROAD_LEVEL_CODE_ALIASES = {
    # Some PG deployments store compact road-level codes on dim_link_info.
    "1": "43000",
    "2": "42000",
    "3": "44000",
    "4": "45000",
    "5": "47000",
    "6": "52000",
}

AOI_TYPE_KEYWORDS = {
    "学校": ("学校", "小学", "中学", "大学", "学院", "幼儿园", "教育", "科教"),
    "医院": ("医院", "门诊", "卫生院", "急救", "医疗"),
    "商圈": ("商场", "商圈", "购物", "商业", "百货", "市场", "广场", "综合体"),
    "港区/园区": ("港", "园区", "物流", "产业园", "工业园", "货运"),
    "公交站": ("公交", "地铁", "车站", "客运", "枢纽", "交通设施服务"),
    "停车场": ("停车场", "停车", "车库"),
    "查验口/收费站": ("查验", "收费站", "卡口", "检查站"),
}

AOI_IMPACT_TIMES = {
    "学校": "上学/放学时段",
    "医院": "全天，早晚高峰叠加",
    "商圈": "晚高峰、周末及节假日",
    "港区/园区": "通勤及货运集中时段",
    "公交站": "早晚高峰换乘时段",
    "停车场": "到离场集中时段",
    "查验口/收费站": "通勤或货运排队时段",
    "其他": "待结合现场调查确认",
}

AOI_SEARCH_RADIUS_M = 800
AOI_AMAP_TABLE = "ods_amap_aoi_info"
POI_AMAP_TABLE = "ods_amap_poi_info"
AOI_LEGACY_SCHEMA = "gaode"
AOI_LEGACY_TABLE = "ods_aoi_info"

# POI 筛选：可能影响进口道通行的医院、学校、商场、园区及停车场出入口
POI_ACCESS_FILTER_SQL = """
    (
      (source_category = '医疗保健服务'
       AND category_l2 IN ('综合医院', '专科医院', '诊所'))
      OR (source_category = '科教文化服务' AND category_l2 = '学校')
      OR (source_category = '购物服务' AND category_l2 = '商场')
      OR (name ~ '产业园|工业园|物流园|科技园|园区'
          OR type_path ~ '产业园|工业园|物流园|科技园|园区'
          OR category_l3 ~ '产业园|工业园|物流园|科技园|园区')
      OR category_l3 IN ('停车场出入口', '停车场入口', '停车场出口')
      OR (category_l2 = '停车场'
          AND (name ~ '入口|出口|出入口'
               OR category_l3 ~ '入口|出口|出入口'))
    )
"""

AOI_IMPACT_METHODS = {
    "学校": "接送车与慢行过街需求集中，易在进口道形成临停与行人干扰",
    "医院": "就医停车、出租网约车临停和慢行过街需求，易占用进口道通行空间",
    "商圈": "购物到离场、停车进出和行人过街需求，易在进口道形成切入流",
    "港区/园区": "通勤流、货车进出和重车低速运行，易在进口道形成大车排队",
    "公交站": "公交停靠、换乘集散和慢行过街需求",
    "停车场": "停车场车辆进出形成切入/切出流，直接扰动进口道通行",
    "查验口/收费站": "排队查验或收费形成脉冲到达",
    "其他": "周边出行发生/吸引需求",
}

DEFAULT_PERIOD_WINDOWS = {
    "早高峰": ("07:00", "09:00"),
    "白平峰": ("10:00", "16:00"),
    "晚高峰": ("17:00", "19:00"),
}

OPPOSITE_DIR4 = {
    "东": "西",
    "西": "东",
    "南": "北",
    "北": "南",
    "东南": "西北",
    "西北": "东南",
    "东北": "西南",
    "西南": "东北",
}


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _step_index_from_hhmm(hhmm: str) -> int:
    """Convert HH:MM to 5-minute step_index (0-287)."""
    parts = hhmm.strip().split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    return hour * 12 + minute // 5


def _time_label(step_index: int) -> str:
    minutes = step_index * 5
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _hhmm_to_minutes(value: str) -> int | None:
    parts = value.strip().split(":")
    if not parts or not parts[0].isdigit():
        return None
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour * 60 + minute


def _period_from_step(step_index: int | None) -> str | None:
    if step_index is None:
        return None
    minutes = int(step_index) * 5
    for period, (start, end) in DEFAULT_PERIOD_WINDOWS.items():
        start_minutes = _hhmm_to_minutes(start)
        end_minutes = _hhmm_to_minutes(end)
        if start_minutes is not None and end_minutes is not None and start_minutes <= minutes < end_minutes:
            return period
    return None


def _period_tag(day_of_week: int, step_index: int | None = None) -> str:
    period = _period_from_step(step_index)
    if period == "早高峰":
        return "weekday_am_peak" if day_of_week not in {6, 7} else "weekend_am_peak"
    if period == "白平峰":
        return "weekday_off_peak" if day_of_week not in {6, 7} else "weekend_off_peak"
    if period == "晚高峰":
        return "weekday_pm_peak" if day_of_week not in {6, 7} else "weekend_pm_peak"
    if day_of_week in {6, 7}:
        return "weekend"
    return "weekday"


def _flow_correlate_day_labels(day_of_week: int) -> tuple[str, str]:
    day_label = FLOW_CORRELATE_DAY_LABELS.get(day_of_week, f"周{day_of_week}")
    type_label = "工作日" if day_of_week in {1, 2, 3, 4, 5} else "非工作日"
    return day_label, type_label


def _day_window_label(day_of_week: int, step_index: int | None = None) -> str:
    labels = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}
    day_label = labels.get(day_of_week, f"周{day_of_week}")
    period = _period_from_step(step_index)
    if period:
        start, end = DEFAULT_PERIOD_WINDOWS[period]
        return f"{day_label} {period}（{start}-{end}）"
    return f"{day_label} 全天"


def _movement_tuple(row: dict[str, Any]) -> tuple[str, int]:
    return (str(row.get("link_id") or ""), int(_as_float(row.get("turn_dir_no"))))


def _avg_by_movement(rows: list[dict[str, Any]], field: str) -> dict[str, float]:
    buckets: dict[str, list[float]] = {}
    for row in rows:
        key = _movement_key(row)
        val = row.get(field)
        if val is None:
            continue
        buckets.setdefault(key, []).append(_as_float(val))
    return {key: sum(vals) / len(vals) for key, vals in buckets.items() if vals}


def _max_by_movement(rows: list[dict[str, Any]], field: str) -> dict[str, float]:
    buckets: dict[str, float] = {}
    for row in rows:
        key = _movement_key(row)
        val = _as_float(row.get(field))
        buckets[key] = max(buckets.get(key, val), val)
    return buckets


def _dedupe_movement_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one row per link_id + turn_dir_no (dynamic queries span all step_index)."""
    seen: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        key = _movement_tuple(row)
        if key not in seen:
            seen[key] = row
    return list(seen.values())


def _read_pg(sql: str, params: dict[str, Any], limit: int = 500) -> list[dict[str, Any]]:
    from traffic_signal_agent.runtime.database import read_pg_rows

    return read_pg_rows(sql, params, limit=limit)


def _enabled_version_sql(schema: str) -> str:
    return f"(SELECT version_id FROM {schema}.dim_data_version WHERE is_enable = 1 LIMIT 1)"


def _dt_for_dow(day_of_week: int) -> str:
    """Map day_of_week (1=Mon … 7=Sun) to dt in lane_flow table coverage (20260601–20260609)."""
    start = date(2026, 6, 1)
    for offset in range(9):
        candidate = start + timedelta(days=offset)
        if candidate.isoweekday() == day_of_week:
            return candidate.strftime("%Y%m%d")
    return start.strftime("%Y%m%d")


def _safe_query(fn, *args, **kwargs) -> tuple[list[dict[str, Any]], str | None]:
    """Run a query function; return rows and optional error message."""
    try:
        return fn(*args, **kwargs), None
    except Exception as exc:
        return [], str(exc)


def _query_lane_detail(
    schema: str,
    inter_id: str,
    version_sql: str,
) -> list[dict[str, Any]]:
    sql = f"""
        SELECT inter_id, link_id, lane_id, lane_no, turn_move, lane_func_code,
               link_role, dir8_label
        FROM {schema}.dwd_tfc_rltn_wide_inter_ft_lane
        WHERE version_id = {version_sql}
          AND inter_id = :inter_id
        ORDER BY link_id, lane_no NULLS LAST
    """
    return _read_pg(sql, {"inter_id": inter_id}, limit=200)


def _query_adjacent_spacing(
    schema: str,
    channel_table: str,
    version_sql: str,
    inter_id: str,
) -> list[dict[str, Any]]:
    """Spacing per connected link and line sequence from link/inter topology."""
    link_table = "dim_link_info"
    inter_table = "dim_inter_info"
    sql = f"""
        WITH topology AS (
            SELECT w.inter_id::text AS inter_id,
                   w.link_id::text AS link_id,
                   w.link_role::text AS link_role,
                   w.dir8_label::text AS dir8_label,
                   w.dir8_code::text AS dir8_code,
                   w.lane_num::numeric AS lane_num,
                   l.length_m::numeric AS length_m,
                   l.road_level::text AS road_level,
                   CASE
                     WHEN LOWER(w.link_role) = 'entrance' THEN l.f_inter_id::text
                     WHEN LOWER(w.link_role) = 'exit' THEN l.t_inter_id::text
                     ELSE NULL
                   END AS adjacent_inter_id,
                   CASE
                     WHEN LOWER(w.link_role) = 'entrance' THEN 'upstream'
                     WHEN LOWER(w.link_role) = 'exit' THEN 'downstream'
                     ELSE ''
                   END AS relation_direction,
                   ai.inter_name::text AS adjacent_inter_name,
                   NULL::text AS line_id,
                   NULL::int AS line_seq_no
            FROM {schema}.{channel_table} w
            JOIN {schema}.{link_table} l
              ON l.link_id = w.link_id
             AND l.version_id = {version_sql}
            LEFT JOIN {schema}.{inter_table} ai
              ON ai.inter_id = CASE
                     WHEN LOWER(w.link_role) = 'entrance' THEN l.f_inter_id
                     WHEN LOWER(w.link_role) = 'exit' THEN l.t_inter_id
                     ELSE NULL
                   END
             AND ai.version_id = {version_sql}
            WHERE w.version_id = {version_sql}
              AND w.inter_id = :inter_id
              AND LOWER(w.link_role) IN ('entrance', 'exit')
        ),
        current_lines AS (
            SELECT DISTINCT ll.line_id
            FROM {schema}.{channel_table} w
            JOIN {schema}.dim_line_link_rltn ll
              ON ll.link_id = w.link_id
             AND ll.is_deleted = 0
            WHERE w.version_id = {version_sql}
              AND w.inter_id = :inter_id
        ),
        current_inter AS (
            SELECT li.line_id, li.seq_no
            FROM {schema}.dim_line_inter_rltn li
            JOIN current_lines cl ON cl.line_id = li.line_id
            WHERE li.inter_id = :inter_id
              AND li.is_deleted = 0
        ),
        line_neighbors AS (
            SELECT CAST(:inter_id AS text) AS inter_id,
                   NULL::text AS link_id,
                   (CASE WHEN nb.seq_no < ci.seq_no THEN 'entrance' ELSE 'exit' END)::text AS link_role,
                   NULL::text AS dir8_label,
                   NULL::text AS dir8_code,
                   NULL::numeric AS lane_num,
                   nb.gap_to_prev_m::numeric AS length_m,
                   NULL::text AS road_level,
                   nb.inter_id::text AS adjacent_inter_id,
                   (CASE WHEN nb.seq_no < ci.seq_no THEN 'upstream' ELSE 'downstream' END)::text AS relation_direction,
                   nb.inter_name::text AS adjacent_inter_name,
                   nb.line_id::text AS line_id,
                   nb.seq_no::int AS line_seq_no
            FROM current_inter ci
            JOIN {schema}.dim_line_inter_rltn nb
              ON nb.line_id = ci.line_id
             AND nb.is_deleted = 0
             AND nb.seq_no IN (ci.seq_no - 1, ci.seq_no + 1)
        )
        SELECT inter_id, link_id, link_role, dir8_label, dir8_code, lane_num,
               length_m, road_level, adjacent_inter_id, relation_direction,
               adjacent_inter_name, line_id, line_seq_no
        FROM topology
        UNION ALL
        SELECT inter_id, link_id, link_role, dir8_label, dir8_code, lane_num,
               length_m, road_level, adjacent_inter_id, relation_direction,
               adjacent_inter_name, line_id, line_seq_no
        FROM line_neighbors
        ORDER BY relation_direction, line_seq_no NULLS LAST, link_role
    """
    return _read_pg(sql, {"inter_id": inter_id}, limit=40)


def _access_type_label(name: Any, raw_type: Any, category_detail: Any = None) -> str:
    text = f"{name or ''} {raw_type or ''} {category_detail or ''}"
    if any(keyword in text for keyword in ("停车场出入口", "停车场入口", "停车场出口", "出入口")):
        return "停车场"
    for label, keywords in AOI_TYPE_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return label
    return "其他"


def _aoi_type_label(name: Any, raw_type: Any) -> str:
    return _access_type_label(name, raw_type)


def _access_role_label(name: Any, category_detail: Any = None) -> str | None:
    text = f"{name or ''} {category_detail or ''}"
    if "出入口" in text:
        return "出入口"
    if "入口" in text:
        return "入口"
    if "出口" in text:
        return "出口"
    return None


def _aoi_impact_time(aoi_type: str) -> str:
    return AOI_IMPACT_TIMES.get(aoi_type, AOI_IMPACT_TIMES["其他"])


def _aoi_impact_method(aoi_type: str) -> str:
    return AOI_IMPACT_METHODS.get(aoi_type, AOI_IMPACT_METHODS["其他"])


def _column_expr(columns: set[str], candidates: tuple[str, ...], fallback: str = "NULL") -> str:
    for column in candidates:
        if column in columns:
            return column
    return fallback


def _aoi_geometry_point_expr(column: str, column_types: dict[str, str]) -> str:
    column_type = column_types.get(column)
    if column_type == "geometry":
        return f"ST_Centroid(ST_SetSRID({column}, 4326))"
    if column_type == "geography":
        return f"ST_Centroid({column}::geometry)"
    return f"ST_Centroid(ST_SetSRID(ST_GeomFromText({column}), 4326))"


def _pg_table_exists(schema: str, table: str) -> bool:
    rows = _read_pg(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = :schema
          AND table_name = :table
        LIMIT 1
        """,
        {"schema": schema, "table": table},
        limit=1,
    )
    return bool(rows)


def _build_nearby_access_sql(source_cte_sql: str) -> str:
    return f"""
        WITH inter AS (
            SELECT ST_SetSRID(ST_GeomFromText(:geom_center), 4326) AS geom
        ),
        source AS (
            {source_cte_sql}
        ),
        nearby AS (
            SELECT source_id, name, raw_type, category_detail, record_kind,
                   ST_Distance(source.geom::geography, inter.geom::geography) AS distance_m,
                   ST_X(source.geom) - ST_X(inter.geom) AS dx,
                   ST_Y(source.geom) - ST_Y(inter.geom) AS dy
            FROM source, inter
            WHERE source.geom IS NOT NULL
              AND name <> ''
              AND ST_DWithin(source.geom::geography, inter.geom::geography, {AOI_SEARCH_RADIUS_M})
        )
        SELECT source_id, name, raw_type, category_detail, record_kind,
               ROUND(distance_m::numeric, 1) AS distance_m,
               CASE
                 WHEN ABS(dx) >= ABS(dy) AND dx >= 0 THEN '东侧'
                 WHEN ABS(dx) >= ABS(dy) AND dx < 0 THEN '西侧'
                 WHEN dy >= 0 THEN '北侧'
                 ELSE '南侧'
               END AS direction
        FROM nearby
        ORDER BY distance_m ASC
        LIMIT 30
    """


def _build_nearby_aoi_sql(aoi_cte_sql: str) -> str:
    return _build_nearby_access_sql(aoi_cte_sql)


def _format_access_source_rows(rows: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen_types: dict[str, int] = {}
    for row in rows:
        category_detail = row.get("category_detail")
        access_type = _access_type_label(row.get("name"), row.get("raw_type"), category_detail)
        seen_types[access_type] = seen_types.get(access_type, 0) + 1
        # Keep the closest examples per type so the report highlights major surrounding attractors.
        if seen_types[access_type] > 3 and len(result) >= 12:
            continue
        distance_m = _as_float(row.get("distance_m"))
        direction = str(row.get("direction") or "")
        record_kind = str(row.get("record_kind") or "aoi")
        access_role = _access_role_label(row.get("name"), category_detail)
        item: dict[str, Any] = {
            "type": access_type,
            "name": row.get("name"),
            "raw_type": row.get("raw_type"),
            "distance_m": round(distance_m, 1),
            "direction": direction,
            "directionDistance": f"{direction} {distance_m:.0f}m" if direction and distance_m else "",
            "impactTime": _aoi_impact_time(access_type),
            "impactMethod": _aoi_impact_method(access_type),
            "source": source,
            "recordKind": record_kind,
        }
        if row.get("source_id"):
            item["id"] = row.get("source_id")
        if category_detail:
            item["categoryDetail"] = category_detail
        if access_role:
            item["accessRole"] = access_role
        result.append(item)
        if len(result) >= 12:
            break
    return result


def _format_aoi_source_rows(rows: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    return _format_access_source_rows(rows, source)


def _merge_access_source_rows(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge AOI/POI hits, preferring closer POI access points on duplicate names."""
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in sorted(
        (item for group in groups for item in group),
        key=lambda item: (
            0 if item.get("recordKind") == "poi" and item.get("accessRole") else 1,
            _as_float(item.get("distance_m"), default=99999.0),
        ),
    ):
        key = (str(row.get("type") or ""), str(row.get("name") or ""))
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
        if len(merged) >= 12:
            break
    return merged


def _query_aoi_sources_amap(flow_schema: str, geom_center: str) -> list[dict[str, Any]]:
    """Query AOIs from xianchang.ods_amap_aoi_info (GCJ-02 center geom + type_path)."""
    source = f"{flow_schema}.{AOI_AMAP_TABLE}"
    aoi_cte_sql = f"""
            SELECT aoi_id AS source_id, name, type_path AS raw_type,
                   NULL::text AS category_detail, 'aoi'::text AS record_kind, geom
            FROM {flow_schema}.{AOI_AMAP_TABLE}
            WHERE is_deleted = 0
    """
    rows = _read_pg(_build_nearby_aoi_sql(aoi_cte_sql), {"geom_center": geom_center}, limit=30)
    return _format_aoi_source_rows(rows, source)


def _query_poi_access_points_amap(flow_schema: str, geom_center: str) -> list[dict[str, Any]]:
    """Query POI access points that may affect approach-road traffic."""
    source = f"{flow_schema}.{POI_AMAP_TABLE}"
    poi_cte_sql = f"""
            SELECT poi_id AS source_id, name, type_path AS raw_type,
                   category_l3 AS category_detail, 'poi'::text AS record_kind, geom
            FROM {flow_schema}.{POI_AMAP_TABLE}
            WHERE is_deleted = 0
              AND {POI_ACCESS_FILTER_SQL.strip()}
    """
    rows = _read_pg(_build_nearby_access_sql(poi_cte_sql), {"geom_center": geom_center}, limit=30)
    return _format_access_source_rows(rows, source)


def _query_aoi_sources_legacy(geom_center: str) -> list[dict[str, Any]]:
    """Fallback: query gaode.ods_aoi_info with dynamic column detection."""
    column_rows = _read_pg(
        """
        SELECT column_name, data_type, udt_name
        FROM information_schema.columns
        WHERE table_schema = :schema
          AND table_name = :table
        """,
        {"schema": AOI_LEGACY_SCHEMA, "table": AOI_LEGACY_TABLE},
        limit=200,
    )
    columns = {str(row.get("column_name")) for row in column_rows if row.get("column_name")}
    column_types = {
        str(row.get("column_name")): str(row.get("udt_name") or row.get("data_type") or "")
        for row in column_rows
        if row.get("column_name")
    }
    if not columns:
        return []

    name_expr = _column_expr(columns, ("aoi_name", "name", "poi_name", "title"), "''")
    type_expr = _column_expr(columns, ("aoi_type", "type", "type_name", "category", "big_type", "small_type"), "''")
    id_expr = _column_expr(columns, ("aoi_id", "id", "adcode"), "NULL")

    point_expr = ""
    if "lon" in columns and "lat" in columns:
        point_expr = "ST_SetSRID(ST_MakePoint(lon::double precision, lat::double precision), 4326)"
    elif "lng" in columns and "lat" in columns:
        point_expr = "ST_SetSRID(ST_MakePoint(lng::double precision, lat::double precision), 4326)"
    elif "longitude" in columns and "latitude" in columns:
        point_expr = "ST_SetSRID(ST_MakePoint(longitude::double precision, latitude::double precision), 4326)"
    elif "geom" in columns:
        point_expr = _aoi_geometry_point_expr("geom", column_types)
    elif "geometry" in columns:
        point_expr = _aoi_geometry_point_expr("geometry", column_types)
    elif "geom_wkt" in columns:
        point_expr = "ST_Centroid(ST_SetSRID(ST_GeomFromText(geom_wkt), 4326))"
    elif "wkt" in columns:
        point_expr = "ST_Centroid(ST_SetSRID(ST_GeomFromText(wkt), 4326))"
    elif "center_x" in columns and "center_y" in columns:
        point_expr = "ST_SetSRID(ST_MakePoint(center_x::double precision, center_y::double precision), 4326)"
    elif "wkb_geometry" in columns:
        point_expr = _aoi_geometry_point_expr("wkb_geometry", column_types)
    else:
        return []

    source = f"{AOI_LEGACY_SCHEMA}.{AOI_LEGACY_TABLE}"
    aoi_cte_sql = f"""
            SELECT {id_expr}::text AS source_id,
                   {name_expr}::text AS name,
                   {type_expr}::text AS raw_type,
                   NULL::text AS category_detail,
                   'aoi'::text AS record_kind,
                   {point_expr} AS geom
            FROM {AOI_LEGACY_SCHEMA}.{AOI_LEGACY_TABLE}
    """
    rows = _read_pg(_build_nearby_aoi_sql(aoi_cte_sql), {"geom_center": geom_center}, limit=30)
    return _format_aoi_source_rows(rows, source)


def _query_aoi_sources(inter: dict[str, Any]) -> list[dict[str, Any]]:
    """Query main AOIs and POI access points within AOI_SEARCH_RADIUS_M around the intersection center."""
    geom_center = inter.get("geom_center")
    if not geom_center:
        return []

    from traffic_signal_agent.core.config import settings

    flow_schema = settings.pg_flow_schema or "xianchang"
    aoi_rows: list[dict[str, Any]] = []
    poi_rows: list[dict[str, Any]] = []

    if _pg_table_exists(flow_schema, AOI_AMAP_TABLE):
        aoi_rows = _query_aoi_sources_amap(flow_schema, geom_center)
        if _pg_table_exists(flow_schema, POI_AMAP_TABLE):
            poi_rows = _query_poi_access_points_amap(flow_schema, geom_center)
        return _merge_access_source_rows(poi_rows, aoi_rows)

    legacy_rows = _query_aoi_sources_legacy(geom_center)
    if _pg_table_exists(flow_schema, POI_AMAP_TABLE):
        poi_rows = _query_poi_access_points_amap(flow_schema, geom_center)
        return _merge_access_source_rows(poi_rows, legacy_rows)
    return legacy_rows


def _query_min_green(
    schema: str,
    inter_id: str,
    day_of_week: int,
) -> list[dict[str, Any]]:
    sql = f"""
        SELECT inter_id, link_id, turn_dir_no, day_of_week, step_index,
               dir8_code, plan_no, cycle_len_sec, green_time_plan, min_green_time,
               has_pedestrian
        FROM {schema}.dws_turn_min_green_5min_mm
        WHERE inter_id = :inter_id
          AND day_of_week = :dow
          AND is_deleted = 0
        ORDER BY link_id, turn_dir_no, step_index
    """
    rows = _read_pg(sql, {"inter_id": inter_id, "dow": day_of_week}, limit=5000)
    return rows


def _query_lane_flow(
    schema: str,
    inter_id: str,
    day_of_week: int,
) -> list[dict[str, Any]]:
    dt = _dt_for_dow(day_of_week)
    sql = f"""
        SELECT inter_id, link_id, lane_id, lane_no, turn_move, step_index,
               dt, vehicle_count, volume
        FROM {schema}.dwd_tfc_lane_roadcross_flow_5mi
        WHERE inter_id = :inter_id
          AND dt = :dt
          AND is_deleted = 0
        ORDER BY link_id, lane_no, step_index
    """
    return _read_pg(sql, {"inter_id": inter_id, "dt": dt}, limit=5000)


def _query_lane_capacity(
    schema: str,
    inter_id: str,
    day_of_week: int,
) -> list[dict[str, Any]]:
    sql = f"""
        SELECT inter_id, lane_id, link_id, lane_capacity, step_index
        FROM {schema}.dws_lane_capacity_5min_mm
        WHERE inter_id = :inter_id
          AND day_of_week = :dow
          AND is_deleted = 0
        ORDER BY link_id, lane_id, step_index
    """
    return _read_pg(sql, {"inter_id": inter_id, "dow": day_of_week}, limit=5000)


def _query_lane_saturation_headway(
    schema: str,
    inter_id: str,
    day_of_week: int,
) -> list[dict[str, Any]]:
    sql = f"""
        WITH selected_day AS (
            SELECT COALESCE(
                (
                    SELECT dayofweek
                    FROM {schema}.dim_lane_saturation_headway
                    WHERE inter_id = :inter_id
                      AND dayofweek = :dow
                      AND is_deleted = 0
                    LIMIT 1
                ),
                (
                    SELECT dayofweek
                    FROM {schema}.dim_lane_saturation_headway
                    WHERE inter_id = :inter_id
                      AND is_deleted = 0
                    ORDER BY dayofweek
                    LIMIT 1
                )
            ) AS dayofweek
        )
        SELECT lane_id, dayofweek, period, inter_id, lane_no,
               saturation_headway, saturation_flow
        FROM {schema}.dim_lane_saturation_headway
        WHERE inter_id = :inter_id
          AND dayofweek = (SELECT dayofweek FROM selected_day)
          AND is_deleted = 0
        ORDER BY lane_no NULLS LAST, period
    """
    return _read_pg(sql, {"inter_id": inter_id, "dow": day_of_week}, limit=5000)


def _query_signal_lane_mapping(schema: str, inter_id: str) -> list[dict[str, Any]]:
    sql = f"""
        SELECT inter_id, plan_no, stage_no, signal_atom, turn_dir_no,
               link_id, lane_nos_json, movement_key
        FROM {schema}.dwd_ctl_inter_signal_atom_lane_mapping
        WHERE inter_id = :inter_id
          AND is_deleted = 0
    """
    return _read_pg(sql, {"inter_id": inter_id}, limit=100)


def _query_stage_cfg(schema: str, inter_id: str) -> list[dict[str, Any]]:
    sql = f"""
        SELECT inter_id, stage_no, stage_name, flow_combo_json, remark
        FROM {schema}.dwd_ctl_inter_stage_cfg
        WHERE inter_id = :inter_id
          AND is_deleted = 0
        ORDER BY stage_no
    """
    return _read_pg(sql, {"inter_id": inter_id}, limit=100)


def _query_stage_motor_flow(schema: str, inter_id: str) -> list[dict[str, Any]]:
    sql = f"""
        SELECT inter_id, stage_no, flow_seq_no, from_link_id, f_dir8_no,
               flow_type_no, flow_type_name, remark
        FROM {schema}.dwd_ctl_inter_stage_motor_flow_rltn
        WHERE inter_id = :inter_id
          AND is_deleted = 0
        ORDER BY stage_no, flow_seq_no
    """
    return _read_pg(sql, {"inter_id": inter_id}, limit=300)


def _query_schedule_cfg(schema: str, inter_id: str) -> list[dict[str, Any]]:
    period_sql = f"""
        SELECT s.inter_id, s.schedule_no, s.schedule_name, s.schedule_type_no,
               s.week_day_no, s.day_plan_no, s.start_day, s.end_day,
               p.period_seq_no, p.start_time, p.end_time, p.plan_no AS period_plan_no,
               p.ctrl_mode, p.remark AS period_remark
        FROM {schema}.dwd_ctl_inter_schedule_cfg s
        LEFT JOIN {schema}.dwd_ctl_inter_day_plan_period p
          ON s.inter_id = p.inter_id AND s.day_plan_no = p.day_plan_no
         AND COALESCE(p.is_deleted, 0) = 0
        WHERE s.inter_id = :inter_id
          AND s.is_deleted = 0
        ORDER BY s.week_day_no NULLS LAST, s.schedule_no, p.period_seq_no NULLS LAST
    """
    try:
        return _read_pg(period_sql, {"inter_id": inter_id}, limit=200)
    except Exception:
        pass

    sql = f"""
        SELECT inter_id, schedule_no, schedule_name, schedule_type_no,
               week_day_no, day_plan_no, start_day, end_day
        FROM {schema}.dwd_ctl_inter_schedule_cfg
        WHERE inter_id = :inter_id
          AND is_deleted = 0
    """
    return _read_pg(sql, {"inter_id": inter_id}, limit=50)


def _checklist_status(rows: list[dict[str, Any]], error: str | None) -> str:
    if error:
        return "error"
    return "has_data" if rows else "no_data"


def _summarize_checklist_item(item_id: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    if item_id == "inter_basic_info":
        row = rows[0]
        sig = "信号化" if row.get("is_signalized") else "非信号化"
        shape = _normalize_intersection_shape(row, [])
        return f"{sig} · {shape or row.get('inter_type') or '-'} · {row.get('inter_name') or ''}"
    if item_id == "channelization":
        ent = sum(1 for r in rows if str(r.get("link_role", "")).lower() == "entrance")
        ext = sum(1 for r in rows if str(r.get("link_role", "")).lower() == "exit")
        return f"进口 {ent} 条 / 出口 {ext} 条"
    if item_id == "lane_detail":
        return f"{len(rows)} 条车道记录"
    if item_id == "adjacent_spacing":
        gaps = [_as_float(r.get("length_m")) for r in rows if r.get("length_m") is not None]
        levels = [r.get("road_level_label") or _road_level_label(r.get("road_level")) for r in rows if r.get("road_level") is not None]
        level_summary = f" · 道路等级 {'/'.join(dict.fromkeys(levels[:4]))}" if levels else ""
        upstream = sum(1 for r in rows if r.get("relation_direction") == "upstream")
        downstream = sum(1 for r in rows if r.get("relation_direction") == "downstream")
        if gaps:
            return f"最短关联路段 {min(gaps):.0f} m · 上游 {upstream} / 下游 {downstream}{level_summary}"
        return f"上游 {upstream} / 下游 {downstream}（无长度）{level_summary}"
    if item_id == "aoi_sources":
        type_counts: dict[str, int] = {}
        poi_access = 0
        for row in rows:
            label = str(row.get("type") or "其他")
            type_counts[label] = type_counts.get(label, 0) + 1
            if row.get("recordKind") == "poi" and row.get("accessRole"):
                poi_access += 1
        summary = "、".join(f"{label}{count}处" for label, count in type_counts.items())
        prefix = f"{AOI_SEARCH_RADIUS_M}m范围主要吸引源"
        if poi_access:
            prefix = f"{AOI_SEARCH_RADIUS_M}m范围吸引源/出入口"
        return f"{prefix}：{summary}" if summary else f"{len(rows)} 个周边吸引源"
    if item_id == "min_green_cfg":
        movements = {_movement_tuple(r) for r in rows}
        times = [_as_float(r.get("min_green_time")) for r in rows if r.get("min_green_time") is not None]
        if times:
            return f"{len(movements)} 个转向 · 最小绿 {min(times):.0f}~{max(times):.0f}s · {len(rows)} 条时序"
        return f"{len(movements)} 个转向（无长度）"
    if item_id == "flow_correlate":
        movements = {
            (
                int(_as_float(row.get("f_dir8_no"))),
                int(_as_float(row.get("turn_dir_no"))),
                str(row.get("period_type") or ""),
            )
            for row in rows
        }
        upstream = sum(1 for row in rows if str(row.get("trace_type") or "").upper() == "UPSTREAM")
        downstream = sum(1 for row in rows if str(row.get("trace_type") or "").upper() == "DOWNSTREAM")
        month = str(rows[0].get("month") or "") if rows else ""
        summary = f"{len(movements)} 个进口转向×时段"
        if month:
            summary = f"{month} · {summary}"
        return f"{summary} · 上游 {upstream} / 下游 {downstream}"
    if item_id == "turn_flow":
        explicit = [r for r in rows if int(_as_float(r.get("turn_dir_no"))) != 0] or rows
        seen: dict[tuple[int, str, int], dict[str, Any]] = {}
        for row in explicit:
            if row.get("step_index") is None:
                continue
            key = (int(row["step_index"]), str(row.get("link_id") or ""), int(_as_float(row.get("turn_dir_no"))))
            seen[key] = row
        total = sum(_as_float(r.get("turn_flow_total")) / 12.0 for r in (seen.values() or explicit))
        return f"全天转向流量 {total:.0f}"
    if item_id == "lane_flow":
        total = sum(_as_float(r.get("volume") or r.get("vehicle_count")) for r in rows)
        return f"车道流量合计 {total:.0f}"
    if item_id == "turn_saturation":
        max_sat = max((_as_float(r.get("turn_saturation")) for r in rows), default=0.0)
        return f"最高转向饱和度 {max_sat:.2f} · {len(rows)} 条"
    if item_id == "inter_evaluation":
        row = rows[0]
        return (
            f"饱和度 {row.get('saturation_max') or row.get('saturation_avg') or '-'} · "
            f"LOS {row.get('level_of_service') or '-'}"
        )
    if item_id == "turn_perf":
        max_q = max((_as_float(r.get("queue_len_max") or r.get("queue_len_avg")) for r in rows), default=0.0)
        return f"最大排队 {max_q:.0f} m · {len(rows)} 条"
    if item_id == "green_utilization":
        vals = [_as_float(r.get("green_utilization")) for r in rows if r.get("green_utilization") is not None]
        avg = sum(vals) / len(vals) if vals else 0.0
        return f"平均绿灯利用率 {avg:.2f}"
    if item_id == "lane_capacity":
        total = sum(_as_float(r.get("lane_capacity")) for r in rows)
        return f"车道能力合计 {total:.0f}"
    if item_id == "lane_saturation_headway":
        flows = [_as_float(r.get("saturation_flow")) for r in rows if r.get("saturation_flow") is not None]
        if flows:
            return f"饱和流率 {min(flows):.0f}~{max(flows):.0f} pcu/h · {len(rows)} 条"
        return f"{len(rows)} 条饱和车头时距记录"
    if item_id in {"plan_cfg", "stage_timing"}:
        plans = {r.get("plan_no") for r in rows}
        cycle = rows[0].get("cycle_len_sec")
        return f"方案 {len(plans)} 个 · 周期 {cycle}s"
    if item_id == "signal_lane_mapping":
        return f"{len(rows)} 条原子-车道映射"
    if item_id == "schedule_cfg":
        return f"{len(rows)} 条时段调度"
    if item_id == "complaint_records":
        return f"{len(rows)} 条投诉"
    if item_id == "field_survey":
        return f"{len(rows)} 条调研"
    return f"{len(rows)} 条记录"


def _load_config_module():
    import importlib.util

    common_dir = Path(__file__).resolve().parents[2] / "common"
    spec = importlib.util.spec_from_file_location("intersection_load_config", common_dir / "load_config.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 intersection/common/load_config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CFG = _load_config_module()
_TH = _CFG.threshold
CHECKLIST_SPEC: list[dict[str, Any]] = _CFG.load_scene_cognition_checklist()


def _checklist_item_from_spec(
    spec: dict[str, Any],
    raw: dict[str, Any],
    query_errors: dict[str, str | None],
) -> dict[str, Any]:
    data_key = spec["data_key"]
    item_id = spec["item_id"]
    error = query_errors.get(data_key)
    if item_id == "stage_timing":
        rows = raw.get("plan") or []
        status = "has_data" if any(r.get("stage_no") is not None for r in rows) else _checklist_status(rows, error)
    elif item_id == "plan_cfg":
        rows = raw.get("plan") or []
        status = "has_data" if rows else _checklist_status([], error)
    else:
        payload = raw.get(data_key)
        if data_key == "inter" and payload is not None and not isinstance(payload, list):
            rows = [payload] if payload else []
        else:
            rows = list(payload or [])
        status = _checklist_status(rows, error)
    entry: dict[str, Any] = {
        **spec,
        "status": status,
        "row_count": len(rows) if item_id not in {"plan_cfg"} else len({r.get("plan_no") for r in rows if r.get("plan_no")}),
        "summary": _summarize_checklist_item(item_id, rows),
    }
    if error and status == "error":
        entry["error"] = error
    return entry


def build_checklist_queries(
    raw: dict[str, Any],
    query_errors: dict[str, str | None],
) -> list[dict[str, Any]]:
    """Build checklist query status from raw PG results (see checklist_rules.md)."""
    return [_checklist_item_from_spec(spec, raw, query_errors) for spec in CHECKLIST_SPEC]


def get_checklist_spec() -> list[dict[str, Any]]:
    """Return checklist manifest for frontend progress UI."""
    items: list[dict[str, Any]] = []
    for spec in CHECKLIST_SPEC:
        item = {
            "item_id": spec["item_id"],
            "category": spec["category"],
            "label": spec["label"],
        }
        if spec.get("table"):
            item["table"] = spec["table"]
        items.append(item)
    return items


def iter_checklist_load(
    inter_id: str | None = None,
    inter_name: str | None = None,
    day_of_week: int = 1,
    step_index: int | None = None,
    time_hhmm: str | None = None,
):
    """Yield checklist item progress events, then final load payload."""
    from traffic_signal_agent.core.config import settings

    total = len(CHECKLIST_SPEC)
    if not settings.pg_configured:
        yield {"type": "error", "message": "PostgreSQL 未配置：请设置 PGHOST/PGUSER/PGDATABASE"}
        return

    if step_index is None and time_hhmm:
        step_index = _step_index_from_hhmm(time_hhmm)

    road = settings.pg_schema
    flow = settings.pg_flow_schema
    inter_table = settings.pg_dim_inter_table
    channel_table = settings.pg_channel_table
    version_sql = _enabled_version_sql(road)

    inter_rows = _query_intersection(road, inter_table, version_sql, inter_id, inter_name)
    if not inter_rows:
        yield {"type": "error", "message": "未找到路口：请检查 inter_id 或 inter_name"}
        return

    inter = inter_rows[0]
    resolved_id = str(inter["inter_id"])
    raw: dict[str, Any] = {"inter": inter}
    query_errors: dict[str, str | None] = {"inter": None}

    query_runners: dict[str, Any] = {
        "channelization": lambda: _safe_query(_query_channelization, road, channel_table, version_sql, resolved_id),
        "lane_detail": lambda: _safe_query(_query_lane_detail, road, resolved_id, version_sql),
        "adjacent_spacing": lambda: _safe_query(_query_adjacent_spacing, road, channel_table, version_sql, resolved_id),
        "aoi_sources": lambda: _safe_query(_query_aoi_sources, inter),
        "min_green_cfg": lambda: _safe_query(_query_min_green, flow, resolved_id, day_of_week),
        "turn_flow": lambda: _safe_query(_query_turn_flow, flow, resolved_id, day_of_week),
        "flow_correlate": lambda: _safe_query(
            _query_flow_correlate, road, flow, resolved_id, day_of_week
        ),
        "lane_flow": lambda: _safe_query(_query_lane_flow, flow, resolved_id, day_of_week),
        "turn_saturation": lambda: _safe_query(_query_turn_saturation, flow, resolved_id, day_of_week),
        "inter_evaluation": lambda: _safe_query(_query_inter_evaluation, flow, resolved_id, day_of_week),
        "turn_perf": lambda: _safe_query(_query_turn_perf, flow, resolved_id, day_of_week),
        "green_utilization": lambda: _safe_query(_query_green_utilization, flow, resolved_id, day_of_week),
        "lane_capacity": lambda: _safe_query(_query_lane_capacity, flow, resolved_id, day_of_week),
        "lane_saturation_headway": lambda: _safe_query(_query_lane_saturation_headway, flow, resolved_id, day_of_week),
        "plan_cfg": lambda: _safe_query(_query_active_plan, flow, resolved_id),
        "signal_lane_mapping": lambda: _safe_query(_query_signal_lane_mapping, flow, resolved_id),
        "schedule_cfg": lambda: _safe_query(_query_schedule_cfg, flow, resolved_id),
        "complaint_records": lambda: _safe_query(_query_complaints, flow, resolved_id),
        "field_survey": lambda: _safe_query(_query_field_survey, flow, resolved_id),
    }
    data_key_by_item = {spec["item_id"]: spec["data_key"] for spec in CHECKLIST_SPEC}

    for index, spec in enumerate(CHECKLIST_SPEC, start=1):
        item_id = spec["item_id"]
        if item_id in query_runners:
            data_key = data_key_by_item[item_id]
            rows, err = query_runners[item_id]()
            raw[data_key] = rows
            query_errors[data_key] = err
        item = _checklist_item_from_spec(spec, raw, query_errors)
        yield {
            "type": "checklist_item",
            "index": index,
            "total": total,
            "item": item,
        }

    stage_cfg_rows, stage_cfg_err = _safe_query(_query_stage_cfg, flow, resolved_id)
    raw["stage_cfg"] = stage_cfg_rows
    query_errors["stage_cfg"] = stage_cfg_err
    stage_motor_rows, stage_motor_err = _safe_query(_query_stage_motor_flow, flow, resolved_id)
    raw["stage_motor_flow"] = stage_motor_rows
    query_errors["stage_motor_flow"] = stage_motor_err

    result = _assemble_task_from_raw(
        inter, raw, query_errors, day_of_week, step_index, errors=[]
    )
    yield {"type": "complete", **result}


def _assemble_task_from_raw(
    inter: dict[str, Any],
    raw: dict[str, Any],
    query_errors: dict[str, str | None],
    day_of_week: int,
    step_index: int | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    checklist_queries = build_checklist_queries(raw, query_errors)
    eval_rows = raw.get("evaluation") or []
    sat_rows = raw.get("turn_saturation") or []
    flow_rows = raw.get("turn_flow") or []
    util_rows = raw.get("green_utilization") or []
    perf_rows = raw.get("turn_perf") or []
    lane_capacity_rows = raw.get("lane_capacity") or []
    channel_rows = raw.get("channelization") or []
    plan_rows = raw.get("plan") or []
    lane_detail_rows = raw.get("lane_detail") or []
    adjacent_rows = raw.get("adjacent_spacing") or []
    aoi_rows = raw.get("aoi_sources") or []
    min_green_rows = raw.get("min_green") or []
    schedule_rows = raw.get("schedule_cfg") or []
    signal_lane_mapping_rows = raw.get("signal_lane_mapping") or []
    stage_cfg_rows = raw.get("stage_cfg") or []
    stage_motor_rows = raw.get("stage_motor_flow") or []
    complaint_rows = raw.get("complaints") or []
    survey_rows = raw.get("field_survey") or []

    sat_rows = _enrich_movement_rows(sat_rows, channel_rows)
    flow_rows = _enrich_movement_rows(flow_rows, channel_rows)
    util_rows = _enrich_movement_rows(util_rows, channel_rows)

    metrics = _aggregate_metrics(
        eval_rows,
        sat_rows,
        flow_rows,
        util_rows,
        perf_rows,
        lane_capacity_rows,
        adjacent_rows=adjacent_rows,
        channel_rows=channel_rows,
    )
    raw["turn_saturation"] = sat_rows
    raw["turn_flow"] = flow_rows
    raw["green_utilization"] = util_rows
    scope = _build_scope(inter, channel_rows, plan_rows, lane_detail_rows, adjacent_rows)
    signal = _build_signal(
        plan_rows,
        schedule_rows,
        min_green_rows,
        signal_lane_mapping_rows,
        stage_cfg_rows,
        stage_motor_rows,
    )
    context = _build_context(
        inter, day_of_week, complaint_rows, survey_rows, metrics, checklist_queries, step_index, aoi_rows
    )
    task = {"scope": scope, "metrics": metrics, "signal": signal, "context": context}
    return {
        "ok": True,
        "task": task,
        "raw": raw,
        "checklist_queries": checklist_queries,
        "errors": errors or [],
    }


def load_intersection_from_pg(
    inter_id: str | None = None,
    inter_name: str | None = None,
    day_of_week: int = 1,
    step_index: int | None = None,
    time_hhmm: str | None = None,
) -> dict[str, Any]:
    """Load intersection task payload from PostgreSQL.

    Queries checklist items one-by-one per references/checklist_rules.md.

    Returns:
        dict with ok, task, raw, checklist_queries, errors.
    """
    for event in iter_checklist_load(
        inter_id=inter_id,
        inter_name=inter_name,
        day_of_week=day_of_week,
        step_index=step_index,
        time_hhmm=time_hhmm,
    ):
        if event["type"] == "error":
            return {
                "ok": False,
                "task": {},
                "raw": {},
                "checklist_queries": build_checklist_queries({"inter": []}, {"inter": None}),
                "errors": [event["message"]],
            }
        if event["type"] == "complete":
            return event
    return {
        "ok": False,
        "task": {},
        "raw": {},
        "checklist_queries": [],
        "errors": ["检查单加载未完成"],
    }


def build_task_from_pg(task_or_inter_id: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Alias entrypoint for skillpack execution_steps.

    Accepts a TrafficTask dict (with scope.intersection_id) or explicit kwargs.
    """
    inter_id = kwargs.get("inter_id")
    inter_name = kwargs.get("inter_name")
    day_of_week = int(kwargs.get("day_of_week", 1))
    step_index = kwargs.get("step_index")
    time_hhmm = kwargs.get("time_hhmm")

    if isinstance(task_or_inter_id, dict):
        scope = task_or_inter_id.get("scope") or {}
        context = task_or_inter_id.get("context") or {}
        inter_id = inter_id or scope.get("intersection_id") or scope.get("inter_id")
        inter_name = inter_name or scope.get("name")
        day_of_week = int(context.get("day_of_week") or day_of_week)
        step_index = context.get("step_index") or step_index
        time_hhmm = context.get("time_hhmm") or time_hhmm
    elif isinstance(task_or_inter_id, str):
        inter_id = task_or_inter_id

    result = load_intersection_from_pg(
        inter_id=str(inter_id) if inter_id else None,
        inter_name=str(inter_name) if inter_name else None,
        day_of_week=day_of_week,
        step_index=int(step_index) if step_index is not None else None,
        time_hhmm=str(time_hhmm) if time_hhmm else None,
    )
    if not result["ok"]:
        return {"ok": False, "validation_errors": result["errors"], **result}
    merged_task = result["task"]
    if isinstance(task_or_inter_id, dict):
        for key in ("task_id", "objectives", "constraints"):
            if key in task_or_inter_id:
                merged_task[key] = task_or_inter_id[key]
    return {"ok": True, "task": merged_task, "raw": result.get("raw", {}), "checklist_queries": result.get("checklist_queries", []), "errors": result.get("errors", [])}


def _query_intersection(
    schema: str,
    table: str,
    version_sql: str,
    inter_id: str | None,
    inter_name: str | None,
) -> list[dict[str, Any]]:
    if inter_id:
        sql = f"""
            SELECT inter_id, inter_name, is_signalized, signal_controller_code,
                   inter_type, inter_proto, geom_center
            FROM {schema}.{table}
            WHERE version_id = {version_sql}
              AND inter_id = :inter_id
            LIMIT 1
        """
        return _read_pg(sql, {"inter_id": inter_id}, limit=1)
    if inter_name:
        sql = f"""
            SELECT inter_id, inter_name, is_signalized, signal_controller_code,
                   inter_type, inter_proto, geom_center
            FROM {schema}.{table}
            WHERE version_id = {version_sql}
              AND is_signalized = 1
              AND inter_name LIKE :pattern
            LIMIT 5
        """
        return _read_pg(sql, {"pattern": f"%{inter_name}%"}, limit=5)
    return []


def _query_channelization(
    schema: str,
    table: str,
    version_sql: str,
    inter_id: str,
) -> list[dict[str, Any]]:
    sql = f"""
        SELECT inter_id, link_id, link_role, dir8_code, dir8_label, dir4_label,
               lane_num, c_lane_num, lane_info, turn_move, link_clockwise_seq
        FROM {schema}.{table}
        WHERE version_id = {version_sql}
          AND inter_id = :inter_id
        ORDER BY link_clockwise_seq NULLS LAST
    """
    return _read_pg(sql, {"inter_id": inter_id}, limit=200)


def _query_inter_evaluation(
    schema: str,
    inter_id: str,
    day_of_week: int,
) -> list[dict[str, Any]]:
    sql = f"""
        SELECT inter_id, day_of_week, step_index,
               saturation_max, saturation_avg, unbalance_index,
               level_of_service, turn_count
        FROM {schema}.dws_inter_evaluation_5min_mm
        WHERE inter_id = :inter_id
          AND day_of_week = :dow
          AND is_deleted = 0
        ORDER BY step_index
    """
    return _read_pg(sql, {"inter_id": inter_id, "dow": day_of_week}, limit=500)


def _query_turn_saturation(
    schema: str,
    inter_id: str,
    day_of_week: int,
) -> list[dict[str, Any]]:
    sql = f"""
        SELECT inter_id, link_id, turn_dir_no, step_index,
               turn_saturation, lane_saturation_detail
        FROM {schema}.dws_turn_saturation_5min_mm
        WHERE inter_id = :inter_id
          AND day_of_week = :dow
          AND is_deleted = 0
        ORDER BY step_index, turn_saturation DESC NULLS LAST
    """
    return _read_pg(sql, {"inter_id": inter_id, "dow": day_of_week}, limit=5000)


def _query_flow_correlate(
    road_schema: str,
    flow_schema: str,
    inter_id: str,
    day_of_week: int,
) -> list[dict[str, Any]]:
    day_label, day_type_label = _flow_correlate_day_labels(day_of_week)
    version_sql = _enabled_version_sql(road_schema)
    sql = f"""
        SELECT fc.month, fc.day_of_week, fc.period_type,
               fc.inter_id, fc.f_dir8_no, fc.turn_dir_no,
               fc.cor_inter_id, fc.cor_f_dir8_no, fc.cor_turn_dir_no,
               fc.flow_share_ratio, fc.trace_type,
               cor_inter.inter_name AS cor_inter_name
        FROM {flow_schema}.dws_tfc_inter_turn_flow_correlate_m fc
        LEFT JOIN {road_schema}.dim_inter_info cor_inter
          ON cor_inter.inter_id = fc.cor_inter_id
         AND cor_inter.version_id = {version_sql}
        WHERE fc.inter_id = :inter_id
          AND fc.is_deleted = 0
          AND fc.day_of_week IN (:day_label, :day_type_label)
          AND fc.month = (
              SELECT MAX(latest.month)
              FROM {flow_schema}.dws_tfc_inter_turn_flow_correlate_m latest
              WHERE latest.inter_id = :inter_id
                AND latest.is_deleted = 0
          )
        ORDER BY fc.period_type, fc.f_dir8_no, fc.turn_dir_no, fc.trace_type,
                 fc.flow_share_ratio DESC NULLS LAST
    """
    return _read_pg(
        sql,
        {"inter_id": inter_id, "day_label": day_label, "day_type_label": day_type_label},
        limit=5000,
    )


def _query_turn_flow(
    schema: str,
    inter_id: str,
    day_of_week: int,
) -> list[dict[str, Any]]:
    sql = f"""
        SELECT inter_id, link_id, turn_dir_no, step_index,
               turn_flow_total, avg_lane_flow_5min, lane_count
        FROM {schema}.dws_inter_link_turn_flow_5min_mm
        WHERE inter_id = :inter_id
          AND day_of_week = :dow
          AND is_deleted = 0
        ORDER BY step_index, link_id, turn_dir_no
    """
    return _read_pg(sql, {"inter_id": inter_id, "dow": day_of_week}, limit=5000)


def _query_green_utilization(
    schema: str,
    inter_id: str,
    day_of_week: int,
) -> list[dict[str, Any]]:
    sql = f"""
        SELECT inter_id, link_id, turn_dir_no, step_index,
               green_utilization
        FROM {schema}.dws_turn_green_utilization_5min_mm
        WHERE inter_id = :inter_id
          AND day_of_week = :dow
          AND is_deleted = 0
        ORDER BY step_index, link_id, turn_dir_no
    """
    return _read_pg(sql, {"inter_id": inter_id, "dow": day_of_week}, limit=5000)


def _query_turn_perf(
    schema: str,
    inter_id: str,
    day_of_week: int,
) -> list[dict[str, Any]]:
    primary_sql = f"""
        SELECT inter_id, f_dir_8, turn_dir_no, day_of_week, step_index,
               f_dir_8_label, turn_dir_label,
               queue_len_max, queue_len_avg, pass_flow,
               stop_time, stop_times, delay_index, los
        FROM {schema}.dws_inter_dir_turn_perf_5min_mm
        WHERE inter_id = :inter_id
          AND day_of_week = :dow
          AND is_deleted = 0
        ORDER BY step_index, f_dir_8, turn_dir_no
    """
    params = {"inter_id": inter_id, "dow": day_of_week}
    rows = _read_pg(primary_sql, params, limit=5000)
    if rows:
        return rows

    approach_sql = f"""
        SELECT inter_id, f_dir_8, turn_dir_no, day_of_week, step_index,
               f_dir_8_label, turn_dir_label,
               queue_len_max, queue_len_avg, pass_flow,
               stop_time, stop_times, delay_index, los
        FROM {schema}.dws_inter_approach_turn_perf_5min_mm
        WHERE inter_id = :inter_id
          AND day_of_week = :dow
          AND is_deleted = 0
        ORDER BY step_index, f_dir_8, turn_dir_no
    """
    rows = _read_pg(approach_sql, params, limit=5000)
    if rows:
        return rows

    dwd_sql = f"""
        SELECT inter_id,
               COALESCE(eight_direction, NULL)::smallint AS f_dir_8,
               turn_dir_no,
               (((EXTRACT(DOW FROM stat_time)::int + 6) % 7) + 1)::smallint AS day_of_week,
               (EXTRACT(HOUR FROM stat_time)::int * 12 + FLOOR(EXTRACT(MINUTE FROM stat_time)::int / 5))::smallint AS step_index,
               NULL::text AS f_dir_8_label,
               NULL::text AS turn_dir_label,
               queue_len_max, queue_len_avg, pass_flow,
               stop_time, stop_times, delay_index, los
        FROM {schema}.dwd_tfc_inter_dir_perf_5min
        WHERE inter_id = :inter_id
          AND (((EXTRACT(DOW FROM stat_time)::int + 6) % 7) + 1) = :dow
        ORDER BY stat_time, f_dir_8, turn_dir_no
    """
    return _read_pg(dwd_sql, params, limit=5000)


def _query_active_plan(schema: str, inter_id: str) -> list[dict[str, Any]]:
    extended_sql = f"""
        SELECT p.inter_id, p.plan_no, p.plan_name, p.cycle_len_sec, p.offset_sec,
               p.coord_stage_no, p.stage_cnt,
               t.stage_no, t.stage_seq_no, t.green_sec, t.yellow_sec,
               t.all_red_sec, t.min_green_sec, t.max_green_sec, t.stage_total_sec,
               t.remark
        FROM {schema}.dwd_ctl_inter_plan_cfg p
        JOIN {schema}.dwd_ctl_inter_plan_stage_timing t
          ON p.inter_id = t.inter_id AND p.plan_no = t.plan_no
        WHERE p.inter_id = :inter_id
          AND p.is_deleted = 0 AND t.is_deleted = 0
        ORDER BY p.plan_no, t.stage_seq_no
        LIMIT 50
    """
    try:
        return _read_pg(extended_sql, {"inter_id": inter_id}, limit=50)
    except Exception:
        pass

    sql = f"""
        SELECT p.inter_id, p.plan_no, p.plan_name, p.cycle_len_sec, p.offset_sec,
               t.stage_no, t.stage_seq_no, t.green_sec, t.yellow_sec,
               t.min_green_sec, t.max_green_sec
        FROM {schema}.dwd_ctl_inter_plan_cfg p
        JOIN {schema}.dwd_ctl_inter_plan_stage_timing t
          ON p.inter_id = t.inter_id AND p.plan_no = t.plan_no
        WHERE p.inter_id = :inter_id
          AND p.is_deleted = 0 AND t.is_deleted = 0
        ORDER BY p.plan_no, t.stage_seq_no
        LIMIT 50
    """
    return _read_pg(sql, {"inter_id": inter_id}, limit=50)


def _query_complaints(schema: str, inter_id: str) -> list[dict[str, Any]]:
    sql = f"""
        SELECT inter_id, complaint_type, core_problem_desc, stat_period
        FROM {schema}.dwd_tfc_complaint_inter_issue
        WHERE inter_id = :inter_id
        ORDER BY stat_period DESC NULLS LAST
        LIMIT 10
    """
    try:
        return _read_pg(sql, {"inter_id": inter_id}, limit=10)
    except Exception:
        return []


def _query_field_survey(schema: str, inter_id: str) -> list[dict[str, Any]]:
    sql = f"""
        SELECT inter_id, issue_type, issue_desc, survey_time
        FROM {schema}.dwd_tfc_field_survey_inter_issue
        WHERE inter_id = :inter_id
        ORDER BY survey_time DESC NULLS LAST
        LIMIT 10
    """
    try:
        return _read_pg(sql, {"inter_id": inter_id}, limit=10)
    except Exception:
        return []


def _entrance_link_lengths(adjacent_rows: list[dict[str, Any]]) -> dict[str, float]:
    """Map entrance link_id → length_m from dim_link_info (via adjacent_spacing query)."""
    lengths: dict[str, float] = {}
    for row in adjacent_rows or []:
        if str(row.get("relation_direction") or "").lower() not in {"", "upstream"} and str(row.get("link_role", "")).lower() != "entrance":
            continue
        link_id = row.get("link_id")
        length = _as_float(row.get("length_m"))
        if link_id and length > 0:
            lengths[str(link_id)] = length
    return lengths


def _road_level_code(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.endswith(".0"):
        text = text[:-2]
    return ROAD_LEVEL_CODE_ALIASES.get(text, text)


def _road_level_label(value: Any) -> str:
    code = _road_level_code(value)
    return ROAD_LEVEL_LABELS.get(code, code)


def _road_level_group(value: Any) -> str:
    code = _road_level_code(value)
    return ROAD_LEVEL_GROUPS.get(code, "未分级" if code else "")


def _road_level_rank(value: Any) -> int:
    return ROAD_LEVEL_RANK.get(_road_level_code(value), 0)


def _classify_road_grade_combination(road_levels: list[dict[str, Any]]) -> str | None:
    groups = sorted({str(item.get("group") or "") for item in road_levels if item.get("group")})
    if not groups:
        return None
    if len(groups) == 1:
        group = groups[0]
        return f"{group}-{group}相交"
    if "主干路" in groups and "次干路" in groups:
        return "主干路-次干路相交"
    if "主干路" in groups and "支路" in groups:
        return "主干路-支路相交"
    if "次干路" in groups and "支路" in groups:
        return "次干路-支路相交"
    return "-".join(groups) + "相交"


def _classify_intersection_importance(road_levels: list[dict[str, Any]]) -> str | None:
    ranks = [_road_level_rank(item.get("code")) for item in road_levels if item.get("code")]
    if not ranks:
        return None
    max_rank = max(ranks)
    min_rank = min(rank for rank in ranks if rank > 0) if any(rank > 0 for rank in ranks) else 0
    if max_rank >= 4 and min_rank >= 4:
        return "city_key_node"
    if max_rank >= 4 and min_rank >= 3:
        return "important_transfer_node"
    if max_rank >= 4:
        return "major_minor_priority_node"
    if max_rank >= 3 and min_rank >= 3:
        return "area_traffic_node"
    return "local_microcirculation_node"


def _build_road_level_profile(adjacent_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    road_levels: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in adjacent_rows or []:
        code = _road_level_code(row.get("road_level"))
        if not code:
            continue
        key = (str(row.get("link_id") or ""), code)
        if key in seen:
            continue
        seen.add(key)
        road_levels.append(
            {
                "link_id": row.get("link_id"),
                "dir8_label": row.get("dir8_label"),
                "code": code,
                "label": _road_level_label(code),
                "group": _road_level_group(code),
                "rank": _road_level_rank(code),
            }
        )
    return road_levels


def _normalize_intersection_shape(inter: dict[str, Any], entrances: list[dict[str, Any]]) -> str | None:
    text = " ".join(str(inter.get(key) or "") for key in ("inter_type", "inter_proto")).lower()
    leg_count = _count_approach_legs(entrances)
    if any(token in text for token in ("环岛", "roundabout")):
        return "roundabout"
    if any(token in text for token in ("行人", "过街", "pedestrian")):
        return "pedestrian_crossing"
    if any(token in text for token in ("畸形", "错位", "异形", "irregular")):
        return "irregular"
    if re.search(r"(^|[^a-z])y([^a-z]|$)", text) or "y型" in text:
        return "y"
    if re.search(r"(^|[^a-z])t([^a-z]|$)", text) or "丁" in text or leg_count == 3:
        return "t"
    if re.search(r"(^|[^a-z])x([^a-z]|$)", text) or "斜" in text:
        return "x"
    if leg_count >= 5 or "五叉" in text or "多路" in text:
        return "multi_leg"
    if leg_count == 4 or "十字" in text:
        return "cross"
    return str(inter.get("inter_type") or inter.get("inter_proto") or "") or None


def _count_approach_legs(entrances: list[dict[str, Any]]) -> int:
    dirs = {
        _compact_dir4(row.get("dir4_label") or row.get("dir8_label"))
        for row in entrances
        if _compact_dir4(row.get("dir4_label") or row.get("dir8_label"))
    }
    return len(dirs) if dirs else len(entrances)


def _shape_static_flags(shape: str | None, leg_count: int) -> list[str]:
    flags: list[str] = []
    if shape in {"roundabout", "irregular", "multi_leg"}:
        flags.append(f"{shape}_intersection")
    if shape in {"x", "y"}:
        flags.append("skewed_intersection")
    if shape == "pedestrian_crossing":
        flags.append("pedestrian_crossing")
    if leg_count >= 5 and "multi_leg_intersection" not in flags:
        flags.append("multi_leg_intersection")
    return flags


def _compact_dir4(label: Any) -> str:
    text = str(label or "").strip()
    if not text:
        return ""
    for suffix in ("进口", "出口"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    for prefix in ("东南", "西南", "东北", "西北", "东", "西", "南", "北"):
        if text.startswith(prefix) or prefix in text[:3]:
            return prefix
    return text


def _build_link_dir_lookup(channel_rows: list[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for row in channel_rows or []:
        link_id = row.get("link_id")
        if not link_id:
            continue
        label = row.get("dir4_label") or row.get("dir8_label") or ""
        if not label:
            continue
        link_key = str(link_id)
        lookup[link_key] = str(label)
        lookup[link_key[-4:]] = str(label)
    return lookup


def _enrich_movement_rows(rows: list[dict[str, Any]], channel_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = _build_link_dir_lookup(channel_rows)
    if not lookup:
        return rows
    enriched: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if not (item.get("f_dir_8_label") or item.get("dir8_label") or item.get("dir4_label")):
            link_id = str(item.get("link_id") or item.get("f_dir_8") or "")
            label = lookup.get(link_id) or lookup.get(link_id[-4:])
            if label:
                item["dir8_label"] = label
        enriched.append(item)
    return enriched


def _dir8_link_map(channel_rows: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in channel_rows or []:
        if str(row.get("link_role", "")).lower() != "entrance":
            continue
        link_id = row.get("link_id")
        if not link_id:
            continue
        for key in ("dir8_code", "dir8_label"):
            value = row.get(key)
            if value is not None:
                mapping[str(value)] = str(link_id)
    return mapping


def _resolve_perf_link_id(row: dict[str, Any], channel_rows: list[dict[str, Any]]) -> str | None:
    link_id = row.get("link_id")
    if link_id:
        return str(link_id)
    dir_map = _dir8_link_map(channel_rows)
    for key in ("f_dir_8", "dir8_code"):
        value = row.get(key)
        if value is not None and str(value) in dir_map:
            return dir_map[str(value)]
    return None


def _derive_storage_m(
    perf_rows: list[dict[str, Any]],
    adjacent_rows: list[dict[str, Any]],
    channel_rows: list[dict[str, Any]],
) -> float:
    """Pick storage_m as the entrance link length for the approach with peak queue."""
    link_lengths = _entrance_link_lengths(adjacent_rows)
    if not link_lengths or not perf_rows:
        return 0.0

    peak_queue = -1.0
    peak_link: str | None = None
    for row in perf_rows:
        queue = _as_float(row.get("queue_len_max") or row.get("queue_len_avg"))
        if queue <= peak_queue:
            continue
        link_id = _resolve_perf_link_id(row, channel_rows)
        if not link_id or link_id not in link_lengths:
            continue
        peak_queue = queue
        peak_link = link_id

    if peak_link:
        return round(link_lengths[peak_link], 2)
    return 0.0


def _aggregate_metrics(
    eval_rows: list[dict[str, Any]],
    sat_rows: list[dict[str, Any]],
    flow_rows: list[dict[str, Any]],
    util_rows: list[dict[str, Any]],
    perf_rows: list[dict[str, Any]],
    lane_capacity_rows: list[dict[str, Any]] | None = None,
    adjacent_rows: list[dict[str, Any]] | None = None,
    channel_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    evaluation = (
        max(
            eval_rows,
            key=lambda row: _as_float(row.get("saturation_max") or row.get("saturation_avg")),
        )
        if eval_rows
        else {}
    )
    saturation = _as_float(evaluation.get("saturation_max") or evaluation.get("saturation_avg"))
    movement_volume = _avg_by_movement(flow_rows, "turn_flow_total")
    movement_saturation = _max_by_movement(sat_rows, "turn_saturation")
    volume = sum(movement_volume.values())
    lane_count = max(
        (int(_as_float(row.get("lane_count"))) for row in flow_rows if row.get("lane_count") is not None),
        default=max(len(movement_volume), 1),
    )
    capacity = volume / saturation if saturation > 0 else 0.0

    green_utils = [_as_float(row.get("green_utilization")) for row in util_rows if row.get("green_utilization") is not None]
    green_utilization = sum(green_utils) / len(green_utils) if green_utils else 0.0
    empty_green_rate = max(0.0, 1.0 - green_utilization) if green_utilization else 0.0

    queues = [_as_float(row.get("queue_len_max") or row.get("queue_len_avg")) for row in perf_rows]
    delays = [_as_float(row.get("delay_index") or row.get("stop_time")) for row in perf_rows]
    stops = [_as_float(row.get("stop_times")) for row in perf_rows if row.get("stop_times") is not None]
    spillback_flags = [
        row for row in perf_rows
        if _as_float(row.get("queue_len_max")) >= _TH("queue.long_queue_m") or _as_float(row.get("delay_index")) >= _TH("delay.high_delay_index")
    ]
    lane_capacity_total = 0.0
    if lane_capacity_rows:
        lane_cap_buckets: dict[str, list[float]] = {}
        for row in lane_capacity_rows:
            lane_key = str(row.get("lane_id") or row.get("link_id") or "")
            lane_cap_buckets.setdefault(lane_key, []).append(_as_float(row.get("lane_capacity")))
        lane_capacity_total = sum(sum(vals) / len(vals) for vals in lane_cap_buckets.values() if vals)
    if lane_capacity_total > 0 and capacity <= 0:
        capacity = lane_capacity_total

    queue_m = round(max(queues), 2) if queues else 0.0
    storage_m = _derive_storage_m(perf_rows, adjacent_rows or [], channel_rows or [])

    return {
        "volume": round(volume, 2),
        "capacity": round(capacity, 2) if capacity else 0.0,
        "saturation": round(saturation, 4),
        "avg_delay_s": round(sum(delays) / len(delays), 2) if delays else 0.0,
        "queue_m": queue_m,
        "storage_m": storage_m,
        "stop_count": round(sum(stops) / len(stops), 2) if stops else 0.0,
        "imbalance_index": _as_float(evaluation.get("unbalance_index")),
        "green_utilization": round(green_utilization, 4),
        "empty_green_rate": round(empty_green_rate, 4),
        "spillback_risk": 0.85 if spillback_flags else (_TH("saturation.pressure_baseline") if saturation >= _TH("saturation.oversaturation") else 0.0),
        "movement_volume": movement_volume,
        "movement_saturation": movement_saturation,
        "los": evaluation.get("level_of_service"),
        "turn_perf_detail": perf_rows[:20],
        "turn_saturation_detail": sat_rows[:20],
    }


def _movement_key(row: dict[str, Any]) -> str:
    link_id = str(row.get("link_id") or row.get("f_dir_8") or "")[-4:]
    turn = TURN_DIR_LABELS.get(int(_as_float(row.get("turn_dir_no"))), str(row.get("turn_dir_no")))
    return f"{link_id}_{turn}"


def _build_scope(
    inter: dict[str, Any],
    channel_rows: list[dict[str, Any]],
    plan_rows: list[dict[str, Any]],
    lane_detail_rows: list[dict[str, Any]] | None = None,
    adjacent_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    entrances = [row for row in channel_rows if str(row.get("link_role", "")).lower() == "entrance"]
    exits = [row for row in channel_rows if str(row.get("link_role", "")).lower() == "exit"]
    lane_mismatch, funnel_details = _detect_funnel(entrances, exits, lane_detail_rows)
    road_levels = _build_road_level_profile(adjacent_rows or [])
    road_grade_combination = _classify_road_grade_combination(road_levels)
    intersection_importance = _classify_intersection_importance(road_levels)
    leg_count = _count_approach_legs(entrances)
    intersection_shape = _normalize_intersection_shape(inter, entrances)
    static_flags = list(dict.fromkeys([*lane_mismatch, *_shape_static_flags(intersection_shape, leg_count)]))
    spacing_detail: list[dict[str, Any]] = []
    for row in adjacent_rows or []:
        if row.get("length_m") is None:
            continue
        relation = row.get("relation_direction") or (
            "upstream" if str(row.get("link_role", "")).lower() == "entrance" else "downstream"
        )
        adjacent_inter_id = row.get("adjacent_inter_id") or row.get("upstream_inter_id")
        spacing_detail.append(
            {
                "link_id": row.get("link_id"),
                "link_role": row.get("link_role"),
                "dir8_label": row.get("dir8_label"),
                "relation_direction": relation,
                "adjacent_inter_id": adjacent_inter_id,
                "adjacent_inter_name": row.get("adjacent_inter_name"),
                "upstream_inter_id": adjacent_inter_id if relation == "upstream" else None,
                "spacing_m": round(_as_float(row.get("length_m")), 2),
                "road_level_code": _road_level_code(row.get("road_level")) or None,
                "road_level_label": _road_level_label(row.get("road_level")) or None,
                "road_level_group": _road_level_group(row.get("road_level")) or None,
            }
        )
    gaps = [item["spacing_m"] for item in spacing_detail if item["spacing_m"] > 0]
    return {
        "level": "intersection",
        "intersection_id": inter.get("inter_id"),
        "name": inter.get("inter_name"),
        "signal_controller_id": inter.get("signal_controller_code"),
        "is_signalized": bool(inter.get("is_signalized")),
        "inter_type": inter.get("inter_type"),
        "cross_type": inter.get("inter_proto"),
        "intersection_shape": intersection_shape,
        "leg_count": leg_count,
        "road_levels": road_levels,
        "road_grade_combination": road_grade_combination,
        "intersection_importance": intersection_importance,
        "approaches": entrances,
        "exits": exits,
        "channelization": channel_rows,
        "lanes": lane_detail_rows if lane_detail_rows else _flatten_lanes(channel_rows),
        "adjacent_inter_spacing_m": min(gaps) if gaps else None,
        "adjacent_inter_spacing_detail": spacing_detail,
        "static_flags": static_flags,
        "funnel_details": funnel_details,
        "plan_count": len({row.get("plan_no") for row in plan_rows}),
    }


def _flatten_lanes(channel_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lanes: list[dict[str, Any]] = []
    for row in channel_rows:
        lanes.append(
            {
                "link_id": row.get("link_id"),
                "dir8_label": row.get("dir8_label"),
                "lane_num": row.get("lane_num"),
                "turn_move": row.get("turn_move"),
                "link_role": row.get("link_role"),
            }
        )
    return lanes


def _normalize_turn_move_token(turn_move: Any) -> str:
    return str(turn_move or "").strip().upper()


def _is_straight_lane(turn_move: Any) -> bool:
    token = _normalize_turn_move_token(turn_move)
    if not token:
        return False
    if token in TURN_MOVE_STRAIGHT_CODES:
        return True
    text = token.lower()
    if any(code in text for code in TURN_MOVE_LEFT_CODES | TURN_MOVE_RIGHT_CODES):
        if token not in TURN_MOVE_STRAIGHT_CODES:
            return False
    if any(keyword in text for keyword in ("左转", "left", "右转", "right", "调头", "uturn")):
        return False
    return any(keyword in text for keyword in ("直行", "直", "through", "straight"))


def _count_straight_lanes_in_turn_move_field(turn_move_field: Any) -> int:
    text = str(turn_move_field or "").strip()
    if not text:
        return 0
    if "|" in text:
        return sum(1 for part in text.split("|") if _is_straight_lane(part))
    return 1 if _is_straight_lane(text) else 0


def _parse_straight_lane_count_from_lane_info(lane_info: Any) -> int:
    text = str(lane_info or "")
    if not text:
        return 0
    match = re.search(r"(\d+)\s*直", text)
    if match:
        return int(match.group(1))
    if "全直" in text or "纯直" in text:
        return 0
    return 0


def _straight_lane_count(
    link_id: Any,
    entrance_row: dict[str, Any],
    lane_detail_rows: list[dict[str, Any]] | None,
) -> int:
    lanes = [
        row
        for row in (lane_detail_rows or [])
        if str(row.get("link_id")) == str(link_id)
        and str(row.get("link_role", "")).lower() == "entrance"
    ]
    straight_lanes = [row for row in lanes if _is_straight_lane(row.get("turn_move"))]
    if straight_lanes:
        return len(straight_lanes)
    parsed_turn_move = _count_straight_lanes_in_turn_move_field(entrance_row.get("turn_move"))
    if parsed_turn_move > 0:
        return parsed_turn_move
    parsed = _parse_straight_lane_count_from_lane_info(entrance_row.get("lane_info"))
    if parsed > 0:
        return parsed
    return 0


def _exit_lane_count_for_link(
    link_id: Any,
    exit_row: dict[str, Any],
    lane_detail_rows: list[dict[str, Any]] | None,
) -> int:
    lanes = [
        row
        for row in (lane_detail_rows or [])
        if str(row.get("link_id")) == str(link_id)
        and str(row.get("link_role", "")).lower() == "exit"
    ]
    if lanes:
        return len(lanes)
    return int(_as_float(exit_row.get("lane_num")))


def _group_rows_by_dir4(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        dir4 = _compact_dir4(row.get("dir4_label") or row.get("dir8_label"))
        if not dir4:
            continue
        grouped.setdefault(dir4, []).append(row)
    return grouped


def _total_straight_lanes_for_direction(
    entrance_rows: list[dict[str, Any]],
    lane_detail_rows: list[dict[str, Any]] | None,
) -> int:
    return sum(
        _straight_lane_count(row.get("link_id"), row, lane_detail_rows)
        for row in entrance_rows
    )


def _total_exit_lanes_for_direction(
    exit_rows: list[dict[str, Any]],
    lane_detail_rows: list[dict[str, Any]] | None,
) -> int:
    """Sum exit lanes across all exit links in the same cardinal direction."""
    return sum(
        _exit_lane_count_for_link(row.get("link_id"), row, lane_detail_rows)
        for row in exit_rows
    )


def _detect_funnel(
    entrances: list[dict[str, Any]],
    exits: list[dict[str, Any]],
    lane_detail_rows: list[dict[str, Any]] | None = None,
) -> tuple[list[str], list[str]]:
    """Detect funnel effect by matching straight entrance lanes to opposite exit lanes."""
    flags: list[str] = []
    details: list[str] = []
    entrances_by_dir4 = _group_rows_by_dir4(entrances)
    exits_by_dir4 = _group_rows_by_dir4(exits)

    for ent_dir, entrance_rows in entrances_by_dir4.items():
        opposite = OPPOSITE_DIR4.get(ent_dir)
        if not opposite:
            continue
        exit_rows = exits_by_dir4.get(opposite) or []
        if not exit_rows:
            continue
        straight_count = _total_straight_lanes_for_direction(entrance_rows, lane_detail_rows)
        if straight_count <= 0:
            continue
        exit_count = _total_exit_lanes_for_direction(exit_rows, lane_detail_rows)
        if exit_count > 0 and straight_count > exit_count:
            details.append(f"{ent_dir}直行{straight_count}车道→{opposite}出口{exit_count}车道")

    if details:
        flags.append("funnel_effect")
    if len(entrances_by_dir4) > len(exits_by_dir4):
        flags.append("more_entrances_than_exits")
    return flags, details


def _build_signal(
    plan_rows: list[dict[str, Any]],
    schedule_rows: list[dict[str, Any]] | None = None,
    min_green_rows: list[dict[str, Any]] | None = None,
    signal_lane_mapping_rows: list[dict[str, Any]] | None = None,
    stage_cfg_rows: list[dict[str, Any]] | None = None,
    stage_motor_flow_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not plan_rows:
        return {}
    first = plan_rows[0]
    cycle = _as_float(first.get("cycle_len_sec"))
    release_by_stage = _release_movements_by_stage(signal_lane_mapping_rows or [])
    for source in (
        _release_movements_from_stage_cfg(stage_cfg_rows or []),
        _release_movements_from_stage_motor_flow(stage_motor_flow_rows or []),
    ):
        for stage, movements in source.items():
            if movements and not release_by_stage.get(stage):
                release_by_stage[stage] = movements
    ordered_plan_rows = sorted(
        plan_rows,
        key=lambda item: (
            _as_float(item.get("plan_no")),
            _as_float(item.get("stage_seq_no")),
            _as_float(item.get("stage_no")),
        ),
    )
    phases = [
        {
            "plan_no": row.get("plan_no"),
            "plan_name": row.get("plan_name"),
            "stage_no": row.get("stage_no"),
            "stage_seq_no": row.get("stage_seq_no"),
            "release_movements": release_by_stage.get(f"{row.get('plan_no')}:{row.get('stage_no')}") or release_by_stage.get(str(row.get("stage_no")), ""),
            "green_sec": row.get("green_sec"),
            "yellow_sec": row.get("yellow_sec"),
            "all_red_sec": row.get("all_red_sec"),
            "min_green_sec": row.get("min_green_sec"),
            "max_green_sec": row.get("max_green_sec"),
            "stage_total_sec": row.get("stage_total_sec"),
            "source_remark": row.get("remark"),
        }
        for row in ordered_plan_rows
    ]
    phase_splits = {
        str(row.get("stage_no")): _as_float(row.get("green_sec"))
        for row in ordered_plan_rows
        if row.get("stage_no") is not None
    }
    min_green_profile = _build_min_green_profile(min_green_rows)
    schedule_count = len({r.get("schedule_no") for r in (schedule_rows or []) if r.get("schedule_no")})
    return {
        "current_cycle_s": cycle,
        "plan_no": first.get("plan_no"),
        "plan_name": first.get("plan_name"),
        "offset_s": _as_float(first.get("offset_sec")),
        "phase_sequence": [str(row.get("stage_no")) for row in ordered_plan_rows],
        "phase_splits": phase_splits,
        "stage_detail": phases,
        "min_green_s": min_green_profile.get("min_green_s"),
        "min_green_detail": min_green_profile.get("min_green_detail"),
        "time_plan_count": schedule_count or len({row.get("plan_no") for row in plan_rows}),
    }


def _release_movements_by_stage(rows: list[dict[str, Any]]) -> dict[str, str]:
    by_stage: dict[str, list[str]] = {}
    for row in rows:
        stage = str(row.get("stage_no") or "")
        if not stage:
            continue
        plan_no = str(row.get("plan_no") or "")
        movement = _signal_atom_movement(row.get("signal_atom")) or _signal_atom_movement(row.get("movement_key"))
        if not movement:
            link = row.get("link_id")
            turn = TURN_DIR_LABELS.get(int(_as_float(row.get("turn_dir_no"))), "")
            movement = f"{link}_{turn}" if link and turn else turn
        if movement:
            by_stage.setdefault(stage, []).append(movement)
            if plan_no:
                by_stage.setdefault(f"{plan_no}:{stage}", []).append(movement)
    return {
        stage: "、".join(dict.fromkeys(movements))
        for stage, movements in by_stage.items()
    }


def _release_movements_from_stage_cfg(rows: list[dict[str, Any]]) -> dict[str, str]:
    by_stage: dict[str, list[str]] = {}
    for row in rows:
        stage = str(row.get("stage_no") or "")
        if not stage:
            continue
        movements: list[str] = []
        combo = row.get("flow_combo_json")
        if isinstance(combo, list):
            for item in combo:
                if not isinstance(item, dict):
                    continue
                movement = _signal_atom_movement(item.get("signal_atom") or item.get("movement_key"))
                if movement:
                    movements.append(movement)
        if not movements:
            movements = [
                _signal_atom_movement(part)
                for part in re.split(r"[、,，/]+", str(row.get("stage_name") or ""))
            ]
            movements = [movement for movement in movements if movement]
        if movements:
            by_stage[stage] = list(dict.fromkeys(movements))
    return {stage: "、".join(movements) for stage, movements in by_stage.items()}


def _release_movements_from_stage_motor_flow(rows: list[dict[str, Any]]) -> dict[str, str]:
    by_stage: dict[str, list[str]] = {}
    for row in rows:
        stage = str(row.get("stage_no") or "")
        if not stage:
            continue
        direction = _dir8_approach_label(row.get("f_dir8_no"))
        turn = FLOW_TYPE_TURN_LABELS.get(int(_as_float(row.get("flow_type_no"))), "")
        if direction and turn:
            by_stage.setdefault(stage, []).append(f"{direction}{turn}")
    return {
        stage: "、".join(dict.fromkeys(movements))
        for stage, movements in by_stage.items()
    }


def _signal_atom_movement(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("atom:"):
        parts = text.split(":")
        text = parts[1] if len(parts) > 1 else text
    text = text.replace("左转", "左").replace("直行", "直").replace("右转", "右").replace("掉头", "掉")
    match = re.search(r"([东南西北]{1,2})(直|左|右|掉)", text)
    return "".join(match.groups()) if match else ""


def _dir8_approach_label(value: Any) -> str:
    try:
        return DIR8_APPROACH_LABELS.get(int(str(value)), "")
    except (TypeError, ValueError):
        return ""


def _build_min_green_profile(min_green_rows: list[dict[str, Any]] | None) -> dict[str, Any]:
    deduped = _dedupe_movement_rows(min_green_rows or [])
    detail: list[dict[str, Any]] = []
    by_movement: dict[str, float] = {}
    for row in deduped:
        key = _movement_key(row)
        min_green = _as_float(row.get("min_green_time"))
        by_movement[key] = min_green
        detail.append(
            {
                "link_id": row.get("link_id"),
                "turn_dir_no": row.get("turn_dir_no"),
                "dir8_code": row.get("dir8_code"),
                "min_green_time": min_green,
                "green_time_plan": _as_float(row.get("green_time_plan")),
                "has_pedestrian": row.get("has_pedestrian"),
            }
        )
    times = [v for v in by_movement.values() if v > 0]
    return {
        "min_green_s": by_movement if by_movement else None,
        "min_green_detail": detail,
        "min_green_min_s": min(times) if times else None,
        "min_green_max_s": max(times) if times else None,
    }


def _build_context(
    inter: dict[str, Any],
    day_of_week: int,
    complaint_rows: list[dict[str, Any]],
    survey_rows: list[dict[str, Any]],
    metrics: dict[str, Any],
    checklist_queries: list[dict[str, Any]] | None = None,
    step_index: int | None = None,
    aoi_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    complaints = [
        str(row.get("core_problem_desc") or row.get("complaint_type") or "")
        for row in complaint_rows
        if row
    ]
    surveys = [str(row.get("issue_desc") or row.get("issue_type") or "") for row in survey_rows if row]
    aoi_sources = aoi_rows or []
    poi_tags = [
        tag
        for tag in dict.fromkeys([*_infer_poi_tags(complaints + surveys), *[_aoi_tag(row.get("type")) for row in aoi_sources]])
        if tag
    ]
    checklist = checklist_queries or []
    has_data_count = sum(1 for item in checklist if item.get("status") == "has_data")
    no_data_items = [item["item_id"] for item in checklist if item.get("status") == "no_data"]
    return {
        "time_period": _period_tag(day_of_week, step_index),
        "day_of_week": day_of_week,
        "time_window": _day_window_label(day_of_week, step_index),
        "query_granularity": "step_index" if step_index is not None else "day_of_week",
        "complaints": [item for item in complaints if item],
        "field_survey_issues": [item for item in surveys if item],
        "poi": poi_tags,
        "aoi_sources": aoi_sources,
        "checklist_summary": {
            "total": len(checklist),
            "has_data": has_data_count,
            "no_data": len(no_data_items),
            "missing_items": no_data_items,
        },
        "data_quality": {
            "source": "postgresql_dws",
            "has_evaluation": bool(metrics.get("saturation")),
            "has_turn_flow": bool(metrics.get("movement_volume")),
        },
        "data_source_tables": [item.get("table", "") for item in checklist if item.get("table")],
    }


def _aoi_tag(aoi_type: Any) -> str:
    mapping = {
        "学校": "school",
        "医院": "hospital",
        "商圈": "commercial",
        "港区/园区": "port",
        "公交站": "transit",
        "停车场": "parking",
        "查验口/收费站": "checkpoint",
    }
    return mapping.get(str(aoi_type or ""), "")


def _infer_poi_tags(texts: list[str]) -> list[str]:
    keywords = {
        "school": ("学校", "小学", "中学", "幼儿园"),
        "hospital": ("医院", "门诊", "急救"),
        "commercial": ("商圈", "商场", "购物"),
        "transit": ("公交", "地铁", "枢纽"),
        "port": ("港", "物流", "货运", "园区", "产业园"),
        "parking": ("停车场", "停车", "出入口"),
    }
    joined = " ".join(texts)
    tags: list[str] = []
    for tag, words in keywords.items():
        if any(word in joined for word in words):
            tags.append(tag)
    return tags
