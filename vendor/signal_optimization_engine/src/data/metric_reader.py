"""PostgreSQL 指标图层数据读取：路口坐标 + xianchang schema 评价指标。"""

from __future__ import annotations

import os
import re
from typing import Any

from preprocessing.timing.dir8_encoding import DIR8_LABELS, dir4_code_from_dir8_no, dir8_label, normalize_dir8_no

# 指标目录：level 为 UI 分组（路口级/投诉等）；dimension 决定地图要素粒度与 SQL
METRIC_DIMENSION_LABELS: dict[str, str] = {
    "intersection": "路口整体",
    "approach": "进口方向",
    "turn": "转向",
    "lane": "车道",
}

METRIC_CATALOG: dict[str, dict[str, Any]] = {
    "saturation_max": {
        "label": "最大饱和度",
        "level": "intersection",
        "dimension": "intersection",
        "table": "dws_inter_evaluation_5min_mm",
        "value_field": "saturation_max",
        "value_type": "numeric",
        "unit": "",
        "description": "路口所有转向饱和度的最大值",
        "thresholds": [0.0, 0.6, 0.7, 0.8, 0.9, 1.0],
        "colors": ["#22c55e", "#84cc16", "#eab308", "#f97316", "#ef4444", "#991b1b"],
    },
    "saturation_avg": {
        "label": "平均饱和度",
        "level": "intersection",
        "dimension": "intersection",
        "table": "dws_inter_evaluation_5min_mm",
        "value_field": "saturation_avg",
        "value_type": "numeric",
        "unit": "",
        "description": "路口所有转向饱和度的算术平均",
        "thresholds": [0.0, 0.6, 0.7, 0.8, 0.9, 1.0],
        "colors": ["#22c55e", "#84cc16", "#eab308", "#f97316", "#ef4444", "#991b1b"],
    },
    "unbalance_index": {
        "label": "失衡指数",
        "level": "intersection",
        "dimension": "intersection",
        "table": "dws_inter_evaluation_5min_mm",
        "value_field": "unbalance_index",
        "value_type": "numeric",
        "unit": "",
        "description": "各转向绿灯利用率标准差，越大表示方向间负荷越不均衡",
        "thresholds": [0.0, 0.05, 0.10, 0.15, 0.20, 0.30],
        "colors": ["#22c55e", "#84cc16", "#eab308", "#f97316", "#ef4444", "#991b1b"],
    },
    "level_of_service": {
        "label": "服务水平",
        "level": "intersection",
        "dimension": "intersection",
        "table": "dws_inter_evaluation_5min_mm",
        "value_field": "level_of_service",
        "value_type": "categorical",
        "unit": "",
        "description": "基于最大饱和度的 A~F 等级",
        "categories": {
            "A": {"label": "A-畅通", "color": "#22c55e", "rank": 1},
            "B": {"label": "B-稳定", "color": "#84cc16", "rank": 2},
            "C": {"label": "C-较稳", "color": "#eab308", "rank": 3},
            "D": {"label": "D-临界", "color": "#f97316", "rank": 4},
            "E": {"label": "E-拥堵", "color": "#ef4444", "rank": 5},
            "F": {"label": "F-阻塞", "color": "#991b1b", "rank": 6},
        },
    },
    "turn_saturation": {
        "label": "转向饱和度",
        "level": "intersection",
        "dimension": "turn",
        "table": "dws_turn_saturation_5min_mm",
        "value_field": "turn_saturation",
        "value_type": "numeric",
        "unit": "",
        "description": "进口转向级饱和度",
        "thresholds": [0.0, 0.6, 0.7, 0.8, 0.9, 1.0],
        "colors": ["#22c55e", "#84cc16", "#eab308", "#f97316", "#ef4444", "#991b1b"],
    },
    "green_utilization": {
        "label": "绿灯利用率",
        "level": "intersection",
        "dimension": "turn",
        "table": "dws_turn_green_utilization_5min_mm",
        "value_field": "green_utilization",
        "value_type": "numeric",
        "unit": "",
        "description": "进口转向绿灯利用率；<0.3 严重，0.3~0.6 中等，>0.6 正常",
        "severity_direction": "inverse",
        "thresholds": [0.0, 0.3, 0.6],
        "colors": ["#991b1b", "#f97316", "#22c55e"],
        "legend_labels": ["< 0.3 严重", "0.3 ~ 0.6 中等", "> 0.6 正常"],
    },
    "lane_saturation": {
        "label": "车道饱和度",
        "level": "intersection",
        "dimension": "lane",
        "table": "dws_lane_saturation_5min_mm",
        "value_field": "lane_saturation",
        "value_type": "numeric",
        "unit": "",
        "description": "车道级饱和度",
        "thresholds": [0.0, 0.6, 0.7, 0.8, 0.9, 1.0],
        "colors": ["#22c55e", "#84cc16", "#eab308", "#f97316", "#ef4444", "#991b1b"],
    },
    "complaint_count": {
        "label": "投诉条数",
        "level": "complaint",
        "table": "dwd_tfc_complaint_inter_issue",
        "value_field": "complaint_count",
        "value_type": "numeric",
        "unit": "件",
        "description": "2025 全年信号类民意投诉，按路口聚合",
        "thresholds": [0, 10, 20, 50, 100],
        "colors": ["#059669", "#2563EB", "#D97706", "#EA580C", "#B91C1C"],
        "legend_labels": ["10 件以下", "10-19 件", "20-49 件", "50-99 件", "100 件及以上"],
    },
    "manual_survey_issue_cnt": {
        "label": "调查问题记录数",
        "level": "manual_survey",
        "table": "dwd_ctl_inter_manual_survey_issue",
        "value_field": "issue_record_cnt",
        "value_type": "numeric",
        "unit": "条",
        "description": "信控路口人工调查问题，按路口聚合 issue_record_cnt",
        "thresholds": [0, 1, 2, 3, 5],
        "colors": ["#94a3b8", "#fbbf24", "#f97316", "#ef4444", "#991b1b"],
        "legend_labels": ["1 条", "2 条", "3 条", "4-5 条", "6 条及以上"],
    },
    "field_survey_issue_cnt": {
        "label": "交通组织调研问题数",
        "level": "field_survey",
        "table": "dwd_tfc_field_survey_inter_issue",
        "value_field": "issue_count",
        "value_type": "numeric",
        "unit": "条",
        "description": "重点路口交通组织调研报告问题明细，按路口聚合",
        "thresholds": [0, 1, 2, 3, 5],
        "colors": ["#94a3b8", "#fbbf24", "#f97316", "#ef4444", "#991b1b"],
        "legend_labels": ["1 条", "2 条", "3 条", "4-5 条", "6 条及以上"],
    },
    "link_stop_time_sec": {
        "label": "延误时间",
        "level": "intersection",
        "dimension": "approach",
        "table": "dws_inter_link_status_5min_mm",
        "value_field": "stop_time_sec",
        "value_type": "numeric",
        "unit": "秒",
        "description": "进口 link 延误时间（秒），来自路况评价 delay_dur",
        "thresholds": [0, 30, 60, 90, 120],
        "colors": ["#22c55e", "#84cc16", "#eab308", "#f97316", "#ef4444"],
        "legend_labels": ["< 30s", "30-59s", "60-89s", "90-119s", "≥ 120s"],
    },
    "link_stop_times": {
        "label": "停车次数",
        "level": "intersection",
        "dimension": "approach",
        "table": "dws_inter_link_status_5min_mm",
        "value_field": "stop_times",
        "value_type": "numeric",
        "unit": "次",
        "description": "进口 link 平均停车次数 = 延误时间 / 主方向平均红灯时长",
        "thresholds": [0, 0.5, 1.0, 1.5, 2.0],
        "colors": ["#22c55e", "#84cc16", "#eab308", "#f97316", "#ef4444"],
        "legend_labels": ["< 0.5", "0.5-0.9", "1.0-1.4", "1.5-1.9", "≥ 2.0"],
    },
    "link_queue_len_est_m": {
        "label": "排队长度",
        "level": "intersection",
        "dimension": "approach",
        "table": "dws_inter_link_status_5min_mm",
        "value_field": "queue_len_est_m",
        "value_type": "numeric",
        "unit": "米",
        "description": "进口 link 排队长度估计（米）",
        "thresholds": [0, 50, 100, 150, 200],
        "colors": ["#22c55e", "#84cc16", "#eab308", "#f97316", "#ef4444"],
        "legend_labels": ["< 50m", "50-99m", "100-149m", "150-199m", "≥ 200m"],
    },
}

APPROACH_METRIC_IDS = ("link_stop_time_sec", "link_stop_times", "link_queue_len_est_m")
INTERSECTION_SERIES_METRIC_IDS = ("saturation_max", "saturation_avg", "unbalance_index")
METRIC_SERIES_IDS = APPROACH_METRIC_IDS + INTERSECTION_SERIES_METRIC_IDS


TURN_DIR_LABELS = {0: "掉头", 1: "左转", 2: "直行", 3: "右转"}


def _metric_dimension(cfg: dict[str, Any]) -> str:
    """地图渲染与 SQL 分支使用的空间维度。"""
    return str(cfg.get("dimension") or cfg.get("level") or "intersection")


def intersection_dimensions_for_api() -> list[dict[str, str]]:
    """路口级下可用的查看维度（前端维度切换）。"""
    return [{"id": dim_id, "label": label} for dim_id, label in METRIC_DIMENSION_LABELS.items()]

_WKT_POINT = re.compile(
    r"POINT\s*\(\s*([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s*\)",
    re.IGNORECASE,
)


def metric_catalog_for_api() -> list[dict[str, Any]]:
    """返回前端可用的指标目录（不含 SQL 细节）。"""
    items: list[dict[str, Any]] = []
    for metric_id, cfg in METRIC_CATALOG.items():
        item = {
            "id": metric_id,
            "label": cfg["label"],
            "level": cfg["level"],
            "dimension": _metric_dimension(cfg),
            "dimensionLabel": METRIC_DIMENSION_LABELS.get(_metric_dimension(cfg), _metric_dimension(cfg)),
            "valueType": cfg["value_type"],
            "unit": cfg.get("unit", ""),
            "description": cfg.get("description", ""),
        }
        if cfg["value_type"] == "numeric":
            item["thresholds"] = cfg.get("thresholds", [])
            item["colors"] = cfg.get("colors", [])
            if cfg.get("severity_direction"):
                item["severityDirection"] = cfg["severity_direction"]
            if cfg.get("legend_labels"):
                item["legendLabels"] = cfg["legend_labels"]
        else:
            item["categories"] = cfg.get("categories", {})
        items.append(item)
    return items


def parse_geom_center(value: Any) -> tuple[float, float] | None:
    """解析 WKT POINT(lon lat) 或 'lon,lat' 文本。"""
    text = str(value or "").strip()
    if not text:
        return None
    match = _WKT_POINT.search(text)
    if match:
        return float(match.group(1)), float(match.group(2))
    parts = [p.strip() for p in text.split(",")]
    if len(parts) == 2:
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            return None
    return None


def step_index_to_hhmm(step_index: int) -> str:
    minutes = max(0, min(int(step_index), 287)) * 5
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _timing_schema() -> str:
    return os.getenv("PG_TIMING_SCHEMA") or os.getenv("PG_FLOW_SCHEMA", "xianchang")


def _dim_inter_qualified() -> str:
    schema = os.getenv("PGSCHEMA", "road6")
    table = os.getenv("PG_DIM_INTER_TABLE", "dim_inter_info")
    return f"{_qident(schema)}.{_qident(table)}"


def _road_schema() -> str:
    return os.getenv("PGSCHEMA", "road6")


def _link_ft_qualified() -> str:
    schema = _road_schema()
    table = os.getenv("PG_LINK_FT_TABLE", "dwd_tfc_rltn_wide_inter_ft_link")
    return f"{_qident(schema)}.{_qident(table)}"


def _link_dim_qualified() -> str:
    schema = _road_schema()
    table = os.getenv("PG_DIM_LINK_TABLE", "dim_link_info")
    if table == "dim_road_link":
        table = "dim_link_info"
    return f"{_qident(schema)}.{_qident(table)}"


def fetch_link_approach_geometries(
    conn,
    keys: list[tuple[str, str]],
) -> dict[str, dict[str, Any]]:
    """读取 (inter_id, link_id) 对应的进口锚点经纬度与 approach_angle。"""
    if not keys:
        return {}
    inter_ids = sorted({k[0] for k in keys})
    link_ids = sorted({k[1] for k in keys})
    ft = _link_ft_qualified()
    dim = _link_dim_qualified()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT r.inter_id::text AS inter_id,
                   r.link_id::text AS link_id,
                   r.link_role,
                   r.approach_angle,
                   r.dir8_code,
                   r.dir8_label,
                   COALESCE(r.lane_num, r.c_lane_num, 1) AS lane_num,
                   CASE
                     WHEN r.link_role = 'entrance' AND d.t_inter_id::text = r.inter_id::text
                       THEN ST_X(ST_EndPoint(d.geom))
                     WHEN r.link_role = 'exit' AND d.f_inter_id::text = r.inter_id::text
                       THEN ST_X(ST_StartPoint(d.geom))
                     WHEN d.t_inter_id::text = r.inter_id::text
                       THEN ST_X(ST_EndPoint(d.geom))
                     ELSE ST_X(ST_StartPoint(d.geom))
                   END AS anchor_lon,
                   CASE
                     WHEN r.link_role = 'entrance' AND d.t_inter_id::text = r.inter_id::text
                       THEN ST_Y(ST_EndPoint(d.geom))
                     WHEN r.link_role = 'exit' AND d.f_inter_id::text = r.inter_id::text
                       THEN ST_Y(ST_StartPoint(d.geom))
                     WHEN d.t_inter_id::text = r.inter_id::text
                       THEN ST_Y(ST_EndPoint(d.geom))
                     ELSE ST_Y(ST_StartPoint(d.geom))
                   END AS anchor_lat
            FROM {ft} r
            JOIN {dim} d ON d.link_id::text = r.link_id::text
            WHERE r.inter_id::text = ANY(%s)
              AND r.link_id::text = ANY(%s)
            """,
            (inter_ids, link_ids),
        )
        rows = cur.fetchall()

    out: dict[str, dict[str, Any]] = {}
    wanted = {f"{a}:{b}" for a, b in keys}
    for row in rows:
        inter_id = str(row.get("inter_id") or "").strip()
        link_id = str(row.get("link_id") or "").strip()
        key = f"{inter_id}:{link_id}"
        if key not in wanted:
            continue
        lon = _to_float(row.get("anchor_lon"))
        lat = _to_float(row.get("anchor_lat"))
        if lon is None or lat is None:
            continue
        approach = _to_float(row.get("approach_angle"))
        out[key] = {
            "linkLon": round(lon, 7),
            "linkLat": round(lat, 7),
            "approachAngle": round(approach, 3) if approach is not None else None,
            "dir8Code": normalize_dir8_no(row.get("dir8_code")),
            "dir8Label": str(row.get("dir8_label") or "").strip(),
            "laneNum": max(1, _to_int(row.get("lane_num")) or 1),
            "linkRole": str(row.get("link_role") or "").strip(),
        }
    return out


def _offset_meters(lon: float, lat: float, bearing_deg: float, distance_m: float) -> tuple[float, float]:
    import math

    bearing = math.radians(bearing_deg)
    dlat = (distance_m * math.cos(bearing)) / 111_320.0
    dlon = (distance_m * math.sin(bearing)) / (111_320.0 * max(math.cos(math.radians(lat)), 0.2))
    return lon + dlon, lat + dlat


def _inbound_bearing(approach_angle: float | None, dir8: int | None = None) -> float:
    if approach_angle is not None:
        return (float(approach_angle) + 180.0) % 360.0
    if dir8 is not None:
        return (float(dir8) * 45.0 + 180.0) % 360.0
    return 180.0


def _turn_arrow_coords(
    lon: float,
    lat: float,
    *,
    approach_angle: float | None,
    turn_dir_no: int | None,
    dir8: int | None = None,
    scale: float = 1.0,
) -> list[tuple[float, float]]:
    """在 link 锚点处生成转向箭头折线（单位：米）。"""
    inbound = _inbound_bearing(approach_angle, dir8)
    turn = turn_dir_no if turn_dir_no is not None else 2
    s = max(0.6, float(scale))
    # 将同一进口的不同转向沿法向做轻微平移，减少重叠“乱线”。
    lateral_by_turn = {
        0: -7.0,  # 掉头
        1: -4.2,  # 左转
        2: 0.0,   # 直行
        3: 4.2,   # 右转
    }
    lateral = lateral_by_turn.get(turn, 0.0) * s
    right_perp = (inbound + 90.0) % 360.0

    anchor = _offset_meters(lon, lat, right_perp, lateral)
    entry = _offset_meters(anchor[0], anchor[1], inbound, -18 * s)
    stem = _offset_meters(anchor[0], anchor[1], inbound, 9 * s)

    if turn == 2:
        tip = _offset_meters(stem[0], stem[1], inbound, 15 * s)
        return [entry, anchor, stem, tip]
    if turn == 1:
        tip = _offset_meters(stem[0], stem[1], inbound - 90, 18 * s)
        return [entry, anchor, stem, tip]
    if turn == 3:
        tip = _offset_meters(stem[0], stem[1], inbound + 90, 14 * s)
        return [entry, anchor, stem, tip]
    if turn == 0:
        side = _offset_meters(stem[0], stem[1], inbound - 90, 11 * s)
        tip = _offset_meters(side[0], side[1], inbound - 180, 15 * s)
        return [entry, anchor, stem, side, tip]
    tip = _offset_meters(stem[0], stem[1], inbound, 14 * s)
    return [entry, anchor, stem, tip]


def _lane_line_coords(
    lon: float,
    lat: float,
    *,
    approach_angle: float | None,
    lane_no: int | None,
    lane_count: int,
    dir8: int | None = None,
    scale: float = 1.0,
) -> list[tuple[float, float]]:
    """在 link 锚点处生成单条车道导向线（单位：米）。"""
    approach = float(approach_angle) if approach_angle is not None else (
        float(dir8) * 45.0 if dir8 is not None else 0.0
    )
    inbound = _inbound_bearing(approach_angle, dir8)
    lane_width = 3.4
    s = max(0.6, float(scale))
    idx = max(0, (lane_no or 1) - 1)
    center = (max(1, lane_count) - 1) / 2.0
    lateral = (idx - center) * lane_width
    perp = (approach + 90.0) % 360.0
    start = _offset_meters(lon, lat, approach, -36 * s)
    end = _offset_meters(lon, lat, inbound, 4 * s)
    start = _offset_meters(start[0], start[1], perp, lateral)
    end = _offset_meters(end[0], end[1], perp, lateral)
    return [start, end]


def _coords_to_linestring(coords: list[tuple[float, float]]) -> dict[str, Any]:
    return {"type": "LineString", "coordinates": [[lon, lat] for lon, lat in coords]}
    schema = os.getenv("PGSCHEMA", "road6")
    table = os.getenv("PG_DIM_INTER_TABLE", "dim_inter_info")
    return f"{_qident(schema)}.{_qident(table)}"


def fetch_intersection_geometries(
    conn,
    *,
    inter_ids: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """读取路口中心坐标与名称。"""
    qualified = _dim_inter_qualified()
    params: list[Any] = []
    where = "geom_center IS NOT NULL AND btrim(geom_center::text) <> ''"
    if inter_ids:
        where += " AND inter_id::text = ANY(%s)"
        params.append(inter_ids)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT inter_id::text AS inter_id, inter_name, geom_center::text AS geom_center
            FROM {qualified}
            WHERE {where}
            """,
            params or None,
        )
        rows = cur.fetchall()

    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        inter_id = str(row.get("inter_id") or "").strip()
        coords = parse_geom_center(row.get("geom_center"))
        if not inter_id or not coords:
            continue
        lon, lat = coords
        out[inter_id] = {
            "interId": inter_id,
            "interName": str(row.get("inter_name") or "").strip(),
            "lon": lon,
            "lat": lat,
        }
    return out


def fetch_available_time_slices(conn, metric_id: str) -> dict[str, Any]:
    """返回某指标表内已有的星期与时间片范围。"""
    cfg = METRIC_CATALOG.get(metric_id)
    if not cfg:
        raise ValueError(f"未知指标: {metric_id}")

    schema = _timing_schema()
    table = cfg["table"]
    qualified = f"{_qident(schema)}.{_qident(table)}"

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT day_of_week, MIN(step_index) AS min_step, MAX(step_index) AS max_step,
                   COUNT(DISTINCT inter_id) AS inter_count
            FROM {qualified}
            WHERE is_deleted = 0
            GROUP BY day_of_week
            ORDER BY day_of_week
            """,
        )
        rows = cur.fetchall()

    days = []
    for row in rows:
        dow = int(row["day_of_week"])
        days.append(
            {
                "dayOfWeek": dow,
                "dayLabel": _day_label(dow),
                "minStepIndex": int(row["min_step"]),
                "maxStepIndex": int(row["max_step"]),
                "interCount": int(row["inter_count"]),
            }
        )
    return {"metricId": metric_id, "days": days}


def fetch_metric_layer(
    conn,
    *,
    metric_id: str,
    day_of_week: int,
    step_index: int,
    inter_ids: list[str] | None = None,
) -> dict[str, Any]:
    """读取指定指标图层，返回 GeoJSON FeatureCollection 风格结构。"""
    cfg = METRIC_CATALOG.get(metric_id)
    if not cfg:
        raise ValueError(f"未知指标: {metric_id}")

    dimension = _metric_dimension(cfg)
    schema = _timing_schema()
    table = cfg["table"]
    value_field = cfg["value_field"]
    qualified = f"{_qident(schema)}.{_qident(table)}"

    params: list[Any] = [day_of_week, step_index]
    inter_filter = ""
    if inter_ids:
        inter_filter = " AND m.inter_id::text = ANY(%s)"
        params.append(inter_ids)

    if dimension == "intersection":
        sql = f"""
            SELECT m.inter_id::text AS inter_id,
                   COALESCE(m.inter_name, d.inter_name) AS inter_name,
                   m.{_qident(value_field)} AS metric_value,
                   d.geom_center::text AS geom_center
            FROM {qualified} m
            JOIN {_dim_inter_qualified()} d ON d.inter_id::text = m.inter_id::text
            WHERE m.is_deleted = 0
              AND m.day_of_week = %s
              AND m.step_index = %s
              AND d.geom_center IS NOT NULL
              {inter_filter}
        """
    elif dimension == "approach":
        sql = f"""
            SELECT m.inter_id::text AS inter_id,
                   COALESCE(m.inter_name, d.inter_name) AS inter_name,
                   m.link_id::text AS link_id,
                   m.link_name,
                   m.dir8_code,
                   m.dir8_label,
                   m.{_qident(value_field)} AS metric_value,
                   d.geom_center::text AS geom_center
            FROM {qualified} m
            JOIN {_dim_inter_qualified()} d ON d.inter_id::text = m.inter_id::text
            WHERE m.is_deleted = 0
              AND m.day_of_week = %s
              AND m.step_index = %s
              AND d.geom_center IS NOT NULL
              AND m.{_qident(value_field)} IS NOT NULL
              {inter_filter}
        """
    elif dimension == "turn":
        sql = f"""
            SELECT m.inter_id::text AS inter_id,
                   COALESCE(m.inter_name, d.inter_name) AS inter_name,
                   m.link_id::text AS link_id,
                   m.turn_dir_no,
                   m.dir8_code,
                   m.{_qident(value_field)} AS metric_value,
                   d.geom_center::text AS geom_center
            FROM {qualified} m
            JOIN {_dim_inter_qualified()} d ON d.inter_id::text = m.inter_id::text
            WHERE m.is_deleted = 0
              AND m.day_of_week = %s
              AND m.step_index = %s
              AND d.geom_center IS NOT NULL
              {inter_filter}
        """
    else:
        turn_qualified = f"{_qident(schema)}.{_qident('dws_turn_saturation_5min_mm')}"
        sql = f"""
            SELECT m.inter_id::text AS inter_id,
                   COALESCE(m.inter_name, d.inter_name) AS inter_name,
                   m.link_id::text AS link_id,
                   m.lane_no,
                   m.turn_dir_no,
                   COALESCE(t.dir8_code, g.dir8_code) AS dir8_code,
                   m.{_qident(value_field)} AS metric_value,
                   d.geom_center::text AS geom_center
            FROM {qualified} m
            JOIN {_dim_inter_qualified()} d ON d.inter_id::text = m.inter_id::text
            LEFT JOIN {turn_qualified} t
              ON t.inter_id::text = m.inter_id::text
             AND t.link_id::text = m.link_id::text
             AND t.day_of_week = m.day_of_week
             AND t.step_index = m.step_index
             AND t.is_deleted = 0
            LEFT JOIN (
                SELECT DISTINCT ON (inter_id, link_id)
                       inter_id, link_id, dir8_code
                FROM {turn_qualified}
                WHERE is_deleted = 0
                ORDER BY inter_id, link_id, day_of_week, step_index
            ) g ON g.inter_id::text = m.inter_id::text
               AND g.link_id::text = m.link_id::text
            WHERE m.is_deleted = 0
              AND m.day_of_week = %s
              AND m.step_index = %s
              AND d.geom_center IS NOT NULL
              {inter_filter}
        """

    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    link_keys: list[tuple[str, str]] = []
    if dimension in ("approach", "turn", "lane"):
        seen: set[str] = set()
        for row in rows:
            inter_id = str(row.get("inter_id") or "").strip()
            link_id = str(row.get("link_id") or "").strip()
            if not inter_id or not link_id:
                continue
            key = f"{inter_id}:{link_id}"
            if key not in seen:
                seen.add(key)
                link_keys.append((inter_id, link_id))
    link_geos = fetch_link_approach_geometries(conn, link_keys) if link_keys else {}

    lane_counts: dict[str, int] = {}
    if dimension == "lane":
        for row in rows:
            inter_id = str(row.get("inter_id") or "").strip()
            link_id = str(row.get("link_id") or "").strip()
            if not inter_id or not link_id:
                continue
            key = f"{inter_id}:{link_id}"
            lane_no = _to_int(row.get("lane_no")) or 0
            lane_counts[key] = max(lane_counts.get(key, 0), lane_no)

    features: list[dict[str, Any]] = []
    value_numbers: list[float] = []

    for row in rows:
        center = parse_geom_center(row.get("geom_center"))
        if not center:
            continue
        base_lon, base_lat = center
        inter_id = str(row.get("inter_id") or "")
        inter_name = str(row.get("inter_name") or "").strip()
        raw_value = row.get("metric_value")

        props: dict[str, Any] = {
            "interId": inter_id,
            "interName": inter_name,
            "centerLon": base_lon,
            "centerLat": base_lat,
            "metricId": metric_id,
            "metricLabel": cfg["label"],
            "dimension": dimension,
            "dimensionLabel": METRIC_DIMENSION_LABELS.get(dimension, dimension),
            "dayOfWeek": day_of_week,
            "stepIndex": step_index,
            "timeLabel": step_index_to_hhmm(step_index),
        }

        lon, lat = base_lon, base_lat
        feature_id = inter_id
        geometry: dict[str, Any] = {"type": "Point", "coordinates": [lon, lat]}
        geom_scale = 1.0

        if dimension == "approach":
            dir8 = normalize_dir8_no(row.get("dir8_code"))
            link_id = str(row.get("link_id") or "")
            link_name = str(row.get("link_name") or "").strip()
            link_key = f"{inter_id}:{link_id}"
            link_geo = link_geos.get(link_key) or {}
            if link_geo.get("linkLon") is not None and link_geo.get("linkLat") is not None:
                lon = float(link_geo["linkLon"])
                lat = float(link_geo["linkLat"])
            else:
                lon, lat = _offset_by_dir8(base_lon, base_lat, dir8)
            props.update(
                {
                    "linkId": link_id,
                    "linkName": link_name,
                    "dir8Code": link_geo.get("dir8Code", dir8),
                    "dir8Label": link_geo.get("dir8Label") or str(row.get("dir8_label") or "").strip()
                    or dir8_label(dir8),
                    "linkLon": lon,
                    "linkLat": lat,
                    "approachAngle": link_geo.get("approachAngle"),
                }
            )
            geometry = {"type": "Point", "coordinates": [lon, lat]}
            feature_id = f"{inter_id}:{link_id}"
        elif dimension == "turn":
            dir8 = normalize_dir8_no(row.get("dir8_code"))
            turn_dir = _to_int(row.get("turn_dir_no"))
            link_id = str(row.get("link_id") or "")
            link_key = f"{inter_id}:{link_id}"
            link_geo = link_geos.get(link_key) or {}
            if link_geo.get("linkLon") is not None and link_geo.get("linkLat") is not None:
                lon = float(link_geo["linkLon"])
                lat = float(link_geo["linkLat"])
            else:
                lon, lat = _offset_by_dir8(base_lon, base_lat, dir8)
            props.update(
                {
                    "linkId": link_id,
                    "dir8Code": link_geo.get("dir8Code", dir8),
                    "dir8Label": link_geo.get("dir8Label") or dir8_label(dir8),
                    "turnDirNo": turn_dir,
                    "turnLabel": TURN_DIR_LABELS.get(turn_dir, ""),
                    "linkLon": lon,
                    "linkLat": lat,
                    "approachAngle": link_geo.get("approachAngle"),
                }
            )
            arrow_coords = _turn_arrow_coords(
                lon,
                lat,
                approach_angle=link_geo.get("approachAngle"),
                turn_dir_no=turn_dir,
                dir8=props.get("dir8Code"),
                scale=geom_scale,
            )
            geometry = _coords_to_linestring(arrow_coords)
            feature_id = f"{inter_id}:{link_id}:{turn_dir}"
        elif dimension == "lane":
            turn_dir = _to_int(row.get("turn_dir_no"))
            lane_no = _to_int(row.get("lane_no"))
            link_id = str(row.get("link_id") or "")
            link_key = f"{inter_id}:{link_id}"
            link_geo = link_geos.get(link_key) or {}
            dir8 = normalize_dir8_no(row.get("dir8_code")) or link_geo.get("dir8Code")
            if link_geo.get("linkLon") is not None and link_geo.get("linkLat") is not None:
                lon = float(link_geo["linkLon"])
                lat = float(link_geo["linkLat"])
            else:
                lon, lat = base_lon, base_lat
            lane_count = max(
                lane_counts.get(link_key, 0),
                link_geo.get("laneNum") or 1,
                lane_no or 1,
            )
            props.update(
                {
                    "linkId": link_id,
                    "laneNo": lane_no,
                    "turnDirNo": turn_dir,
                    "turnLabel": TURN_DIR_LABELS.get(turn_dir, ""),
                    "dir8Code": dir8,
                    "dir8Label": link_geo.get("dir8Label") or dir8_label(dir8),
                    "linkLon": lon,
                    "linkLat": lat,
                    "approachAngle": link_geo.get("approachAngle"),
                    "laneCount": lane_count,
                }
            )
            lane_coords = _lane_line_coords(
                lon,
                lat,
                approach_angle=link_geo.get("approachAngle"),
                lane_no=lane_no,
                lane_count=lane_count,
                dir8=dir8,
                scale=geom_scale,
            )
            geometry = _coords_to_linestring(lane_coords)
            feature_id = f"{inter_id}:{link_id}:{lane_no}"

        if cfg["value_type"] == "categorical":
            cat = str(raw_value or "").strip().upper()
            cat_cfg = (cfg.get("categories") or {}).get(cat, {})
            props["value"] = cat
            props["valueLabel"] = cat_cfg.get("label", cat)
            props["color"] = cat_cfg.get("color", "#64748b")
            props["rank"] = cat_cfg.get("rank", 0)
            props["valueType"] = "categorical"
        else:
            num = _to_float(raw_value)
            if num is None:
                continue
            props["value"] = round(num, 4)
            props["valueType"] = "numeric"
            value_numbers.append(num)

        features.append(
            {
                "type": "Feature",
                "id": feature_id,
                "geometry": geometry,
                "properties": props,
            }
        )

    stats = _value_stats(value_numbers)
    return {
        "type": "FeatureCollection",
        "metricId": metric_id,
        "metricLabel": cfg["label"],
        "level": cfg["level"],
        "dimension": dimension,
        "dimensionLabel": METRIC_DIMENSION_LABELS.get(dimension, dimension),
        "dayOfWeek": day_of_week,
        "stepIndex": step_index,
        "timeLabel": step_index_to_hhmm(step_index),
        "featureCount": len(features),
        "valueStats": stats,
        "features": features,
    }


def fetch_inter_link_status_series(
    conn,
    *,
    inter_id: str,
    day_of_week: int,
    metric_id: str,
) -> dict[str, Any]:
    """读取某路口指标在一天内的时序（用于曲线图）。"""
    return fetch_metric_series(
        conn,
        inter_id=inter_id,
        day_of_week=day_of_week,
        metric_id=metric_id,
    )


def fetch_metric_series(
    conn,
    *,
    inter_id: str,
    day_of_week: int,
    metric_id: str,
) -> dict[str, Any]:
    """读取某路口单日指标时序：路口整体为单曲线，进口方向按 link 分序列。"""
    cfg = METRIC_CATALOG.get(metric_id)
    if not cfg:
        raise ValueError(f"未知指标: {metric_id}")
    dimension = _metric_dimension(cfg)
    if dimension == "approach":
        return _fetch_approach_metric_series(conn, cfg=cfg, inter_id=inter_id, day_of_week=day_of_week, metric_id=metric_id)
    if dimension == "intersection" and metric_id in INTERSECTION_SERIES_METRIC_IDS:
        return _fetch_intersection_metric_series(
            conn, cfg=cfg, inter_id=inter_id, day_of_week=day_of_week, metric_id=metric_id
        )
    raise ValueError(f"指标不支持时序曲线: {metric_id}")


def _fetch_intersection_metric_series(
    conn,
    *,
    cfg: dict[str, Any],
    inter_id: str,
    day_of_week: int,
    metric_id: str,
) -> dict[str, Any]:
    schema = _timing_schema()
    table = cfg["table"]
    value_field = cfg["value_field"]
    qualified = f"{_qident(schema)}.{_qident(table)}"

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT m.inter_id::text AS inter_id,
                   COALESCE(m.inter_name, d.inter_name) AS inter_name,
                   m.step_index,
                   m.{_qident(value_field)} AS metric_value
            FROM {qualified} m
            LEFT JOIN {_dim_inter_qualified()} d ON d.inter_id::text = m.inter_id::text
            WHERE m.is_deleted = 0
              AND m.inter_id::text = %s
              AND m.day_of_week = %s
              AND m.{_qident(value_field)} IS NOT NULL
            ORDER BY m.step_index
            """,
            (inter_id.strip(), day_of_week),
        )
        rows = cur.fetchall()

    inter_name = ""
    values: list[dict[str, Any]] = []
    for row in rows:
        inter_name = str(row.get("inter_name") or "").strip()
        step = _to_int(row.get("step_index"))
        num = _to_float(row.get("metric_value"))
        if step is None or num is None:
            continue
        values.append(
            {
                "stepIndex": step,
                "timeLabel": step_index_to_hhmm(step),
                "value": round(num, 4),
            }
        )

    return {
        "interId": inter_id.strip(),
        "interName": inter_name,
        "dayOfWeek": day_of_week,
        "dayLabel": _day_label(day_of_week),
        "metricId": metric_id,
        "metricLabel": cfg["label"],
        "unit": cfg.get("unit", ""),
        "dimension": "intersection",
        "series": [
            {
                "seriesId": metric_id,
                "label": cfg["label"],
                "values": values,
            }
        ],
    }


def _fetch_approach_metric_series(
    conn,
    *,
    cfg: dict[str, Any],
    inter_id: str,
    day_of_week: int,
    metric_id: str,
) -> dict[str, Any]:
    schema = _timing_schema()
    table = cfg["table"]
    value_field = cfg["value_field"]
    qualified = f"{_qident(schema)}.{_qident(table)}"

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT m.inter_id::text AS inter_id,
                   COALESCE(m.inter_name, d.inter_name) AS inter_name,
                   m.link_id::text AS link_id,
                   m.link_name,
                   m.dir8_code,
                   m.dir8_label,
                   m.step_index,
                   m.{_qident(value_field)} AS metric_value
            FROM {qualified} m
            LEFT JOIN {_dim_inter_qualified()} d ON d.inter_id::text = m.inter_id::text
            WHERE m.is_deleted = 0
              AND m.inter_id::text = %s
              AND m.day_of_week = %s
              AND m.{_qident(value_field)} IS NOT NULL
            ORDER BY m.link_id, m.step_index
            """,
            (inter_id.strip(), day_of_week),
        )
        rows = cur.fetchall()

    by_link: dict[str, dict[str, Any]] = {}
    inter_name = ""
    for row in rows:
        inter_name = str(row.get("inter_name") or "").strip()
        link_id = str(row.get("link_id") or "").strip()
        if not link_id:
            continue
        step = _to_int(row.get("step_index"))
        num = _to_float(row.get("metric_value"))
        if step is None or num is None:
            continue
        if link_id not in by_link:
            dir8 = normalize_dir8_no(row.get("dir8_code"))
            by_link[link_id] = {
                "linkId": link_id,
                "linkName": str(row.get("link_name") or "").strip(),
                "dir8Code": dir8,
                "dir8Label": str(row.get("dir8_label") or "").strip() or dir8_label(dir8),
                "values": [],
            }
        by_link[link_id]["values"].append(
            {
                "stepIndex": step,
                "timeLabel": step_index_to_hhmm(step),
                "value": round(num, 4),
            }
        )

    series = sorted(by_link.values(), key=lambda x: (x.get("dir8Code") is None, x.get("dir8Code") or 99))
    return {
        "interId": inter_id.strip(),
        "interName": inter_name,
        "dayOfWeek": day_of_week,
        "dayLabel": _day_label(day_of_week),
        "metricId": metric_id,
        "metricLabel": cfg["label"],
        "unit": cfg.get("unit", ""),
        "dimension": "approach",
        "series": series,
    }


def _day_label(day_of_week: int) -> str:
    labels = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}
    return labels.get(day_of_week, f"星期{day_of_week}")


def _offset_by_dir8(lon: float, lat: float, dir8: int | None, meters: float = 55.0) -> tuple[float, float]:
    """将转向点位从路口中心沿 dir8 方向偏移（近似平面换算）。"""
    if dir8 is None:
        return lon, lat
    import math

    # dir8: 0=北，顺时针；方位角从北顺时针
    angle_deg = (dir8 % 8) * 45.0
    angle_rad = math.radians(angle_deg)
    dlat = (meters * math.cos(angle_rad)) / 111_320.0
    dlon = (meters * math.sin(angle_rad)) / (111_320.0 * max(math.cos(math.radians(lat)), 0.2))
    return lon + dlon, lat + dlat


def _value_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"min": None, "max": None, "avg": None, "p50": None, "p90": None, "count": 0}
    ordered = sorted(values)
    n = len(ordered)

    def pct(p: float) -> float:
        if n == 1:
            return ordered[0]
        idx = (n - 1) * p
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        w = idx - lo
        return ordered[lo] * (1 - w) + ordered[hi] * w

    return {
        "min": round(ordered[0], 4),
        "max": round(ordered[-1], 4),
        "avg": round(sum(values) / n, 4),
        "p50": round(pct(0.5), 4),
        "p90": round(pct(0.9), 4),
        "count": n,
    }


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
