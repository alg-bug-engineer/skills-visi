"""GIS 指标地图 API：从 PostgreSQL 读取评价指标并按图层返回。"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from data.corridor_coord_reader import (
    fetch_corridor_catalog,
    fetch_corridor_coord_layer,
    fetch_corridor_time_slices,
)
from data.complaint_reader import (
    complaint_types_for_api,
    fetch_complaint_layer,
    fetch_complaint_types,
)
from data.field_survey_reader import (
    fetch_field_survey_layer,
    fetch_field_survey_types,
    field_survey_issue_types_for_api,
)
from data.manual_survey_reader import (
    fetch_manual_survey_layer,
    fetch_manual_survey_types,
    manual_survey_problem_types_for_api,
    manual_survey_time_periods_for_api,
)
from data.line_val_reader import (
    LINE_METRIC_CATALOG,
    LINE_SERIES_METRIC_IDS,
    fetch_line_catalog,
    fetch_line_time_slices,
    fetch_line_val_layer,
    fetch_line_val_series,
    line_metric_catalog_for_api,
)
from data.metric_reader import (
    APPROACH_METRIC_IDS,
    INTERSECTION_SERIES_METRIC_IDS,
    METRIC_CATALOG,
    METRIC_SERIES_IDS,
    fetch_available_time_slices,
    fetch_inter_link_status_series,
    fetch_intersection_geometries,
    fetch_metric_layer,
    fetch_metric_series,
    intersection_dimensions_for_api,
    metric_catalog_for_api,
)
from data.pg_reader import connect_pg

router = APIRouter(prefix="/v1/map", tags=["map"])


@router.get("/config")
def map_config() -> dict[str, Any]:
    """地图与指标配置（前端初始化用）。"""
    amap_key = os.getenv("AMAP_JS_KEY", "").strip()
    coord_srs = os.getenv("PG_INTER_LONLAT_SRS") or os.getenv("MYSQL_INTERSECTION_LONLAT_SRS", "wgs84")
    return {
        "mapProvider": "amap" if amap_key else "leaflet",
        "amapKey": amap_key or None,
        "amapSecurityCode": os.getenv("AMAP_JS_SECURITY", "").strip() or None,
        "coordSrs": coord_srs.lower(),
        "timingSchema": os.getenv("PG_TIMING_SCHEMA") or os.getenv("PG_FLOW_SCHEMA", "xianchang"),
        "metrics": metric_catalog_for_api() + line_metric_catalog_for_api(),
        "intersectionDimensions": intersection_dimensions_for_api(),
        "levels": [
            {"id": "intersection", "label": "路口级"},
            {"id": "line", "label": "line 道路"},
            {"id": "complaint", "label": "投诉民意"},
            {"id": "manual_survey", "label": "人工调查"},
            {"id": "field_survey", "label": "交通组织调研"},
            {"id": "corridor_coord", "label": "干线协调"},
        ],
        "complaintStatPeriods": ["2025"],
        "complaintTypes": ["全部", *complaint_types_for_api()],
        "manualSurveyBatches": ["jinan_2025"],
        "manualSurveyTimePeriods": ["全部", *manual_survey_time_periods_for_api()],
        "manualSurveyProblemTypes": ["全部", *manual_survey_problem_types_for_api()],
        "fieldSurveyBatches": ["jinan_20260609"],
        "fieldSurveyIssueTypes": ["全部", *field_survey_issue_types_for_api()],
    }


@router.get("/metrics")
def map_metrics(
    level: str | None = Query(None, description="intersection | complaint | ..."),
    dimension: str | None = Query(None, description="路口级下维度：intersection | approach | turn | lane"),
) -> dict[str, Any]:
    """指标列表，可按粒度或维度筛选。"""
    items = metric_catalog_for_api()
    if level:
        items = [item for item in items if item["level"] == level]
    if dimension:
        items = [item for item in items if item.get("dimension") == dimension]
    return {"count": len(items), "metrics": items}


@router.get("/time-slices")
def map_time_slices(
    metric_id: str = Query(..., description="指标 ID，如 saturation_max"),
) -> dict[str, Any]:
    """某指标表内可用的时间片（星期 + step_index 范围）。"""
    if metric_id not in METRIC_CATALOG:
        raise HTTPException(status_code=400, detail=f"未知指标: {metric_id}")
    try:
        conn = connect_pg()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PostgreSQL 连接失败: {exc}") from exc
    try:
        return fetch_available_time_slices(conn, metric_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取时间片失败: {exc}") from exc
    finally:
        conn.close()


@router.get("/intersections")
def map_intersections() -> dict[str, Any]:
    """带坐标的路口列表（用于地图定位与筛选）。"""
    try:
        conn = connect_pg()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PostgreSQL 连接失败: {exc}") from exc
    try:
        geos = fetch_intersection_geometries(conn)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取路口坐标失败: {exc}") from exc
    finally:
        conn.close()
    items = sorted(geos.values(), key=lambda x: x.get("interName") or x.get("interId") or "")
    return {"count": len(items), "intersections": items}


@router.get("/layer")
def map_layer(
    metric_id: str = Query(..., description="指标 ID"),
    day_of_week: int = Query(..., ge=1, le=7, description="星期 1-7"),
    step_index: int = Query(..., ge=0, le=287, description="5 分钟时间片 0-287"),
    inter_id: str | None = Query(None, description="可选，仅返回指定路口"),
) -> dict[str, Any]:
    """返回指定指标图层（GeoJSON FeatureCollection）。"""
    if metric_id not in METRIC_CATALOG:
        raise HTTPException(status_code=400, detail=f"未知指标: {metric_id}")
    inter_ids = [inter_id.strip()] if inter_id and inter_id.strip() else None
    try:
        conn = connect_pg()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PostgreSQL 连接失败: {exc}") from exc
    try:
        return fetch_metric_layer(
            conn,
            metric_id=metric_id,
            day_of_week=day_of_week,
            step_index=step_index,
            inter_ids=inter_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取指标图层失败: {exc}") from exc
    finally:
        conn.close()


@router.get("/inter-link-status/series")
def map_inter_link_status_series(
    inter_id: str = Query(..., description="路口 ID"),
    day_of_week: int = Query(..., ge=1, le=7, description="星期 1-7"),
    metric_id: str = Query("link_stop_time_sec", description="进口方向指标 ID"),
) -> dict[str, Any]:
    """某路口各进口 link 在一天内的指标时序（曲线图）。"""
    if metric_id not in APPROACH_METRIC_IDS:
        raise HTTPException(status_code=400, detail=f"未知进口方向指标: {metric_id}")
    return _map_metric_series_response(inter_id, day_of_week, metric_id)


@router.get("/metric-series")
def map_metric_series(
    inter_id: str = Query(..., description="路口 ID"),
    day_of_week: int = Query(..., ge=1, le=7, description="星期 1-7"),
    metric_id: str = Query(..., description="指标 ID"),
) -> dict[str, Any]:
    """某路口单日指标时序（路口整体单曲线 / 进口方向多序列）。"""
    if metric_id not in METRIC_SERIES_IDS:
        raise HTTPException(status_code=400, detail=f"指标不支持时序曲线: {metric_id}")
    return _map_metric_series_response(inter_id, day_of_week, metric_id)


def _map_metric_series_response(inter_id: str, day_of_week: int, metric_id: str) -> dict[str, Any]:
    try:
        conn = connect_pg()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PostgreSQL 连接失败: {exc}") from exc
    try:
        return fetch_metric_series(
            conn,
            inter_id=inter_id,
            day_of_week=day_of_week,
            metric_id=metric_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取指标时序失败: {exc}") from exc
    finally:
        conn.close()


@router.get("/complaint/types")
def map_complaint_types(
    stat_period: str = Query("2025", description="统计时段"),
) -> dict[str, Any]:
    """投诉类型及件数分布。"""
    try:
        conn = connect_pg()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PostgreSQL 连接失败: {exc}") from exc
    try:
        types = fetch_complaint_types(conn, stat_period=stat_period)
        return {"statPeriod": stat_period, "types": types}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取投诉类型失败: {exc}") from exc
    finally:
        conn.close()


@router.get("/complaint/layer")
def map_complaint_layer(
    stat_period: str = Query("2025", description="统计时段"),
    complaint_type: str = Query("全部", description="投诉类型，全部表示不限"),
    inter_id: str | None = Query(None, description="可选，仅返回指定路口"),
) -> dict[str, Any]:
    """投诉民意图层（GeoJSON FeatureCollection）。"""
    inter_ids = [inter_id.strip()] if inter_id and inter_id.strip() else None
    try:
        conn = connect_pg()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PostgreSQL 连接失败: {exc}") from exc
    try:
        return fetch_complaint_layer(
            conn,
            stat_period=stat_period,
            complaint_type=complaint_type,
            inter_ids=inter_ids,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取投诉图层失败: {exc}") from exc
    finally:
        conn.close()


@router.get("/manual-survey/types")
def map_manual_survey_types(
    survey_batch: str = Query("jinan_2025", description="调查批次"),
) -> dict[str, Any]:
    """人工调查问题类型及记录数分布。"""
    try:
        conn = connect_pg()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PostgreSQL 连接失败: {exc}") from exc
    try:
        types = fetch_manual_survey_types(conn, survey_batch=survey_batch)
        return {"surveyBatch": survey_batch, "types": types}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取调查问题类型失败: {exc}") from exc
    finally:
        conn.close()


@router.get("/manual-survey/layer")
def map_manual_survey_layer(
    survey_batch: str = Query("jinan_2025", description="调查批次"),
    time_period: str = Query("全部", description="时段，全部表示不限"),
    problem_type: str = Query("全部", description="问题类型，全部表示不限"),
    inter_id: str | None = Query(None, description="可选，仅返回指定路口"),
) -> dict[str, Any]:
    """人工调查问题图层（GeoJSON FeatureCollection）。"""
    inter_ids = [inter_id.strip()] if inter_id and inter_id.strip() else None
    try:
        conn = connect_pg()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PostgreSQL 连接失败: {exc}") from exc
    try:
        return fetch_manual_survey_layer(
            conn,
            survey_batch=survey_batch,
            time_period=time_period,
            problem_type=problem_type,
            inter_ids=inter_ids,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取人工调查图层失败: {exc}") from exc
    finally:
        conn.close()


@router.get("/field-survey/types")
def map_field_survey_types(
    report_batch: str = Query("jinan_20260609", description="调研批次"),
) -> dict[str, Any]:
    """交通组织调研问题类型及条数分布。"""
    try:
        conn = connect_pg()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PostgreSQL 连接失败: {exc}") from exc
    try:
        types = fetch_field_survey_types(conn, report_batch=report_batch)
        return {"reportBatch": report_batch, "types": types}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取调研问题类型失败: {exc}") from exc
    finally:
        conn.close()


@router.get("/field-survey/layer")
def map_field_survey_layer(
    report_batch: str = Query("jinan_20260609", description="调研批次"),
    issue_type: str = Query("全部", description="问题类型，全部表示不限"),
    inter_id: str | None = Query(None, description="可选，仅返回指定路口"),
) -> dict[str, Any]:
    """交通组织调研问题图层（GeoJSON FeatureCollection）。"""
    inter_ids = [inter_id.strip()] if inter_id and inter_id.strip() else None
    try:
        conn = connect_pg()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PostgreSQL 连接失败: {exc}") from exc
    try:
        return fetch_field_survey_layer(
            conn,
            report_batch=report_batch,
            issue_type=issue_type,
            inter_ids=inter_ids,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取交通组织调研图层失败: {exc}") from exc
    finally:
        conn.close()


@router.get("/corridor-coord/corridors")
def map_corridor_coord_catalog() -> dict[str, Any]:
    """干线协调走廊目录（侧边栏筛选）。"""
    try:
        conn = connect_pg()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PostgreSQL 连接失败: {exc}") from exc
    try:
        corridors = fetch_corridor_catalog(conn)
        return {"count": len(corridors), "corridors": corridors}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取走廊目录失败: {exc}") from exc
    finally:
        conn.close()


@router.get("/corridor-coord/time-slices")
def map_corridor_coord_time_slices() -> dict[str, Any]:
    """干线协调可用日型统计。"""
    try:
        conn = connect_pg()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PostgreSQL 连接失败: {exc}") from exc
    try:
        return fetch_corridor_time_slices(conn)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取干线协调时间片失败: {exc}") from exc
    finally:
        conn.close()


@router.get("/line-val/lines")
def map_line_val_catalog() -> dict[str, Any]:
    """line 道路目录（侧边栏筛选）。"""
    try:
        conn = connect_pg()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PostgreSQL 连接失败: {exc}") from exc
    try:
        lines = fetch_line_catalog(conn)
        return {"count": len(lines), "lines": lines}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取 line 目录失败: {exc}") from exc
    finally:
        conn.close()


@router.get("/line-val/time-slices")
def map_line_val_time_slices(
    metric_id: str = Query(..., description="line 指标 ID，如 line_delay_index"),
) -> dict[str, Any]:
    """line 指标可用时间片。"""
    if metric_id not in LINE_METRIC_CATALOG:
        raise HTTPException(status_code=400, detail=f"未知 line 指标: {metric_id}")
    try:
        conn = connect_pg()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PostgreSQL 连接失败: {exc}") from exc
    try:
        return fetch_line_time_slices(conn, metric_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取 line 时间片失败: {exc}") from exc
    finally:
        conn.close()


@router.get("/line-val/layer")
def map_line_val_layer(
    metric_id: str = Query(..., description="line 指标 ID"),
    day_of_week: int = Query(..., ge=1, le=7, description="星期 1-7"),
    step_index: int = Query(..., ge=0, le=287, description="5 分钟时间片 0-287"),
    travel_dir: int | None = Query(None, ge=1, le=2, description="行驶方向：1 正向，2 反向，空=全部"),
    line_id: str = Query("全部", description="line_id，全部表示不限"),
) -> dict[str, Any]:
    """line 道路指标图层：道路折线 + 信控路口点。"""
    if metric_id not in LINE_METRIC_CATALOG:
        raise HTTPException(status_code=400, detail=f"未知 line 指标: {metric_id}")
    try:
        conn = connect_pg()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PostgreSQL 连接失败: {exc}") from exc
    try:
        return fetch_line_val_layer(
            conn,
            metric_id=metric_id,
            day_of_week=day_of_week,
            step_index=step_index,
            travel_dir=travel_dir,
            line_id=line_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取 line 图层失败: {exc}") from exc
    finally:
        conn.close()


@router.get("/line-val/series")
def map_line_val_series(
    line_id: str = Query(..., description="line_id"),
    day_of_week: int = Query(..., ge=1, le=7, description="星期 1-7"),
    metric_id: str = Query(..., description="line 指标 ID"),
    travel_dir: int | None = Query(None, ge=1, le=2, description="行驶方向，空=正向+反向"),
) -> dict[str, Any]:
    """某 line 单日指标时序（正向/反向曲线）。"""
    if metric_id not in LINE_SERIES_METRIC_IDS:
        raise HTTPException(status_code=400, detail=f"line 指标不支持时序曲线: {metric_id}")
    try:
        conn = connect_pg()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PostgreSQL 连接失败: {exc}") from exc
    try:
        return fetch_line_val_series(
            conn,
            line_id=line_id,
            day_of_week=day_of_week,
            metric_id=metric_id,
            travel_dir=travel_dir,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取 line 指标时序失败: {exc}") from exc
    finally:
        conn.close()


@router.get("/corridor-coord/layer")
def map_corridor_coord_layer(
    day_of_week: int = Query(..., ge=1, le=7, description="星期 1-7"),
    step_index: int = Query(..., ge=0, le=287, description="5 分钟时间片 0-287"),
    corridor_id: str = Query("全部", description="走廊 ID，全部表示不限"),
) -> dict[str, Any]:
    """干线协调图层：走廊路段线 + 路口点（GeoJSON FeatureCollection）。"""
    try:
        conn = connect_pg()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PostgreSQL 连接失败: {exc}") from exc
    try:
        return fetch_corridor_coord_layer(
            conn,
            day_of_week=day_of_week,
            step_index=step_index,
            corridor_id=corridor_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取干线协调图层失败: {exc}") from exc
    finally:
        conn.close()
