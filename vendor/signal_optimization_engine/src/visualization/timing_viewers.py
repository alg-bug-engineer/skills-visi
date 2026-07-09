"""MySQL-backed timing-plan viewer APIs used by the static debug pages."""

from __future__ import annotations

import json
import os
import re
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query

try:  # Optional dependency: install with `pip install -e ".[db]"`.
    import pymysql
    import pymysql.cursors
except ModuleNotFoundError:  # pragma: no cover - runtime dependency hint
    pymysql = None


router = APIRouter(prefix="/v1/timing", tags=["timing-viewers"])

DEFAULT_RAW_TABLE = "ods_ctl_inter_scheme_hisense_raw"
DEFAULT_STAGE_TABLE = "ods_ctl_inter_scheme_hisense_stage"


def _get_ring_visualizer_module():
    """延迟加载 tools/ring_timing_visualizer_v2，避免 FastAPI 启动时强依赖 matplotlib。"""
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    module_path = root / "tools" / "ring_timing_visualizer_v2.py"
    spec = importlib.util.spec_from_file_location("ring_timing_visualizer_v2", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载环图模块: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@router.get("/ring/intersections")
def ring_intersections(
    table: str = Query("raw", description="raw 或 stage"),
) -> list[dict[str, Any]]:
    """列出 ODS 海信配时表中有数据的路口。"""
    mod = _get_ring_visualizer_module()
    rows = mod.list_db_intersections(table=table)
    return [
        {
            "cross_id": row["cross_id"],
            "inter_id": row.get("inter_id"),
            "cross_name": row.get("cross_name"),
            "inter_name": row.get("inter_name"),
            "name": row.get("cross_name") or row.get("inter_name") or row["cross_id"],
            "scheme_count": row.get("scheme_count", 0),
        }
        for row in rows
    ]


@router.get("/ring/schemes")
def ring_schemes(
    cross_id: str = Query(..., min_length=1),
    table: str = Query("raw", description="raw 或 stage"),
) -> list[dict[str, Any]]:
    """列出指定路口下的全部 Ring-Barrier 配时方案。"""
    mod = _get_ring_visualizer_module()
    return mod.list_db_schemes(table=table, cross_id=cross_id)


@router.get("/ring/data")
def ring_data(
    cross_id: str = Query(..., min_length=1),
    plan_no: int = Query(..., ge=1),
    pattern_no: int = Query(..., ge=1),
    table: str = Query("raw", description="raw 或 stage"),
) -> dict[str, Any]:
    """返回指定方案的 Ring-Barrier 前端渲染数据。"""
    mod = _get_ring_visualizer_module()
    table_name = mod._resolve_table_name(table)
    rows = mod.fetch_scheme_rows(
        table=table_name,
        cross_id=cross_id,
        plan_no=plan_no,
        pattern_no=pattern_no,
        limit=1,
    )
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"未找到方案 cross_id={cross_id} plan_no={plan_no} pattern_no={pattern_no}",
        )
    try:
        record = mod.parse_scheme_row(rows[0], source_table=table_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"环图数据解析失败: {exc}") from exc
    return record


@router.get("/ring/image")
def ring_image(
    cross_id: str = Query(..., min_length=1),
    plan_no: int = Query(..., ge=1),
    pattern_no: int = Query(..., ge=1),
    table: str = Query("raw", description="raw 或 stage"),
):
    """返回指定方案的 Ring-Barrier 环图 PNG。"""
    from fastapi.responses import Response

    mod = _get_ring_visualizer_module()
    table_name = mod._resolve_table_name(table)
    rows = mod.fetch_scheme_rows(
        table=table_name,
        cross_id=cross_id,
        plan_no=plan_no,
        pattern_no=pattern_no,
        limit=1,
    )
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"未找到方案 cross_id={cross_id} plan_no={plan_no} pattern_no={pattern_no}",
        )
    try:
        record = mod.parse_scheme_row(rows[0], source_table=table_name)
        png = mod.render_ring_barrier_png(record)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"环图渲染失败: {exc}") from exc
    return Response(content=png, media_type="image/png")


TABLE_PERIOD_PLAN_EXEC_HIS = "dwd_ctl_inter_period_plan_exec_his"


def _db_config() -> dict[str, Any]:
    return {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "signalctl"),
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor if pymysql else None,
    }


def get_db():
    if pymysql is None:
        raise HTTPException(
            status_code=500,
            detail="缺少 pymysql 依赖，请执行: pip install -e '.[db]' 或 pip install pymysql",
        )
    return pymysql.connect(**_db_config())


def _extract_name(remark: str | None) -> str | None:
    if not remark:
        return None
    match = re.search(r"路口名称=([^;]+)", remark)
    return match.group(1).strip() if match else None


def _json_loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _time_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, timedelta):
        total_seconds = int(value.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours:02d}:{minutes:02d}"
    return str(value)[:5]


def _stage_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage_seq_no": row["stage_seq_no"],
        "stage_no": row["stage_no"],
        "stage_name": row.get("stage_name") or f"阶段{row['stage_no']}",
        "green_sec": row["green_sec"] or 0,
        "yellow_sec": row["yellow_sec"] or 0,
        "all_red_sec": row["all_red_sec"] or 0,
        "stage_total_sec": row["stage_total_sec"] or 0,
        "max_green_sec": row.get("max_green_sec"),
        "min_green_sec": row.get("min_green_sec"),
        "flow_combo": _json_loads(row.get("flow_combo_json"), []),
    }


def _derived_green_bounds(
    db,
    inter_id: str,
) -> tuple[dict[tuple[int, int], dict[str, Any]], dict[int, dict[str, Any]]]:
    """按交通流推导各方案各阶段最小绿/最大绿，并保留分时段明细。

    复用 data.mysql_reader.fill_stage_green_bounds（机动车最小绿 14s、行人按
    过街车道数推算、历史实际放行更短时取实际值），用于校正库内
    dwd_ctl_inter_plan_stage_timing.min_green_sec 可能存在的脏数据
    （如信号机相位级 3s 最小绿被错误套到机动车阶段）。
    """
    from data.mysql_reader import fetch_phase_plan_request, fill_stage_green_bounds

    request = fetch_phase_plan_request(db, inter_id)
    fill_stage_green_bounds(request, db)
    stage_bounds: dict[tuple[int, int], dict[str, Any]] = {}
    plan_bounds: dict[int, dict[str, Any]] = {}
    for plan in request.get("phasePlanOfTimeList") or []:
        plan_no = plan.get("planNo")
        if plan_no is not None:
            plan_bounds[int(plan_no)] = {
                "time_periods": plan.get("timePeriods") or [],
                "green_bounds": plan.get("greenBounds") or {},
            }
        for stage in plan.get("phaseStageInfoList") or []:
            stage_no = stage.get("stageNo")
            if plan_no is None or stage_no is None:
                continue
            stage_bounds[(plan_no, stage_no)] = {
                "min_green_sec": stage.get("min_green_s"),
                "max_green_sec": stage.get("max_green_s"),
                "green_bounds": stage.get("greenBounds"),
            }
    return stage_bounds, plan_bounds


@router.get("/offline/intersections")
def offline_intersections() -> list[dict[str, Any]]:
    """List intersections that have offline day-plan configuration."""
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT d.inter_id,
                       MIN(d.cross_id) AS cross_id,
                       MIN(d.remark) AS remark,
                       COUNT(DISTINCT d.day_plan_no) AS day_plan_count,
                       COUNT(DISTINCT s.schedule_no) AS schedule_count,
                       COUNT(DISTINCT p.plan_no) AS plan_count
                FROM dwd_ctl_inter_day_plan_cfg d
                LEFT JOIN dwd_ctl_inter_schedule_cfg s
                  ON s.inter_id = d.inter_id AND s.is_deleted = 0
                LEFT JOIN dwd_ctl_inter_plan_cfg p
                  ON p.inter_id = d.inter_id AND p.is_deleted = 0
                WHERE d.is_deleted = 0
                GROUP BY d.inter_id
                ORDER BY d.inter_id
                """
            )
            rows = cur.fetchall()
    finally:
        db.close()

    result = []
    for row in rows:
        result.append(
            {
                "inter_id": row["inter_id"],
                "cross_id": row.get("cross_id"),
                "name": _extract_name(row.get("remark")) or row.get("cross_id") or row["inter_id"],
                "day_plan_count": row["day_plan_count"],
                "schedule_count": row["schedule_count"],
                "plan_count": row["plan_count"],
            }
        )
    return result


@router.get("/offline")
def offline_timing(inter_id: str = Query(..., min_length=1)) -> dict[str, Any]:
    """Return schedules, day plans, periods, plans and stage timings for one intersection."""
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT schedule_no, schedule_name, schedule_type_no, priority_no,
                       start_day, end_day, week_day_no, day_plan_no, remark
                FROM dwd_ctl_inter_schedule_cfg
                WHERE is_deleted = 0 AND inter_id = %s
                ORDER BY COALESCE(priority_no, 999999),
                         schedule_type_no, schedule_no, COALESCE(week_day_no, 0)
                """,
                (inter_id,),
            )
            schedules = cur.fetchall()

            cur.execute(
                """
                SELECT inter_id, cross_id, signal_controller_id, day_plan_no,
                       day_plan_name, period_cnt, remark
                FROM dwd_ctl_inter_day_plan_cfg
                WHERE is_deleted = 0 AND inter_id = %s
                ORDER BY day_plan_no
                """,
                (inter_id,),
            )
            day_plan_rows = cur.fetchall()

            cur.execute(
                """
                SELECT dp.day_plan_no, dp.period_seq_no, dp.start_time, dp.end_time,
                       dp.plan_no, dp.ctrl_mode, dp.remark,
                       pc.plan_name, pc.cycle_len_sec
                FROM dwd_ctl_inter_day_plan_period dp
                LEFT JOIN dwd_ctl_inter_plan_cfg pc
                  ON pc.inter_id = dp.inter_id
                 AND pc.plan_no = dp.plan_no
                 AND pc.is_deleted = 0
                WHERE dp.is_deleted = 0 AND dp.inter_id = %s
                ORDER BY dp.day_plan_no, dp.period_seq_no
                """,
                (inter_id,),
            )
            period_rows = cur.fetchall()

            cur.execute(
                """
                SELECT plan_no, plan_name, cycle_len_sec, coord_stage_no,
                       offset_sec, stage_cnt, plan_source_no, remark
                FROM dwd_ctl_inter_plan_cfg
                WHERE is_deleted = 0 AND inter_id = %s
                ORDER BY plan_no
                """,
                (inter_id,),
            )
            plan_rows = cur.fetchall()

            cur.execute(
                """
                SELECT pst.plan_no, pst.stage_seq_no, pst.stage_no,
                       pst.green_sec, pst.yellow_sec, pst.all_red_sec,
                       pst.max_green_sec, pst.min_green_sec, pst.stage_total_sec,
                       sc.stage_name,
                       CAST(sc.flow_combo_json AS CHAR) AS flow_combo_json
                FROM dwd_ctl_inter_plan_stage_timing pst
                LEFT JOIN dwd_ctl_inter_stage_cfg sc
                  ON sc.inter_id = pst.inter_id
                 AND sc.stage_no = pst.stage_no
                 AND sc.is_deleted = 0
                WHERE pst.is_deleted = 0 AND pst.inter_id = %s
                ORDER BY pst.plan_no, pst.stage_seq_no
                """,
                (inter_id,),
            )
            stage_rows = cur.fetchall()

        # 库内阶段最小绿/最大绿可能为信号机脏数据（全方案钉死 3s/60s），
        # 返回前用交通流推导值覆盖；推导失败时保留库内原值。
        try:
            derived_bounds, derived_plan_bounds = _derived_green_bounds(db, inter_id)
        except Exception:
            derived_bounds = {}
            derived_plan_bounds = {}
    finally:
        db.close()

    periods_by_day_plan: dict[int, list[dict[str, Any]]] = {}
    for row in period_rows:
        item = {
            "day_plan_no": row["day_plan_no"],
            "period_seq_no": row["period_seq_no"],
            "start_time": _time_text(row.get("start_time")),
            "end_time": _time_text(row.get("end_time")) or "24:00",
            "plan_no": row["plan_no"],
            "ctrl_mode": row.get("ctrl_mode"),
            "plan_name": row.get("plan_name"),
            "cycle_len_sec": row.get("cycle_len_sec"),
            "remark": row.get("remark") or "",
        }
        periods_by_day_plan.setdefault(row["day_plan_no"], []).append(item)

    day_plans = []
    for row in day_plan_rows:
        day_plan_no = row["day_plan_no"]
        day_plans.append(
            {
                "day_plan_no": day_plan_no,
                "day_plan_name": row.get("day_plan_name") or f"日计划{day_plan_no}",
                "period_cnt": row.get("period_cnt") or 0,
                "remark": row.get("remark") or "",
                "periods": periods_by_day_plan.get(day_plan_no, []),
            }
        )

    stages_by_plan: dict[int, list[dict[str, Any]]] = {}
    for row in stage_rows:
        stage = _stage_payload(row)
        bounds = derived_bounds.get((row["plan_no"], row["stage_no"]))
        if bounds:
            if bounds.get("min_green_sec") is not None:
                stage["min_green_sec"] = bounds["min_green_sec"]
            if bounds.get("max_green_sec") is not None:
                stage["max_green_sec"] = bounds["max_green_sec"]
            stage["green_bounds"] = bounds.get("green_bounds")
        stages_by_plan.setdefault(row["plan_no"], []).append(stage)

    plans = {}
    for row in plan_rows:
        plan_no = row["plan_no"]
        plans[str(plan_no)] = {
            "plan_no": plan_no,
            "plan_name": row.get("plan_name") or f"方案{plan_no}",
            "cycle_len_sec": row.get("cycle_len_sec") or 0,
            "coord_stage_no": row.get("coord_stage_no") or 0,
            "offset_sec": row.get("offset_sec") or 0,
            "stage_cnt": row.get("stage_cnt") or len(stages_by_plan.get(plan_no, [])),
            "remark": row.get("remark") or "",
            "time_periods": (derived_plan_bounds.get(plan_no) or {}).get("time_periods") or [],
            "green_bounds": (derived_plan_bounds.get(plan_no) or {}).get("green_bounds") or {},
            "stages": stages_by_plan.get(plan_no, []),
        }

    info = day_plan_rows[0] if day_plan_rows else {}
    return {
        "inter_id": inter_id,
        "cross_id": info.get("cross_id"),
        "name": _extract_name(info.get("remark")) or info.get("cross_id") or inter_id,
        "schedules": schedules,
        "day_plans": day_plans,
        "plans": plans,
    }


@router.get("/history/intersections")
def history_intersections() -> list[dict[str, Any]]:
    """List intersections that have period-plan execution history."""
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                f"""
                SELECT inter_id, cross_id,
                       MIN(remark) AS remark,
                       COUNT(*) AS period_count,
                       MIN(period_start_time) AS first_time,
                       MAX(period_end_time) AS last_time
                FROM {TABLE_PERIOD_PLAN_EXEC_HIS}
                WHERE is_deleted = 0
                GROUP BY inter_id, cross_id
                ORDER BY inter_id
                """
            )
            rows = cur.fetchall()
    finally:
        db.close()

    result = []
    for row in rows:
        result.append(
            {
                "inter_id": row["inter_id"],
                "cross_id": row["cross_id"],
                "name": _extract_name(row["remark"]) or row["cross_id"],
                "period_count": row["period_count"],
                "first_time": str(row["first_time"]),
                "last_time": str(row["last_time"]),
            }
        )
    return result


@router.get("/history/dates")
def history_dates(inter_id: str = Query(..., min_length=1)) -> list[dict[str, Any]]:
    """List dates with execution history for one intersection."""
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                f"""
                SELECT DATE(period_start_time) AS dt, COUNT(*) AS cnt
                FROM {TABLE_PERIOD_PLAN_EXEC_HIS}
                WHERE is_deleted = 0 AND inter_id = %s
                GROUP BY dt
                ORDER BY dt DESC
                """,
                (inter_id,),
            )
            rows = cur.fetchall()
    finally:
        db.close()
    return [{"date": str(row["dt"]), "count": row["cnt"]} for row in rows]


@router.get("/history/periods")
def history_periods(
    inter_id: str = Query(..., min_length=1),
    date: str = Query(..., min_length=1),
) -> list[dict[str, Any]]:
    """Return historical period execution plans for one intersection/date."""
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                f"""
                SELECT inter_id, cross_id,
                       period_start_time, period_end_time, cycle_len_sec,
                       plan_no, ctrl_mode,
                       CAST(stage_exec_json AS CHAR) AS stage_exec_json,
                       CAST(stage_flow_combo_json AS CHAR) AS stage_flow_combo_json
                FROM {TABLE_PERIOD_PLAN_EXEC_HIS}
                WHERE is_deleted = 0
                  AND inter_id = %s
                  AND DATE(period_start_time) = %s
                ORDER BY period_start_time
                """,
                (inter_id, date),
            )
            rows = cur.fetchall()
    finally:
        db.close()

    return [
        {
            "period_start_time": str(row["period_start_time"]),
            "period_end_time": str(row["period_end_time"]),
            "cycle_len_sec": row["cycle_len_sec"],
            "plan_no": row["plan_no"],
            "ctrl_mode": row["ctrl_mode"],
            "stage_exec_json": _json_loads(row["stage_exec_json"], []),
            "stage_flow_combo_json": _json_loads(row["stage_flow_combo_json"], []),
        }
        for row in rows
    ]
