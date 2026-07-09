"""Lightweight FastAPI app for interactive optimization UIs."""

from __future__ import annotations

import json

from env import load_project_env

load_project_env()
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from data.flow_series_resolver import fetch_turn_flow_series_resolved, resolve_flow_weekdays
from data.lane_flow_reader import (
    fetch_turn_flow_stats_from_lane_mm,
    lane_flow_table_exists,
)
from data.mysql_reader import (
    connect_mysql,
    fetch_atom_lane_mapping,
    fetch_day_plan_weekdays,
    fetch_intersection_list,
    fetch_lane_phase_mapping,
    fetch_phase_plan_request,
    fill_stage_green_bounds,
    fill_turn_flows,
)
from data.pg_reader import (
    connect_pg,
    fetch_channelization,
    fetch_turn_flow_series,
    fetch_turn_flow_stats,
)
from optimization import optimize_corridor, optimize_intersection
from preprocessing.timing.ring_to_stage.standard_timing_tables import TABLE_PLAN_STAGE_PHASE_RLTN
from preprocessing.timing.stage_to_ring_table import (
    DEFAULT_CYCLE_COLUMN,
    DEFAULT_OVERLAP_COLUMN,
    DEFAULT_PHASE_COLUMN,
    build_ring_fields_from_stage_phase_rltn,
)
from preprocessing.timing.period_segmentation import (
    SegmentationConfig,
    build_flow_chart_payload,
    segment_timing_periods,
)
from preprocessing.timing.period_segmentation_llm import segment_timing_periods_via_llm
from visualization.period_segmentation_report import (
    build_flow_chart_svg,
    build_flow_series_legend_html,
    build_segmentation_chart_svg,
)
from visualization.map_api import router as map_api_router
from visualization.timing_viewers import (
    _get_ring_visualizer_module,
    get_db,
    router as timing_viewers_router,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
FIELD_SURVEY_STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "field_survey"

app = FastAPI(
    title="信号智能优化工程 API",
    description="单路口配时优化与干线协调绿波可视化服务",
    version="0.1.0",
)
app.include_router(timing_viewers_router)
app.include_router(map_api_router)


def _resolve_flow_weekdays(inter_id: str, day_plan_no: int | None) -> list[int] | None:
    return resolve_flow_weekdays(inter_id, day_plan_no)


def _prefer_lane_flow_profile(date: str | None, weekdays: list[int] | None) -> bool:
    return date is None and bool(weekdays)


def _fetch_turn_flow_stats_resolved(
    inter_id: str,
    *,
    date: str | None,
    weekdays: list[int] | None,
    windows: list[tuple[str, str]],
) -> dict[str, Any]:
    if _prefer_lane_flow_profile(date, weekdays):
        mysql_db = connect_mysql()
        try:
            if lane_flow_table_exists(mysql_db):
                pg_conn = connect_pg()
                try:
                    stats = fetch_turn_flow_stats_from_lane_mm(
                        mysql_db,
                        pg_conn,
                        inter_id,
                        weekdays=weekdays,
                        windows=windows,
                    )
                finally:
                    pg_conn.close()
                if stats.get("flows"):
                    return stats
        finally:
            mysql_db.close()

    pg_conn = connect_pg()
    try:
        return fetch_turn_flow_stats(
            pg_conn,
            inter_id,
            date=date,
            weekdays=weekdays,
            windows=windows,
        )
    finally:
        pg_conn.close()


def _fetch_turn_flow_series_resolved(
    inter_id: str,
    *,
    date: str | None,
    weekdays: list[int] | None,
    interval_min: int,
) -> dict[str, Any]:
    return fetch_turn_flow_series_resolved(
        inter_id,
        date=date,
        weekdays=weekdays,
        interval_min=interval_min,
    )


class SinglePointPlanRequest(BaseModel):
    """Single-intersection optimization request."""

    model_config = ConfigDict(extra="allow")

    interId: str = Field(..., description="目标路口 ID")
    phasePlanOfTimeList: list[dict[str, Any]] = Field(default_factory=list)
    parameter_json_str: str | dict[str, Any] | None = None
    obj_intensity: float | None = None
    profile: dict[str, Any] = Field(default_factory=dict)
    strategy_instruction: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)


class CorridorPlanRequest(BaseModel):
    """Corridor coordination request."""

    model_config = ConfigDict(extra="allow")

    corridor_id: str = Field(default="", description="走廊标识")
    intersection_ids: list[str] = Field(default_factory=list)
    links: list[dict[str, Any]] | None = None
    intersections: list[dict[str, Any]] | None = None
    profile: dict[str, Any] = Field(default_factory=dict)
    strategy_instruction: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
def health() -> dict[str, str]:
    """Health check used by static pages."""
    return {"status": "ok", "service": "signal-optimization-engine"}


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/debug/")


@app.get("/v1/planning/single-point/ui", include_in_schema=False)
def timing_optimizer_ui() -> RedirectResponse:
    return RedirectResponse(url="/debug/timing-optimizer.html")


@app.get("/v1/planning/corridor/ui", include_in_schema=False)
def corridor_coordination_ui() -> RedirectResponse:
    return RedirectResponse(url="/debug/corridor-coordination.html")


@app.get("/v1/timing/offline/ui", include_in_schema=False)
def offline_timing_ui() -> RedirectResponse:
    return RedirectResponse(url="/debug/offline-timing-viewer.html")


@app.get("/v1/timing/history/ui", include_in_schema=False)
def history_timing_ui() -> RedirectResponse:
    return RedirectResponse(url="/debug/history-timing-viewer.html")


@app.get("/v1/timing/ring/ui", include_in_schema=False)
def ring_barrier_ui() -> RedirectResponse:
    return RedirectResponse(url="/debug/ring-barrier-viewer.html")


@app.get("/v1/timing/period-segmentation/ui", include_in_schema=False)
def period_segmentation_ui() -> RedirectResponse:
    return RedirectResponse(url="/debug/period-segmentation-viewer.html")


def _resolve_period_segmentation_weekdays(
    inter_id: str,
    *,
    weekday: int | None,
    day_plan_no: int | None,
) -> list[int] | None:
    if weekday is not None:
        if not 1 <= weekday <= 7:
            raise HTTPException(status_code=400, detail="weekday 须在 1..7 之间（1=周一）")
        return [weekday]
    if day_plan_no is not None:
        return _resolve_flow_weekdays(inter_id, day_plan_no)
    return None


@app.get("/v1/timing/period-segmentation/flow")
def period_segmentation_flow(
    inter_id: str,
    weekday: int | None = None,
    day_plan_no: int | None = None,
    flow_date: str | None = None,
) -> dict[str, Any]:
    """Load 5-minute lane-group flow series for the period-segmentation viewer."""
    try:
        weekdays = _resolve_period_segmentation_weekdays(
            inter_id,
            weekday=weekday,
            day_plan_no=day_plan_no,
        )
        flow_series = _fetch_turn_flow_series_resolved(
            inter_id,
            date=flow_date,
            weekdays=weekdays,
            interval_min=5,
        )
        if weekday is not None:
            flow_series.setdefault("flowDateMeta", {})["selectedWeekday"] = weekday
        if day_plan_no is not None:
            flow_series.setdefault("flowDateMeta", {})["dayPlanNo"] = day_plan_no
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取流量数据失败: {exc}") from exc
    if not (flow_series.get("series") or flow_series.get("laneGroupSeries")):
        raise HTTPException(
            status_code=404,
            detail=f"流量库内无路口 {inter_id} 在指定日期类型的 5 分钟流量",
        )
    flow_chart = build_flow_chart_payload(flow_series)
    return {
        "interId": flow_series.get("interId") or inter_id,
        "interName": flow_series.get("interName") or "",
        "flowDateMeta": flow_series.get("flowDateMeta") or {},
        "intervalMinutes": flow_series.get("intervalMinutes") or 5,
        "seriesKind": "laneGroupSeries" if flow_series.get("laneGroupSeries") else "series",
        "flowChart": flow_chart,
        "chartSvg": build_flow_chart_svg(flow_chart),
        "seriesLegendHtml": build_flow_series_legend_html(flow_chart),
    }


@app.get("/v1/timing/period-segmentation")
def period_segmentation_run(
    inter_id: str,
    weekday: int | None = None,
    day_plan_no: int | None = None,
    flow_date: str | None = None,
    min_period_minutes: int = 15,
    min_periods: int = 3,
    max_periods: int = 15,
    engine: str = "deterministic",
) -> dict[str, Any]:
    """Run timing-period segmentation for one intersection.

    ``engine``: ``deterministic`` (default) or ``llm``.
    """
    engine_key = str(engine or "deterministic").strip().lower()
    if engine_key not in {"deterministic", "llm"}:
        raise HTTPException(status_code=400, detail="engine 须为 deterministic 或 llm")
    try:
        weekdays = _resolve_period_segmentation_weekdays(
            inter_id,
            weekday=weekday,
            day_plan_no=day_plan_no,
        )
        flow_series = _fetch_turn_flow_series_resolved(
            inter_id,
            date=flow_date,
            weekdays=weekdays,
            interval_min=5,
        )
        if weekday is not None:
            flow_series.setdefault("flowDateMeta", {})["selectedWeekday"] = weekday
        if day_plan_no is not None:
            flow_series.setdefault("flowDateMeta", {})["dayPlanNo"] = day_plan_no
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取流量数据失败: {exc}") from exc
    if not (flow_series.get("series") or flow_series.get("laneGroupSeries")):
        raise HTTPException(
            status_code=404,
            detail=f"流量库内无路口 {inter_id} 在指定日期类型的 5 分钟流量",
        )
    config = SegmentationConfig(
        min_period_minutes=min_period_minutes,
        min_periods=min_periods,
        max_periods=max_periods,
    )
    try:
        if engine_key == "llm":
            result = segment_timing_periods_via_llm(flow_series, config=config)
        else:
            result = segment_timing_periods(flow_series, config=config)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"时段划分失败: {exc}") from exc
    return {
        "ok": True,
        "engine": engine_key,
        "result": result,
        "chartSvg": build_segmentation_chart_svg(result),
        "seriesLegendHtml": build_flow_series_legend_html(result.get("flowChart") or {}),
    }


@app.get("/v1/map/ui", include_in_schema=False)
def metric_map_ui() -> RedirectResponse:
    return RedirectResponse(url="/debug/metric-map-viewer.html")


@app.get("/v1/db/intersections")
def db_intersections() -> dict[str, Any]:
    """List intersections with phase plans stored in MySQL."""
    try:
        db = connect_mysql()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 连接失败
        raise HTTPException(status_code=500, detail=f"MySQL 连接失败: {exc}") from exc
    try:
        intersections = fetch_intersection_list(db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取路口列表失败: {exc}") from exc
    finally:
        db.close()
    return {"count": len(intersections), "intersections": intersections}


@app.get("/v1/db/intersections/{inter_id}/phase-plans")
def db_phase_plans(
    inter_id: str,
    with_flows: bool = False,
    flow_date: str | None = None,
    with_green_bounds: bool = True,
) -> dict[str, Any]:
    """Return all phase/stage plans of one intersection in optimizer-compatible shape.

    with_flows=true 时按各方案的日计划执行时段，从 PG 车道流量表统计小时流量
    并填充 turnFlowTotal（veh/h）；flow_date 为 YYYYMMDD，缺省取库内最新一天。
    with_green_bounds=true（默认）时按交通流推导各阶段/各时段最小绿与最大绿，
    覆盖 min_green_s / max_green_s 并附 greenBounds 明细。
    """
    try:
        db = connect_mysql()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 连接失败
        raise HTTPException(status_code=500, detail=f"MySQL 连接失败: {exc}") from exc
    try:
        request = fetch_phase_plan_request(db, inter_id)
        if request["phasePlanOfTimeList"] and with_green_bounds:
            try:
                fill_stage_green_bounds(request, db)
            except Exception as exc:
                raise HTTPException(
                    status_code=500, detail=f"阶段最小绿计算失败: {exc}"
                ) from exc
        if request["phasePlanOfTimeList"] and with_flows:
            try:
                fill_turn_flows(request, None, db, flow_date=flow_date)
            except Exception as exc:
                try:
                    pg_conn = connect_pg()
                except Exception as pg_exc:
                    raise HTTPException(
                        status_code=500,
                        detail=f"预计算流量不可用且 PostgreSQL 连接失败: {pg_exc}",
                    ) from exc
                try:
                    fill_turn_flows(
                        request,
                        pg_conn,
                        db,
                        flow_date=flow_date,
                        prefer_precomputed=False,
                    )
                except Exception as flow_exc:
                    raise HTTPException(status_code=500, detail=f"流量统计填充失败: {flow_exc}") from flow_exc
                finally:
                    pg_conn.close()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取相位方案失败: {exc}") from exc
    finally:
        db.close()
    if not request["phasePlanOfTimeList"]:
        raise HTTPException(status_code=404, detail=f"库内无路口 {inter_id} 的相位方案")
    return request


@app.get("/v1/db/intersections/{inter_id}/turn-flows")
def db_turn_flows(
    inter_id: str,
    date: str | None = None,
    day_plan_no: int | None = None,
    start: str = "00:00",
    end: str = "24:00",
) -> dict[str, Any]:
    """Return aggregated hourly turn flows (veh/h) of one intersection.

    优先从 MySQL dws_lane_flow_5min_mm 按日计划星期几读取历史均值；
    缺表或无数据时回退 PG 原始车道 5 分钟流量表。
    date 为 YYYYMMDD，显式指定 date 时始终读 PG 单日实测。
    """
    try:
        weekdays = _resolve_flow_weekdays(inter_id, day_plan_no)
        stats = _fetch_turn_flow_stats_resolved(
            inter_id,
            date=date,
            weekdays=weekdays,
            windows=[(start, end)],
        )
        if day_plan_no is not None:
            stats.setdefault("flowDateMeta", {})["dayPlanNo"] = day_plan_no
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取流量数据失败: {exc}") from exc
    if not stats["flows"]:
        raise HTTPException(
            status_code=404,
            detail=f"流量库内无路口 {inter_id} 在指定日期/时段的数据",
        )
    return stats


@app.get("/v1/db/intersections/{inter_id}/turn-flow-series")
def db_turn_flow_series(
    inter_id: str,
    date: str | None = None,
    day_plan_no: int | None = None,
    interval: int = 15,
) -> dict[str, Any]:
    """Return whole-day turn flow time series (veh/h) of one intersection.

    优先从 MySQL dws_lane_flow_5min_mm 按日计划星期几读取历史均值曲线；
    缺表或无数据时回退 PG 原始车道 5 分钟流量表。
    """
    try:
        weekdays = _resolve_flow_weekdays(inter_id, day_plan_no)
        series = _fetch_turn_flow_series_resolved(
            inter_id,
            date=date,
            weekdays=weekdays,
            interval_min=interval,
        )
        if day_plan_no is not None:
            series.setdefault("flowDateMeta", {})["dayPlanNo"] = day_plan_no
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取流量数据失败: {exc}") from exc
    if not series["series"]:
        raise HTTPException(
            status_code=404,
            detail=f"流量库内无路口 {inter_id} 在指定日期的数据",
        )
    return series


@app.get("/v1/db/intersections/{inter_id}/channelization")
def db_channelization(inter_id: str) -> dict[str, Any]:
    """Return entrance-lane channelization from PG channelization wide table."""
    try:
        conn = connect_pg()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PostgreSQL 连接失败: {exc}") from exc
    try:
        result = fetch_channelization(conn, inter_id)
        if result["approaches"]:
            result["source"] = "PG渠化宽表"
            return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取 PG 渠化宽表失败: {exc}") from exc
    finally:
        conn.close()
    raise HTTPException(status_code=404, detail=f"PG 渠化库内无路口 {inter_id} 的进口车道数据")


@app.get("/v1/db/intersections/{inter_id}/atom-lane-mapping")
def db_atom_lane_mapping(inter_id: str, plan_no: int) -> dict[str, Any]:
    """Return signal-atom to lane-cluster mappings for one intersection plan."""
    try:
        db = connect_mysql()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"MySQL 连接失败: {exc}") from exc
    try:
        result = fetch_atom_lane_mapping(db, inter_id, plan_no)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取 atom-lane-mapping 失败: {exc}") from exc
    finally:
        db.close()
    if not result.get("mappings"):
        raise HTTPException(
            status_code=404,
            detail=f"映射库内无路口 {inter_id} 方案 {plan_no} 的车道-相位映射数据",
        )
    return result


@app.get("/v1/db/intersections/{inter_id}/lane-phase-mapping")
def db_lane_phase_mapping(inter_id: str, plan_no: int) -> dict[str, Any]:
    """Return unified lane-cluster to phase/stage mappings for one intersection plan."""
    try:
        db = connect_mysql()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"MySQL 连接失败: {exc}") from exc
    try:
        result = fetch_lane_phase_mapping(db, inter_id, plan_no)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取 lane-phase-mapping 失败: {exc}") from exc
    finally:
        db.close()
    if not result.get("mappings"):
        if not result.get("tableExists", True):
            raise HTTPException(
                status_code=404,
                detail="统一映射表 dwd_ctl_inter_plan_lane_phase_mapping 尚未生成，请先执行 lane-phase-mapping。",
            )
        raise HTTPException(
            status_code=404,
            detail=f"映射库内无路口 {inter_id} 方案 {plan_no} 的统一车道-相位-阶段映射数据",
        )
    return result


@app.post("/v1/planning/single-point")
def single_point_plan(req: SinglePointPlanRequest) -> dict[str, Any]:
    """Generate a single-intersection timing plan for the UI."""
    payload = req.model_dump(exclude_none=True)
    has_flow_items, has_positive_flow = _single_point_flow_state(payload)
    if has_flow_items and not has_positive_flow:
        raise HTTPException(
            status_code=400,
            detail="请至少为一个受控转向填入大于 0 的 turnFlowTotal 或 criticalLaneFlow。",
        )
    try:
        plan = optimize_intersection(payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if plan.get("isError"):
        return {
            "ok": False,
            "isError": True,
            "error": plan.get("error") or "single point optimization failed",
            "plan": plan,
            "data": plan.get("data"),
            "tool": "single_point_plan_tool",
        }

    _attach_optimized_ring_record(plan, payload)

    return {
        "ok": True,
        "isError": False,
        "error": None,
        "data": plan.get("data"),
        "tool": "single_point_plan_tool",
        "plan": plan,
    }


@app.post("/v1/planning/corridor")
def corridor_plan(req: CorridorPlanRequest) -> dict[str, Any]:
    """Generate a corridor coordination plan for the UI."""
    payload = req.model_dump(exclude_none=True)
    try:
        plan = optimize_corridor(payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    coordination = plan.get("coordination") or {}
    if coordination.get("error"):
        return {
            "ok": False,
            "tool": "corridor_coordination_plan_tool",
            "plan": plan,
            "error": coordination.get("error"),
        }

    return {
        "ok": True,
        "tool": "corridor_coordination_plan_tool",
        "plan": plan,
    }


if STATIC_DIR.is_dir():
    app.mount("/debug", StaticFiles(directory=str(STATIC_DIR), html=True), name="debug-console")

if FIELD_SURVEY_STATIC_DIR.is_dir():
    app.mount(
        "/static/field_survey",
        StaticFiles(directory=str(FIELD_SURVEY_STATIC_DIR)),
        name="field-survey-static",
    )


def _single_point_flow_state(payload: dict[str, Any]) -> tuple[bool, bool]:
    """Return whether controlled flow items exist and whether any has positive demand."""
    flow_items = list(_iter_single_point_flow_items(payload))
    return bool(flow_items), any(_flow_item_has_positive_demand(item) for item in flow_items)


def _attach_optimized_ring_record(plan: dict[str, Any], payload: dict[str, Any]) -> None:
    """Build optimized Ring-Barrier data from the canonical stage-phase relation table."""

    meta = plan.setdefault("meta", {})
    notes = meta.setdefault("notes", [])
    context = _single_point_ring_context(plan, payload)
    if not context.get("inter_id") or context.get("plan_no") is None:
        notes.append("未生成优化环结构：请求缺少 inter_id 或 plan_no，已保留前端阶段回放兜底。")
        return

    db = get_db()
    try:
        original_row, source_table = _fetch_original_ring_row(context)
        if not original_row:
            notes.append("未生成优化环结构：ODS 原始环结构表未匹配到当前路口方案。")
            return
        rltn_rows = _fetch_stage_phase_rltn_rows(db, context["inter_id"], int(context["plan_no"]))
        if not rltn_rows:
            notes.append("未生成优化环结构：dwd_ctl_inter_plan_stage_phase_rltn 无当前方案映射。")
            return
        optimized_stage_rows = _optimized_stage_rows(plan, payload)
        cycle_json, phase_json, overlap_json = build_ring_fields_from_stage_phase_rltn(
            original_row,
            optimized_stage_rows,
            rltn_rows,
        )
        record = _parse_ring_record_from_fields(
            original_row,
            source_table,
            cycle_json,
            phase_json,
            overlap_json,
            cycle_len=plan.get("cycleTime"),
        )
    except Exception as exc:
        notes.append(f"未生成优化环结构：{exc}")
        return
    finally:
        db.close()

    record["ring_replay_mode"] = "stage_phase_rltn_optimized"
    record["conversion_source"] = TABLE_PLAN_STAGE_PHASE_RLTN
    record["pattern"] = f"{context.get('plan_no') or record.get('pattern')}-OPT"
    record["offset_sec"] = context.get("offset_sec", record.get("offset_sec"))
    plan["optimizedRingRecord"] = record


def _single_point_ring_context(plan: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    first_plan = _first_phase_plan(payload)
    plan_no = _first_int(
        payload.get("planNo"),
        payload.get("plan_no"),
        first_plan.get("planNo"),
        first_plan.get("plan_no"),
        _plan_no_from_id(plan.get("phasePlanId")),
        _plan_no_from_id(first_plan.get("phasePlanId")),
    )
    return {
        "inter_id": payload.get("interId") or plan.get("intersectionId") or first_plan.get("interId"),
        "cross_id": payload.get("crossId") or payload.get("cross_id") or first_plan.get("crossId") or first_plan.get("cross_id"),
        "plan_no": plan_no,
        "cycle_len_sec": _first_int(plan.get("cycleTime"), first_plan.get("cycleTime"), first_plan.get("cycleLenSec")),
        "offset_sec": _first_int(payload.get("offsetSec"), payload.get("offset_sec"), first_plan.get("offsetSec"), first_plan.get("offset_sec"), default=0),
    }


def _first_phase_plan(payload: dict[str, Any]) -> dict[str, Any]:
    items = payload.get("phasePlanOfTimeList")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return items[0]
    parameter_payload = _decode_parameter_json(payload.get("parameter_json_str"))
    items = parameter_payload.get("phasePlanOfTimeList")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return items[0]
    return {}


def _fetch_original_ring_row(context: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    mod = _get_ring_visualizer_module()
    plan_no = int(context["plan_no"])
    tables = ("raw", "stage")
    candidates: list[tuple[dict[str, Any], str]] = []
    for table in tables:
        table_name = mod._resolve_table_name(table)
        if context.get("inter_id"):
            candidates.extend((row, table_name) for row in mod.fetch_scheme_rows(table=table_name, inter_id=context["inter_id"], plan_no=plan_no, limit=20))
        if context.get("cross_id"):
            candidates.extend((row, table_name) for row in mod.fetch_scheme_rows(table=table_name, cross_id=context["cross_id"], plan_no=plan_no, limit=20))
            candidates.extend((row, table_name) for row in mod.fetch_scheme_rows(table=table_name, cross_id=str(context["cross_id"]).lstrip("0") or context["cross_id"], plan_no=plan_no, limit=20))

    seen: set[tuple[str, Any, Any]] = set()
    unique: list[tuple[dict[str, Any], str]] = []
    for row, table_name in candidates:
        sig = (table_name, row.get("id"), row.get("pattern_no"))
        if sig in seen:
            continue
        seen.add(sig)
        unique.append((row, table_name))

    cycle = context.get("cycle_len_sec")
    if cycle:
        for row, table_name in unique:
            if _first_int(row.get("cycle_len_sec"), row.get("cycle_len")) == cycle:
                return row, table_name
    return unique[0] if unique else (None, "")


def _fetch_stage_phase_rltn_rows(db: Any, inter_id: str, plan_no: int) -> list[dict[str, Any]]:
    with db.cursor() as cur:
        cur.execute(
            f"""
            SELECT *
            FROM {TABLE_PLAN_STAGE_PHASE_RLTN}
            WHERE is_deleted = 0
              AND inter_id = %s
              AND plan_no = %s
            ORDER BY stage_seq_no, source_type, source_no
            """,
            (inter_id, plan_no),
        )
        return list(cur.fetchall())


def _optimized_stage_rows(plan: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_stages = list(_iter_single_point_stages(_first_phase_plan(payload).get("phaseStageInfoList")))
    raw_by_id = {
        str(item.get("phaseStageId") or "").strip(): item
        for item in raw_stages
        if str(item.get("phaseStageId") or "").strip()
    }
    rows = []
    for idx, stage in enumerate(plan.get("phaseStageTimingList") or [], start=1):
        stage_id = str(stage.get("phaseStageId") or "").strip()
        raw = raw_by_id.get(stage_id, {})
        stage_seq_no = _first_int(
            raw.get("stageSeqNo"),
            raw.get("stage_seq_no"),
            stage.get("stageSeqNo"),
            stage.get("stage_seq_no"),
            default=idx,
        )
        stage_no = _first_int(
            raw.get("stageNo"),
            raw.get("stage_no"),
            stage.get("stageNo"),
            stage.get("stage_no"),
            _numeric_suffix(stage_id),
            default=stage_seq_no,
        )
        green = _first_int(stage.get("greenTime"), stage.get("green_sec"), default=0)
        yellow = _first_int(stage.get("yellowTime"), stage.get("yellow_sec"), default=0)
        red = _first_int(stage.get("allRedTime"), stage.get("all_red_sec"), default=0)
        rows.append(
            {
                "stage_seq_no": stage_seq_no,
                "stage_no": stage_no,
                "green_sec": green,
                "yellow_sec": yellow,
                "all_red_sec": red,
                "stage_total_sec": green + yellow + red,
            }
        )
    return rows


def _parse_ring_record_from_fields(
    original_row: dict[str, Any],
    source_table: str,
    cycle_json: str,
    phase_json: str,
    overlap_json: str,
    *,
    cycle_len: Any,
) -> dict[str, Any]:
    mod = _get_ring_visualizer_module()
    row = dict(original_row)
    row[DEFAULT_CYCLE_COLUMN] = cycle_json
    row[DEFAULT_PHASE_COLUMN] = phase_json
    row[DEFAULT_OVERLAP_COLUMN] = overlap_json
    if cycle_len is not None:
        row["cycle_len_sec"] = cycle_len
    return mod.parse_scheme_row(row, source_table=source_table)


def _plan_no_from_id(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.upper().startswith("PLAN-"):
        return _first_int(text[5:])
    return _numeric_suffix(text)


def _numeric_suffix(value: Any) -> int | None:
    text = str(value or "").strip()
    digits = ""
    for ch in reversed(text):
        if not ch.isdigit():
            break
        digits = ch + digits
    return int(digits) if digits else None


def _first_int(*values: Any, default: int | None = None) -> int | None:
    for value in values:
        if value in (None, ""):
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return default


def _iter_single_point_flow_items(payload: dict[str, Any]):
    for stage in _iter_single_point_stages(payload.get("phasePlanOfTimeList")):
        yield from stage.get("phaseDirInfoDTOList") or []

    parameter_payload = _decode_parameter_json(payload.get("parameter_json_str"))
    for stage in _iter_single_point_stages(parameter_payload.get("phasePlanOfTimeList")):
        yield from stage.get("phaseDirInfoDTOList") or []


def _iter_single_point_stages(candidate: Any):
    if not isinstance(candidate, list):
        return
    for item in candidate:
        if not isinstance(item, dict):
            continue
        stages = item.get("phaseStageInfoList")
        if isinstance(stages, list):
            yield from (stage for stage in stages if isinstance(stage, dict))
        else:
            yield item


def _decode_parameter_json(candidate: Any) -> dict[str, Any]:
    if isinstance(candidate, dict):
        return candidate
    if not isinstance(candidate, str) or not candidate.strip():
        return {}
    try:
        decoded = json.loads(candidate)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _flow_item_has_positive_demand(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    for key in ("criticalLaneFlow", "criticalLaneFlowVph", "turnFlowTotal", "turnFlowTotalVph"):
        value = item.get(key)
        try:
            if value is not None and float(value) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False
