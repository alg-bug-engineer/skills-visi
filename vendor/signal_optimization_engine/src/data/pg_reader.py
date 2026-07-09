"""PostgreSQL 路网/渠化/流量数据读取：路口进口车道渠化（lane_info 宽表）与车道级流量。

数据来源（road6 库，与 signalControl_agent 路口渠化图工具共用）：
    - dwd_tfc_rltn_wide_inter_ft_link    路口-路段渠化宽表
      关键字段：inter_id / link_id / link_role(entrance|exit) /
                dir8_code(0基，北=0..西北=7) / dir8_label / dir4_code / dir4_label /
                approach_angle / lane_info（'|' 分隔高德车道码，从中心线向外侧）

流量来源（xianchang 模式，可经 PG_FLOW_SCHEMA / PG_FLOW_TABLE 覆盖）：
    - dwd_tfc_lane_roadcross_flow_5mi    路口车道 5 分钟粒度流量
      关键字段：dt(YYYYMMDD) / inter_id / link_id / lane_no /
                turn_move(国标转向码，同 GB_TURNS 键) /
                step_index(0..287，第 k 槽覆盖当日 [k*5, k*5+5) 分钟) /
                vehicle_count（5 分钟过车数）
      进口方向通过 link_id 关联渠化宽表（link_role='entrance'）得到 dir8_code。

渠化生成方式（依据 docs/高德车道码_国标码完整映射表(2).xlsx）：
    1. 高德车道码 → 国标码：先查显式映射表（表内 27 种码），未命中时
       提取方向成分（A=掉头 B=左转 C=直行 D=右转）组合后再查；
       L/R/T/F 等为附加属性（左入/右入/提右/公交），只取其方向成分。
    2. 国标码 → 转向车道：11=直行、12=左转、13=右转、21=直左、22=直右、
       23=左右、24=直左右、31..34=含掉头组合（掉头并入左转）。
       无方向成分的码（Z 空、G 潮汐、T 提右、FZ、TZ 等映射为 "—"）不计入转向。
    含掉头多方向码按表内近似口径：ABC→32、ACD→33、ABD→34、ABCD→24
    （以「全量lane_info映射」逐车道序列与「国标码反向速查」为准）。

转向车道数统计口径：合用车道对其服务的每个转向各计 1 条
（如 B|BC|C|CD → 12|21|11|22 → left=2, through=3, right=1），
与优化器 laneCount（按转向的通行能力车道数）一致。

同一 dir8 方位多条进口 link（主辅路）时，按 dim_link_info 几何与路口中心
计算横向偏移，内侧 link 优先排列（见 data.approach_side_order）。
"""

from __future__ import annotations

import os
import re
from typing import Any

from data.approach_side_order import annotate_and_sort_approaches
from preprocessing.timing.dir8_encoding import (
    DIR4_LABELS,
    DIR8_LABELS,
    dir4_code_from_dir8_no,
    dir8_label,
    normalize_dir8_no,
)
from preprocessing.timing.lane_cluster import build_lane_groups

# 高德车道码 → 国标码（docs/高德车道码_国标码完整映射表(2).xlsx）
# None 表示无方向成分（逐车道映射表中为 "—"），不计入转向统计。
GAODE_TO_GB = {
    # 单方向码
    "C": "11", "B": "12", "D": "13", "A": "31",
    # 双方向组合
    "CD": "22", "BC": "21", "AB": "32", "BD": "23", "AC": "33", "AD": "34",
    # 三/四方向组合（含掉头按表内近似口径）
    "BCD": "24", "ABC": "32", "ACD": "33", "ABD": "34", "ABCD": "24",
    # 含特殊属性（左入/右入/提右/公交），方向成分可映射
    "RD": "13", "LB": "12", "RC": "11", "FC": "11", "LA": "31",
    "TC": "11", "FA": "31", "FCD": "22",
    # 无方向成分：空/潮汐/提右/公交+空/提右+空
    "Z": None, "G": None, "T": None, "FZ": None, "TZ": None,
}

# 国标码 → 含义（用于 API 展示）
GB_LABELS = {
    "11": "直行", "12": "左转", "13": "右转",
    "21": "直左混行", "22": "直右混行", "23": "左右混行", "24": "直左右混行",
    "31": "掉头", "32": "掉头加左转", "33": "掉头加直行", "34": "掉头加右转",
}

# 国标码 → 页面/优化器转向（掉头并入左转）
GB_TURNS = {
    "11": ("through",),
    "12": ("left",),
    "13": ("right",),
    "21": ("left", "through"),
    "22": ("through", "right"),
    "23": ("left", "right"),
    "24": ("left", "through", "right"),
    "31": ("left",),
    "32": ("left",),
    "33": ("left", "through"),
    "34": ("left", "right"),
}

# 并入 left 桶的 turn_move 来源分类（用于展示名：掉头 / 左转 / 左转·掉头）
UTURN_LEFT_TRAFFIC_CODES = frozenset({"31", "33", "34"})
PURE_LEFT_TRAFFIC_CODES = frozenset({"12"})
MIXED_LEFT_TRAFFIC_CODES = frozenset({"21", "23", "24", "32"})
LEFT_LANE_KIND_LABELS = {
    "uturn": "掉头",
    "left": "左转",
    "mixed": "左转/掉头",
    "none": "左转",
}

def _lane_has_uturn(lane: dict[str, Any]) -> bool:
    drive_dir = lane.get("driveDir")
    if drive_dir is not None:
        return bool(int(drive_dir) & 8)
    gb_code = str(lane.get("gbCode") or "")
    if gb_code in {"31", "32", "33", "34"}:
        return True
    return "掉头" in str(lane.get("gbName") or "")


def _lane_has_left_turn(lane: dict[str, Any]) -> bool:
    drive_dir = lane.get("driveDir")
    if drive_dir is not None:
        return bool(int(drive_dir) & 2)
    gb_code = str(lane.get("gbCode") or "")
    if gb_code in {"12", "21", "23", "24", "32"}:
        return True
    return "左转" in str(lane.get("gbName") or "")


def summarize_left_lane_kind(lanes: list[dict[str, Any]]) -> str:
    """进口 left 车道构成：仅掉头 / 仅左转 / 兼有 / 无。"""
    has_uturn = has_left = False
    for lane in lanes:
        if lane.get("laneType", 0) not in (0, None) and lane.get("driveDir") is None:
            if not lane.get("turns"):
                continue
        if _lane_has_uturn(lane):
            has_uturn = True
        if _lane_has_left_turn(lane):
            has_left = True
    if has_uturn and not has_left:
        return "uturn"
    if has_left and not has_uturn:
        return "left"
    if has_uturn and has_left:
        return "mixed"
    return "none"


def display_name_for_left(kind: str) -> str:
    return LEFT_LANE_KIND_LABELS.get(kind, "左转")


def classify_left_traffic_kind(
    uturn_veh: float,
    pure_left_veh: float,
    mixed_left_veh: float,
) -> str:
    kinds: set[str] = set()
    if uturn_veh > 0:
        kinds.add("uturn")
    if pure_left_veh > 0:
        kinds.add("left")
    if mixed_left_veh > 0:
        kinds.add("mixed")
    if not kinds:
        return "left"
    if kinds == {"uturn"}:
        return "uturn"
    if kinds == {"left"}:
        return "left"
    return "mixed"


def gaode_token_to_gb(token: str) -> str | None:
    """单个高德车道码 → 国标码；未在表内时按方向成分组合回退。"""
    if token in GAODE_TO_GB:
        return GAODE_TO_GB[token]
    # 回退：提取方向成分（按 A/B/C/D 顺序组合），如 LBC→BC→21、RCD→CD→22
    direction = "".join(ch for ch in "ABCD" if ch in token)
    return GAODE_TO_GB.get(direction) if direction else None


def connect_pg():
    """按 .env 中 PG* 配置建立连接（dict_row）。"""
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ModuleNotFoundError as exc:  # pragma: no cover - 运行时依赖提示
        raise RuntimeError(
            "缺少 psycopg 依赖，请执行: pip install -e '.[db]' 或 pip install 'psycopg[binary]'"
        ) from exc

    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=int(os.getenv("PGPORT", "5432")),
        user=os.getenv("PGUSER", ""),
        password=os.getenv("PGPASSWORD", ""),
        dbname=os.getenv("PGDATABASE") or os.getenv("PGUSER", ""),
        connect_timeout=8,
        row_factory=dict_row,
    )


def fetch_channelization(conn, inter_id: str) -> dict[str, Any]:
    """读取一个路口的进口/出口渠化；进口解析 lane_info，出口车道数取 dim_link_info.lane_num。

    返回:
        {
          "interId": ...,
          "approaches": [
            {
              "linkId": ..., "linkRole": "entrance"|"exit",
              "dir8Code": 0, "dir8Label": "北",
              "laneTotal": 6, "lanes": [...],   # 进口：lane_info 解析
              "turnLanes": {"left": 1, "through": 3, "right": 2},
              "leftLaneKind": "mixed",         # 仅 entrance
              ...
            },
            {
              "linkRole": "exit", "laneTotal": 3, "lanes": [],  # 出口：无车道明细
              ...
            }, ...
          ],
        }

    同一 dir8 下多条 link（进口/出口分别）按 lateralOffset 降序（内侧在前）；
    lanes 含 laneNo 与 laneSide（仅 entrance）。
    """
    schema = os.getenv("PGSCHEMA", "road6")
    table = os.getenv("PG_CHANNEL_TABLE", "dwd_tfc_rltn_wide_inter_ft_link")
    qualified = _qident(schema) + "." + _qident(table)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT link_id, lower(btrim(link_role::text)) AS link_role,
                   dir8_code, dir8_label, dir4_code, dir4_label,
                   approach_angle, lane_num, lane_info
            FROM {qualified}
            WHERE inter_id::text = %s
              AND lower(btrim(link_role::text)) IN ('entrance', 'exit')
            ORDER BY dir8_code, link_id
            """,
            (inter_id,),
        )
        rows = cur.fetchall()

    center_lon, center_lat = _fetch_inter_center(conn, inter_id, schema)
    link_geom = _fetch_link_geometry(conn, rows, schema)

    approaches: list[dict[str, Any]] = []
    seen_entrance_dirs: set[int] = set()
    for row in rows:
        link_role = str(row.get("link_role") or "")
        if link_role not in {"entrance", "exit"}:
            continue
        dir8_no = normalize_dir8_no(row.get("dir8_code"))
        if dir8_no is None:
            continue
        dir4_code = _to_int(row.get("dir4_code")) or dir4_code_from_dir8_no(dir8_no)
        link_id = str(row.get("link_id") or "")
        geom = link_geom.get(link_id, {})
        side_fields = _link_side_geometry_fields(link_role, geom)

        if link_role == "exit":
            lane_num = _to_int(geom.get("laneNum"))
            if lane_num is None:
                lane_num = _to_int(row.get("lane_num"))
            if not lane_num or lane_num <= 0:
                continue
            approaches.append(
                {
                    "linkId": link_id,
                    "linkRole": link_role,
                    "dir8Code": dir8_no,
                    "dir8Label": _strip_suffix(row.get("dir8_label")) or dir8_label(dir8_no),
                    "dir4Code": dir4_code,
                    "dir4Label": _strip_suffix(row.get("dir4_label")) or DIR4_LABELS.get(dir4_code or -1, ""),
                    "angle": _to_float(row.get("approach_angle")),
                    "laneInfo": "",
                    "gbLaneInfo": "",
                    "laneTotal": lane_num,
                    "lanes": [],
                    "turnLanes": {"left": 0, "through": 0, "right": 0},
                    "roadLevel": geom.get("roadLevel"),
                    **side_fields,
                }
            )
            continue

        lane_info = str(row.get("lane_info") or "").strip().upper()
        tokens = [t for t in re.split(r"[|｜,，/、\s]+", lane_info) if t]
        if not tokens:
            continue
        lanes, turn_lanes = _lanes_from_tokens(tokens)
        if dir8_no is not None:
            seen_entrance_dirs.add(dir8_no)
        approaches.append(
            {
                "linkId": link_id,
                "linkRole": link_role,
                "dir8Code": dir8_no,
                "dir8Label": _strip_suffix(row.get("dir8_label")) or dir8_label(dir8_no),
                "dir4Code": dir4_code,
                "dir4Label": _strip_suffix(row.get("dir4_label")) or DIR4_LABELS.get(dir4_code or -1, ""),
                "angle": _to_float(row.get("approach_angle")),
                "laneInfo": lane_info,
                "gbLaneInfo": "|".join(lane["gbCode"] or "—" for lane in lanes),
                "laneTotal": len(tokens),
                "lanes": lanes,
                "turnLanes": turn_lanes,
                "roadLevel": geom.get("roadLevel"),
                **side_fields,
                "leftLaneKind": summarize_left_lane_kind(lanes),
            }
        )

    # 仅有出口、无进口的方向（如单行道）保留空进口占位
    exit_dirs = {
        normalize_dir8_no(row.get("dir8_code"))
        for row in rows
        if row.get("link_role") == "exit" and normalize_dir8_no(row.get("dir8_code")) is not None
    }
    for dir8_no in sorted(exit_dirs):
        if dir8_no in seen_entrance_dirs:
            continue
        dir4_code = dir4_code_from_dir8_no(dir8_no)
        approaches.append(
            {
                "linkId": "",
                "linkRole": "entrance",
                "dir8Code": dir8_no,
                "dir8Label": dir8_label(dir8_no),
                "dir4Code": dir4_code,
                "dir4Label": DIR4_LABELS.get(dir4_code or -1, ""),
                "angle": None,
                "laneInfo": "",
                "gbLaneInfo": "",
                "laneTotal": 0,
                "lanes": [],
                "turnLanes": {"left": 0, "through": 0, "right": 0},
            }
        )

    approaches = annotate_and_sort_approaches(
        approaches,
        center_lon=center_lon,
        center_lat=center_lat,
    )
    return {"interId": inter_id, "approaches": approaches}


# 页面/优化器转向 → 优化器 turnDirNo（掉头=0，左转=1，直行=2，右转=3；掉头已并入左转）
TURN_TO_TURN_DIR_NO = {"left": 1, "through": 2, "right": 3}
TURN_DIR_NO_LABELS = {1: "左转", 2: "直行", 3: "右转"}

# 关键车道流量：取各车道 5 分钟小时流量的 80% 分位数，再取车道最大值。
CRITICAL_LANE_PERCENTILE = 0.8
FIVE_MIN_FLOW_SCALE = 12.0
FULL_DAY_STEP_COUNT = 288
WEEKDAY_LABELS = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}


def _normalize_weekdays(weekdays: list[int] | None) -> list[int] | None:
    if not weekdays:
        return None
    out = sorted({int(day) for day in weekdays if 1 <= int(day) <= 7})
    return out or None


def _is_flow_date_complete(step_cnt: int | None, max_step: int | None) -> bool:
    if max_step is not None and max_step >= FULL_DAY_STEP_COUNT - 1:
        return True
    return (step_cnt or 0) >= FULL_DAY_STEP_COUNT


def _flow_date_meta(date: str | None, weekdays: list[int] | None, *, complete: bool) -> dict[str, Any]:
    normalized = _normalize_weekdays(weekdays)
    return {
        "date": date,
        "weekdays": normalized,
        "weekdayLabels": [WEEKDAY_LABELS[day] for day in normalized] if normalized else [],
        "dateComplete": complete,
    }


def resolve_flow_date(
    conn,
    inter_id: str,
    *,
    date: str | None = None,
    weekdays: list[int] | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """按显式 date 或调度星期几，解析路口流量观测日。

    未指定 date 时，在库内该路口可用 dt 中优先选取：
      1. 星期几命中 weekdays（若提供）；
      2. 全天 288 个 5 分钟槽位完整的日期；
      3. 满足以上条件的最新 dt；若无完整日则回退到最新可用 dt。
    """
    flow_schema = os.getenv("PG_FLOW_SCHEMA", "xianchang")
    flow_table = os.getenv("PG_FLOW_TABLE", "dwd_tfc_lane_roadcross_flow_5mi")
    qualified_flow = _qident(flow_schema) + "." + _qident(flow_table)
    normalized_weekdays = _normalize_weekdays(weekdays)

    if date:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT count(DISTINCT step_index::int) AS step_cnt,
                       max(step_index::int) AS max_step
                FROM {qualified_flow}
                WHERE inter_id::text = %s AND dt = %s AND is_deleted = 0
                """,
                (inter_id, date),
            )
            row = cur.fetchone() or {}
        complete = _is_flow_date_complete(_to_int(row.get("step_cnt")), _to_int(row.get("max_step")))
        return date, _flow_date_meta(date, normalized_weekdays, complete=complete)

    params: list[Any] = [inter_id]
    weekday_clause = ""
    if normalized_weekdays:
        weekday_clause = " AND dow = ANY(%s)"
        params.append(normalized_weekdays)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            WITH daily AS (
                SELECT dt::text AS dt,
                       count(DISTINCT step_index::int) AS step_cnt,
                       max(step_index::int) AS max_step,
                       EXTRACT(ISODOW FROM to_date(dt::text, 'YYYYMMDD'))::int AS dow
                FROM {qualified_flow}
                WHERE inter_id::text = %s
                  AND is_deleted = 0
                  AND dt IS NOT NULL
                  AND btrim(dt::text) <> ''
                GROUP BY dt
            )
            SELECT dt, step_cnt, max_step
            FROM daily
            WHERE 1=1{weekday_clause}
            ORDER BY
              CASE WHEN step_cnt >= {FULL_DAY_STEP_COUNT} OR max_step >= {FULL_DAY_STEP_COUNT - 1}
                   THEN 0 ELSE 1 END,
              dt DESC
            LIMIT 1
            """,
            params,
        )
        row = cur.fetchone() or {}

    resolved = str(row.get("dt") or "").strip() or None
    if not resolved:
        return None, _flow_date_meta(None, normalized_weekdays, complete=False)
    complete = _is_flow_date_complete(_to_int(row.get("step_cnt")), _to_int(row.get("max_step")))
    return resolved, _flow_date_meta(resolved, normalized_weekdays, complete=complete)


def fetch_turn_flow_stats(
    conn,
    inter_id: str,
    *,
    date: str | None = None,
    weekdays: list[int] | None = None,
    windows: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """统计一个路口指定日期、若干时段内的转向流量，并换算为小时流量(veh/h)。

    数据口径：
        - 5 分钟车道流量表（vehicle_count）按 link_id 关联渠化宽表取进口 dir8_code；
        - turn_move 国标码经 GB_TURNS 映射到 left/through/right，掉头并入左转；
          合用车道（21 直左等）的流量在其服务的各转向间均分；
        - 无方向成分的 turn_move（40/42/99 等非机动/特殊码）与无法关联进口
          方向的 link 不计入转向流量，仅在返回值中给出车辆数提示；
        - 时段总流量 flowVph = 该转向所有车道时段内过车总数 / 实际有数据的
          时长（observedMinutes/60），时段内数据缺失时按实际观测时长换算，
          避免低估；
        - 关键车道流量 criticalLaneVph = 该转向各车道「时段内 5 分钟流量
          换算 veh/h（×12）后 80% 分位数」的最大值（按 link_id+lane_no
          区分车道，分位数采用线性插值，合用车道取其分摊到该转向的流量）。

    参数:
        date:    流量日期 YYYYMMDD；缺省取库内该路口最新一天。
        windows: [("HH:MM", "HH:MM"), ...] 时段列表（左闭右开，支持跨午夜，
                 "24:00" 表示当日结束）；缺省统计全天。

    返回:
        {
          "interId": ..., "interName": ..., "date": "20260609",
          "windows": [["07:00","09:00"], ...],
          "requestedMinutes": 120, "observedMinutes": 120,
          "flows": [
            {"dir8Code": 0, "dir8No": 0, "dirName": "北",
             "turn": "left", "turnDirNo": 1, "turnName": "左转",
             "vehicleCount": 123, "flowVph": 246,
             "criticalLaneVph": 138, "observedLaneCount": 2}, ...
          ],
          "uncountedVehicles": {"40": 12, ...},   # 特殊转向码过车数
          "unmappedVehicles": 0,                  # 关联不到进口方向的过车数
        }
    """
    flow_schema = os.getenv("PG_FLOW_SCHEMA", "xianchang")
    flow_table = os.getenv("PG_FLOW_TABLE", "dwd_tfc_lane_roadcross_flow_5mi")
    qualified_flow = _qident(flow_schema) + "." + _qident(flow_table)
    channel_schema = os.getenv("PGSCHEMA", "road6")
    channel_table = os.getenv("PG_CHANNEL_TABLE", "dwd_tfc_rltn_wide_inter_ft_link")
    qualified_channel = _qident(channel_schema) + "." + _qident(channel_table)

    windows = windows or [("00:00", "24:00")]
    steps = sorted(_windows_to_steps(windows))
    if not steps:
        raise ValueError(f"时段列表无有效 5 分钟槽位: {windows}")

    empty = {
        "interId": inter_id,
        "interName": "",
        "date": date,
        "flowDateMeta": _flow_date_meta(date, weekdays, complete=False),
        "windows": [list(w) for w in windows],
        "requestedMinutes": len(steps) * 5,
        "observedMinutes": 0,
        "flows": [],
        "laneGroups": [],
        "uncountedVehicles": {},
        "unmappedVehicles": 0,
    }

    date, flow_date_meta = resolve_flow_date(conn, inter_id, date=date, weekdays=weekdays)
    empty["date"] = date
    empty["flowDateMeta"] = flow_date_meta
    if not date:
        return empty

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT w.dir8_code::int AS dir8_code, f.turn_move,
                   f.link_id::text AS link_id, f.lane_no,
                   f.step_index::int AS step_index,
                   SUM(f.vehicle_count) AS veh
            FROM {qualified_flow} f
            LEFT JOIN {qualified_channel} w
              ON w.inter_id::text = f.inter_id::text
             AND w.link_id::text = f.link_id::text
             AND lower(btrim(w.link_role::text)) = 'entrance'
            WHERE f.inter_id::text = %s AND f.dt = %s AND f.is_deleted = 0
              AND f.step_index = ANY(%s)
            GROUP BY 1, 2, 3, 4, 5
            """,
            (inter_id, date, steps),
        )
        rows = cur.fetchall()

        cur.execute(
            f"""
            SELECT COUNT(DISTINCT step_index) AS slot_count, MIN(inter_name) AS inter_name
            FROM {qualified_flow}
            WHERE inter_id::text = %s AND dt = %s AND is_deleted = 0
              AND step_index = ANY(%s)
            """,
            (inter_id, date, steps),
        )
        meta = cur.fetchone() or {}

    observed_minutes = (_to_int(meta.get("slot_count")) or 0) * 5
    if not rows or observed_minutes <= 0:
        return empty

    return build_turn_flow_stats_from_lane_rows(
        conn,
        inter_id,
        rows,
        windows=windows,
        flow_date_meta=flow_date_meta,
        inter_name=str(meta.get("inter_name") or ""),
        observed_minutes=observed_minutes,
        date=date,
    )


def build_turn_flow_stats_from_lane_rows(
    conn,
    inter_id: str,
    rows: list[dict[str, Any]],
    *,
    windows: list[tuple[str, str]],
    flow_date_meta: dict[str, Any],
    inter_name: str = "",
    observed_minutes: int | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    """将车道级 5 分钟流量行聚合为转向流量统计（与 fetch_turn_flow_stats 同口径）。"""
    steps = sorted(_windows_to_steps(windows))
    observed_steps = {
        step_index
        for row in rows
        if (step_index := _to_int(row.get("step_index"))) is not None
    }
    if observed_minutes is None:
        observed_minutes = len(observed_steps) * 5 if observed_steps else len(steps) * 5

    turn_veh: dict[tuple[int, str], float] = {}
    left_uturn_veh: dict[int, float] = {}
    left_pure_veh: dict[int, float] = {}
    left_mixed_veh: dict[int, float] = {}
    lane_veh: dict[tuple[int, str], dict[str, float]] = {}
    lane_step_veh: dict[tuple[int, str], dict[str, dict[int, float]]] = {}
    uncounted: dict[str, int] = {}
    unmapped = 0
    for row in rows:
        veh = float(row.get("veh") or 0)
        if veh <= 0:
            continue
        dir8_no = normalize_dir8_no(row.get("dir8_code"))
        turn_move = _to_int(row.get("turn_move"))
        if dir8_no is None:
            unmapped += int(veh)
            continue
        turns = GB_TURNS.get(str(turn_move)) if turn_move is not None else None
        if not turns:
            key = str(turn_move) if turn_move is not None else "null"
            uncounted[key] = uncounted.get(key, 0) + int(veh)
            continue
        share = veh / len(turns)
        step_index = _to_int(row.get("step_index"))
        lane_key = f"{row.get('link_id') or ''}#{row.get('lane_no')}"
        turn_move_str = str(turn_move)
        for turn in turns:
            turn_veh[(dir8_no, turn)] = turn_veh.get((dir8_no, turn), 0.0) + share
            if turn == "left":
                if turn_move_str in UTURN_LEFT_TRAFFIC_CODES:
                    left_uturn_veh[dir8_no] = left_uturn_veh.get(dir8_no, 0.0) + share
                elif turn_move_str in PURE_LEFT_TRAFFIC_CODES:
                    left_pure_veh[dir8_no] = left_pure_veh.get(dir8_no, 0.0) + share
                elif turn_move_str in MIXED_LEFT_TRAFFIC_CODES:
                    left_mixed_veh[dir8_no] = left_mixed_veh.get(dir8_no, 0.0) + share
                else:
                    left_mixed_veh[dir8_no] = left_mixed_veh.get(dir8_no, 0.0) + share
            lanes = lane_veh.setdefault((dir8_no, turn), {})
            lanes[lane_key] = lanes.get(lane_key, 0.0) + share
            if step_index is not None:
                step_values = lane_step_veh.setdefault((dir8_no, turn), {}).setdefault(
                    lane_key, {}
                )
                step_values[step_index] = step_values.get(step_index, 0.0) + share

    hours = observed_minutes / 60.0 if observed_minutes > 0 else 0.0
    flows = []
    for (dir8_no, turn), veh in sorted(
        turn_veh.items(), key=lambda kv: (kv[0][0], TURN_TO_TURN_DIR_NO[kv[0][1]])
    ):
        turn_dir_no = TURN_TO_TURN_DIR_NO[turn]
        display_turn_name = TURN_DIR_NO_LABELS[turn_dir_no]
        left_traffic_kind: str | None = None
        if turn == "left":
            left_traffic_kind = classify_left_traffic_kind(
                left_uturn_veh.get(dir8_no, 0.0),
                left_pure_veh.get(dir8_no, 0.0),
                left_mixed_veh.get(dir8_no, 0.0),
            )
            display_turn_name = display_name_for_left(left_traffic_kind)
        lanes = lane_veh.get((dir8_no, turn), {})
        lane_steps = lane_step_veh.get((dir8_no, turn), {})
        critical_vph = max(
            (
                _percentile_linear(
                    [
                        steps_by_lane.get(step_index, 0.0) * FIVE_MIN_FLOW_SCALE
                        for step_index in observed_steps
                    ],
                    CRITICAL_LANE_PERCENTILE,
                )
                for steps_by_lane in lane_steps.values()
            ),
            default=0.0,
        )
        flow_item = {
            "dir8Code": dir8_no,
            "dir8No": dir8_no,
            "dirName": dir8_label(dir8_no),
            "turn": turn,
            "turnDirNo": turn_dir_no,
            "turnName": display_turn_name,
            "displayTurnName": display_turn_name,
            "vehicleCount": round(veh),
            "flowVph": round(veh / hours) if hours > 0 else 0,
            "criticalLaneVph": round(critical_vph),
            "observedLaneCount": len(lanes),
        }
        if left_traffic_kind is not None:
            flow_item["leftTrafficKind"] = left_traffic_kind
        flows.append(flow_item)

    channelization = fetch_channelization(conn, inter_id)
    lane_groups = build_lane_groups(channelization)
    lane_group_flows = _lane_group_flow_items(
        lane_groups,
        lane_veh,
        lane_step_veh,
        observed_steps,
        observed_minutes,
    )

    return {
        "interId": inter_id,
        "interName": inter_name,
        "date": date,
        "flowDateMeta": flow_date_meta,
        "windows": [list(w) for w in windows],
        "requestedMinutes": len(steps) * 5,
        "observedMinutes": observed_minutes,
        "flows": flows,
        "laneGroups": lane_group_flows,
        "uncountedVehicles": uncounted,
        "unmappedVehicles": unmapped,
    }


def _lane_group_flow_items(
    lane_groups: list[dict[str, Any]],
    lane_veh: dict[tuple[int, str], dict[str, float]],
    lane_step_veh: dict[tuple[int, str], dict[str, dict[int, float]]],
    observed_steps: set[int],
    observed_minutes: int,
) -> list[dict[str, Any]]:
    hours = observed_minutes / 60.0 if observed_minutes > 0 else 0.0
    if hours <= 0:
        return []
    items: list[dict[str, Any]] = []
    for group in lane_groups:
        dir8_no = _to_int(group.get("dir8No")) or normalize_dir8_no(group.get("dir8Code"))
        if dir8_no is None:
            continue
        lane_nos = {_to_int(lane_no) for lane_no in group.get("laneNos") or []}
        lane_nos.discard(None)
        link_id = str(group.get("linkId") or "")
        turns = _group_flow_turns(group.get("capabilities") or [])
        veh_total = 0.0
        critical = 0.0
        for turn in turns:
            by_lane = lane_veh.get((dir8_no, turn), {})
            for lane_key, veh in by_lane.items():
                if _lane_key_in_group(lane_key, lane_nos, link_id):
                    veh_total += veh
            step_by_lane = lane_step_veh.get((dir8_no, turn), {})
            for lane_key, steps_by_lane in step_by_lane.items():
                if not _lane_key_in_group(lane_key, lane_nos, link_id):
                    continue
                critical = max(
                    critical,
                    _percentile_linear(
                        [
                            steps_by_lane.get(step_index, 0.0) * FIVE_MIN_FLOW_SCALE
                            for step_index in observed_steps
                        ],
                        CRITICAL_LANE_PERCENTILE,
                    ),
                )
        primary_turn = _primary_turn_dir_no(group.get("capabilities") or [])
        items.append(
            {
                "laneGroupId": group.get("laneGroupId"),
                "laneGroupKey": group.get("laneGroupKey") or group.get("laneGroupId"),
                "linkId": link_id,
                "approachIndex": group.get("approachIndex"),
                "dir8No": group.get("dir8No"),
                "dir8Code": dir8_no,
                "laneNos": sorted(lane_no for lane_no in lane_nos if lane_no is not None),
                "capabilities": group.get("capabilities") or [],
                "clusterKind": group.get("clusterKind"),
                "primaryFamily": group.get("primaryFamily"),
                "separated": group.get("separated"),
                "turnDirNo": primary_turn,
                "linkLaneTotal": group.get("linkLaneTotal"),
                "sourceLaneGroupKeys": group.get("sourceLaneGroupKeys") or [group.get("laneGroupKey") or group.get("laneGroupId")],
                "vehicleCount": round(veh_total),
                "flowVph": round(veh_total / hours),
                "criticalLaneVph": round(critical),
            }
        )
    return items


def _group_flow_turns(capabilities: list[Any]) -> set[str]:
    turns: set[str] = set()
    caps = {str(cap) for cap in capabilities}
    if "直" in caps:
        turns.add("through")
    if "左" in caps or "掉" in caps:
        turns.add("left")
    if "右" in caps:
        turns.add("right")
    return turns


def _primary_turn_dir_no(capabilities: list[Any]) -> int | None:
    caps = {str(cap) for cap in capabilities}
    if "掉" in caps:
        return 0
    if "左" in caps:
        return 1
    if "直" in caps:
        return 2
    if "右" in caps:
        return 3
    return None


def _lane_no_from_key(lane_key: str) -> int | None:
    _, _, lane_no = str(lane_key).partition("#")
    return _to_int(lane_no)


def _link_id_from_key(lane_key: str) -> str:
    link_id, _, _ = str(lane_key).partition("#")
    return link_id


def _lane_key_in_group(lane_key: str, lane_nos: set[int | None], link_id: str = "") -> bool:
    lane_no = _lane_no_from_key(lane_key)
    if lane_no not in lane_nos:
        return False
    return not link_id or _link_id_from_key(lane_key) == link_id


def fetch_turn_flow_series(
    conn,
    inter_id: str,
    *,
    date: str | None = None,
    weekdays: list[int] | None = None,
    interval_min: int = 15,
) -> dict[str, Any]:
    """统计一个路口全天各进口转向的流量时序（用于流量曲线图）。

    将 5 分钟槽位聚合为 interval_min 粒度（须为 5 的倍数，5..120），
    每个时段输出折算小时流量：
        - totalVph：该转向总流量（合用车道按 GB_TURNS 均分，掉头并入左转）；
        - criticalVph：该转向关键车道流量 = 各车道 5 分钟小时流量
          80% 分位数的最大值。
    全路口在该时段完全无数据时，两个序列均为 None（曲线断开），
    有数据但该转向无过车时为 0。

    返回:
        {
          "interId": ..., "interName": ..., "date": "20260609",
          "intervalMinutes": 15,
          "times": ["00:00", "00:15", ...],
          "series": [
            {"dir8Code": 0, "dir8No": 0, "dirName": "北",
             "turn": "left", "turnDirNo": 1, "turnName": "左转",
             "totalVph": [12, None, ...], "criticalVph": [8, None, ...]}, ...
          ],
        }
    """
    if interval_min % 5 != 0 or not 5 <= interval_min <= 120:
        raise ValueError(f"interval_min 须为 5 的倍数且在 5..120 之间: {interval_min}")
    flow_schema = os.getenv("PG_FLOW_SCHEMA", "xianchang")
    flow_table = os.getenv("PG_FLOW_TABLE", "dwd_tfc_lane_roadcross_flow_5mi")
    qualified_flow = _qident(flow_schema) + "." + _qident(flow_table)
    channel_schema = os.getenv("PGSCHEMA", "road6")
    channel_table = os.getenv("PG_CHANNEL_TABLE", "dwd_tfc_rltn_wide_inter_ft_link")
    qualified_channel = _qident(channel_schema) + "." + _qident(channel_table)

    steps_per_bucket = interval_min // 5
    bucket_count = -(-288 // steps_per_bucket)
    times = [f"{(i * interval_min) // 60:02d}:{(i * interval_min) % 60:02d}" for i in range(bucket_count)]

    result: dict[str, Any] = {
        "interId": inter_id,
        "interName": "",
        "date": date,
        "flowDateMeta": _flow_date_meta(date, weekdays, complete=False),
        "intervalMinutes": interval_min,
        "times": times,
        "series": [],
        "laneGroupSeries": [],
        "approachSeries": [],
    }

    date, flow_date_meta = resolve_flow_date(conn, inter_id, date=date, weekdays=weekdays)
    result["date"] = date
    result["flowDateMeta"] = flow_date_meta
    if not date:
        return result

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT (f.step_index::int / %s)::int AS bucket,
                   f.step_index::int AS step_index,
                   w.dir8_code::int AS dir8_code, f.turn_move,
                   f.link_id::text AS link_id, f.lane_no,
                   SUM(f.vehicle_count) AS veh,
                   MIN(f.inter_name) AS inter_name
            FROM {qualified_flow} f
            LEFT JOIN {qualified_channel} w
              ON w.inter_id::text = f.inter_id::text
             AND w.link_id::text = f.link_id::text
             AND lower(btrim(w.link_role::text)) = 'entrance'
            WHERE f.inter_id::text = %s AND f.dt = %s AND f.is_deleted = 0
            GROUP BY 1, 2, 3, 4, 5, 6
            """,
            (steps_per_bucket, inter_id, date),
        )
        rows = cur.fetchall()
    if not rows:
        return result

    inter_name = str(result.get("interName") or "")
    for row in rows:
        if not inter_name and row.get("inter_name"):
            inter_name = str(row["inter_name"])
            break

    return build_turn_flow_series_from_lane_rows(
        conn,
        inter_id,
        rows,
        interval_min=interval_min,
        flow_date_meta=flow_date_meta,
        inter_name=inter_name,
        date=date,
    )


def build_turn_flow_series_from_lane_rows(
    conn,
    inter_id: str,
    rows: list[dict[str, Any]],
    *,
    interval_min: int,
    flow_date_meta: dict[str, Any],
    inter_name: str = "",
    date: str | None = None,
) -> dict[str, Any]:
    """将车道级 5 分钟流量行聚合为全天转向流量时序（与 fetch_turn_flow_series 同口径）。"""
    if interval_min % 5 != 0 or not 5 <= interval_min <= 120:
        raise ValueError(f"interval_min 须为 5 的倍数且在 5..120 之间: {interval_min}")

    steps_per_bucket = interval_min // 5
    bucket_count = -(-288 // steps_per_bucket)
    times = [f"{(i * interval_min) // 60:02d}:{(i * interval_min) % 60:02d}" for i in range(bucket_count)]

    result: dict[str, Any] = {
        "interId": inter_id,
        "interName": inter_name,
        "date": date,
        "flowDateMeta": flow_date_meta,
        "intervalMinutes": interval_min,
        "times": times,
        "series": [],
        "laneGroupSeries": [],
        "approachSeries": [],
    }
    if not rows:
        result["dataComplete"] = False
        return result

    observed: set[int] = set()
    observed_steps_by_bucket: dict[int, set[int]] = {}
    left_uturn_veh: dict[int, float] = {}
    left_pure_veh: dict[int, float] = {}
    left_mixed_veh: dict[int, float] = {}
    total_veh: dict[tuple[int, str], dict[int, float]] = {}
    lane_step_veh: dict[tuple[int, str], dict[int, dict[str, dict[int, float]]]] = {}
    for row in rows:
        if not result["interName"] and row.get("inter_name"):
            result["interName"] = str(row["inter_name"])
        step_index = _to_int(row.get("step_index"))
        bucket = _to_int(row.get("bucket"))
        if bucket is None and step_index is not None:
            bucket = step_index // steps_per_bucket
        if bucket is None or not 0 <= bucket < bucket_count:
            continue
        observed.add(bucket)
        if step_index is not None:
            observed_steps_by_bucket.setdefault(bucket, set()).add(step_index)
        veh = float(row.get("veh") or 0)
        dir8_no = normalize_dir8_no(row.get("dir8_code"))
        turn_move = _to_int(row.get("turn_move"))
        if veh <= 0 or dir8_no is None:
            continue
        turns = GB_TURNS.get(str(turn_move)) if turn_move is not None else None
        if not turns:
            continue
        share = veh / len(turns)
        lane_key = f"{row.get('link_id') or ''}#{row.get('lane_no')}"
        turn_move_str = str(turn_move)
        for turn in turns:
            key = (dir8_no, turn)
            if turn == "left":
                if turn_move_str in UTURN_LEFT_TRAFFIC_CODES:
                    left_uturn_veh[dir8_no] = left_uturn_veh.get(dir8_no, 0.0) + share
                elif turn_move_str in PURE_LEFT_TRAFFIC_CODES:
                    left_pure_veh[dir8_no] = left_pure_veh.get(dir8_no, 0.0) + share
                elif turn_move_str in MIXED_LEFT_TRAFFIC_CODES:
                    left_mixed_veh[dir8_no] = left_mixed_veh.get(dir8_no, 0.0) + share
                else:
                    left_mixed_veh[dir8_no] = left_mixed_veh.get(dir8_no, 0.0) + share
            buckets = total_veh.setdefault(key, {})
            buckets[bucket] = buckets.get(bucket, 0.0) + share
            if step_index is not None:
                lane_steps = lane_step_veh.setdefault(key, {}).setdefault(bucket, {})
                step_values = lane_steps.setdefault(lane_key, {})
                step_values[step_index] = step_values.get(step_index, 0.0) + share

    scale = 60.0 / interval_min
    for (dir8_no, turn), buckets in sorted(
        total_veh.items(), key=lambda kv: (kv[0][0], TURN_TO_TURN_DIR_NO[kv[0][1]])
    ):
        turn_dir_no = TURN_TO_TURN_DIR_NO[turn]
        display_turn_name = TURN_DIR_NO_LABELS[turn_dir_no]
        left_traffic_kind: str | None = None
        if turn == "left":
            left_traffic_kind = classify_left_traffic_kind(
                left_uturn_veh.get(dir8_no, 0.0),
                left_pure_veh.get(dir8_no, 0.0),
                left_mixed_veh.get(dir8_no, 0.0),
            )
            display_turn_name = display_name_for_left(left_traffic_kind)
        total_series: list[int | None] = []
        critical_series: list[int | None] = []
        for i in range(bucket_count):
            if i not in observed:
                total_series.append(None)
                critical_series.append(None)
                continue
            total_series.append(round(buckets.get(i, 0.0) * scale))
            lane_steps = lane_step_veh.get((dir8_no, turn), {}).get(i, {})
            critical_series.append(
                round(
                    max(
                        (
                            _percentile_linear(
                                [
                                    steps_by_lane.get(step_index, 0.0) * FIVE_MIN_FLOW_SCALE
                                    for step_index in observed_steps_by_bucket.get(i, set())
                                ],
                                CRITICAL_LANE_PERCENTILE,
                            )
                            for steps_by_lane in lane_steps.values()
                        ),
                        default=0.0,
                    )
                )
            )
        series_item = {
            "dir8Code": dir8_no,
            "dir8No": dir8_no,
            "dirName": dir8_label(dir8_no),
            "turn": turn,
            "turnDirNo": turn_dir_no,
            "turnName": display_turn_name,
            "displayTurnName": display_turn_name,
            "totalVph": total_series,
            "criticalVph": critical_series,
        }
        if left_traffic_kind is not None:
            series_item["leftTrafficKind"] = left_traffic_kind
        result["series"].append(series_item)
    channelization = fetch_channelization(conn, inter_id)
    lane_groups = build_lane_groups(channelization)
    result["laneGroupSeries"] = _lane_group_series_items(
        lane_groups,
        total_veh,
        lane_step_veh,
        observed,
        observed_steps_by_bucket,
        bucket_count,
        interval_min,
    )
    result["approachSeries"] = _approach_series_items(
        lane_step_veh,
        observed,
        observed_steps_by_bucket,
        bucket_count,
    )
    profile_mode = bool(flow_date_meta.get("profileMode"))
    if observed:
        last_bucket = max(observed)
        result["lastDataBucket"] = last_bucket
        result["lastDataTime"] = times[last_bucket] if 0 <= last_bucket < len(times) else None
        result["dataComplete"] = profile_mode or last_bucket >= bucket_count - 1
    else:
        result["lastDataBucket"] = None
        result["lastDataTime"] = None
        result["dataComplete"] = False
    result["flowDateMeta"] = {
        **flow_date_meta,
        "dateComplete": result.get("dataComplete", False),
    }
    return result


def _lane_group_series_items(
    lane_groups: list[dict[str, Any]],
    total_veh: dict[tuple[int, str], dict[int, float]],
    lane_step_veh: dict[tuple[int, str], dict[int, dict[str, dict[int, float]]]],
    observed_buckets: set[int],
    observed_steps_by_bucket: dict[int, set[int]],
    bucket_count: int,
    interval_min: int,
) -> list[dict[str, Any]]:
    scale = 60.0 / interval_min
    items: list[dict[str, Any]] = []
    for group in lane_groups:
        dir8_no = _to_int(group.get("dir8No")) or normalize_dir8_no(group.get("dir8Code"))
        if dir8_no is None:
            continue
        lane_nos = {_to_int(lane_no) for lane_no in group.get("laneNos") or []}
        lane_nos.discard(None)
        link_id = str(group.get("linkId") or "")
        turns = sorted(_group_flow_turns(group.get("capabilities") or []))
        if not turns:
            continue
        total_series: list[int | None] = []
        critical_series: list[int | None] = []
        for bucket in range(bucket_count):
            if bucket not in observed_buckets:
                total_series.append(None)
                critical_series.append(None)
                continue
            bucket_veh = 0.0
            bucket_critical = 0.0
            for turn in turns:
                for lane_key, steps_by_lane in lane_step_veh.get((dir8_no, turn), {}).get(bucket, {}).items():
                    if not _lane_key_in_group(lane_key, lane_nos, link_id):
                        continue
                    bucket_veh += sum(steps_by_lane.values())
                    bucket_critical = max(
                        bucket_critical,
                        _percentile_linear(
                            [
                                steps_by_lane.get(step_index, 0.0) * FIVE_MIN_FLOW_SCALE
                                for step_index in observed_steps_by_bucket.get(bucket, set())
                            ],
                            CRITICAL_LANE_PERCENTILE,
                        ),
                    )
            total_series.append(round(bucket_veh * scale))
            critical_series.append(round(bucket_critical))
        turn_dir_no = _primary_turn_dir_no(group.get("capabilities") or [])
        turn = _turn_en_for_dir_no(turn_dir_no)
        cap_label = "".join(str(x) for x in group.get("capabilities") or []) or "车流"
        lane_label = ",".join(str(x) for x in sorted(lane_no for lane_no in lane_nos if lane_no is not None))
        approach_label = f"进口{group.get('approachIndex')}" if group.get("linkId") else ""
        label_parts = [part for part in (approach_label, f"车道{lane_label}" if lane_label else "") if part]
        items.append(
            {
                "laneGroupId": group.get("laneGroupId"),
                "laneGroupKey": group.get("laneGroupKey") or group.get("laneGroupId"),
                "linkId": link_id,
                "approachIndex": group.get("approachIndex"),
                "dir8Code": dir8_no,
                "dir8No": dir8_no,
                "dirName": dir8_label(dir8_no),
                "turn": turn,
                "turnDirNo": turn_dir_no,
                "turnName": cap_label,
                "displayTurnName": f"{cap_label}车道簇{('(' + '·'.join(label_parts) + ')') if label_parts else ''}",
                "laneNos": sorted(lane_no for lane_no in lane_nos if lane_no is not None),
                "capabilities": group.get("capabilities") or [],
                "clusterKind": group.get("clusterKind"),
                "primaryFamily": group.get("primaryFamily"),
                "separated": group.get("separated"),
                "linkLaneTotal": group.get("linkLaneTotal"),
                "sourceLaneGroupKeys": group.get("sourceLaneGroupKeys") or [group.get("laneGroupKey") or group.get("laneGroupId")],
                "totalVph": total_series,
                "criticalVph": critical_series,
            }
        )
    return items


APPROACH_SEGMENTATION_TURNS = ("left", "through")


def _approach_series_items(
    lane_step_veh: dict[tuple[int, str], dict[int, dict[str, dict[int, float]]]],
    observed_buckets: set[int],
    observed_steps_by_bucket: dict[int, set[int]],
    bucket_count: int,
) -> list[dict[str, Any]]:
    """Per-approach max-lane 5-minute flow series (excludes right-turn lanes)."""
    dir8_nos = sorted(
        {
            dir8_no
            for dir8_no, turn in lane_step_veh.keys()
            if turn in APPROACH_SEGMENTATION_TURNS and dir8_no is not None
        }
    )
    items: list[dict[str, Any]] = []
    for dir8_no in dir8_nos:
        critical_series: list[int | None] = []
        for bucket in range(bucket_count):
            if bucket not in observed_buckets:
                critical_series.append(None)
                continue
            max_lane_vph = 0.0
            for turn in APPROACH_SEGMENTATION_TURNS:
                for steps_by_lane in lane_step_veh.get((dir8_no, turn), {}).get(bucket, {}).values():
                    for step_index in observed_steps_by_bucket.get(bucket, set()):
                        max_lane_vph = max(
                            max_lane_vph,
                            steps_by_lane.get(step_index, 0.0) * FIVE_MIN_FLOW_SCALE,
                        )
            critical_series.append(round(max_lane_vph))
        items.append(
            {
                "dir8Code": dir8_no,
                "dir8No": dir8_no,
                "dirName": dir8_label(dir8_no),
                "turn": "approach",
                "turnName": "关键车道",
                "displayTurnName": "进口关键车道",
                "criticalVph": critical_series,
            }
        )
    return items


def _turn_en_for_dir_no(turn_dir_no: int | None) -> str:
    if turn_dir_no == 0:
        return "left"
    if turn_dir_no == 1:
        return "left"
    if turn_dir_no == 2:
        return "through"
    if turn_dir_no == 3:
        return "right"
    return "through"


def _windows_to_steps(windows: list[tuple[str, str]]) -> set[int]:
    """时段列表 → 5 分钟槽位下标集合（0..287，左闭右开，支持跨午夜）。"""
    steps: set[int] = set()
    for start, end in windows:
        start_min = _hhmm_to_minutes(start)
        end_min = _hhmm_to_minutes(end)
        if start_min is None or end_min is None:
            continue
        start_step = start_min // 5
        end_step = min(-(-end_min // 5), 288)
        if end_min <= start_min:  # 跨午夜（含 start==end 视为整天）
            steps.update(range(start_step, 288))
            steps.update(range(0, end_step))
        else:
            steps.update(range(start_step, end_step))
    return steps


def _hhmm_to_minutes(value: str) -> int | None:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", str(value or "").strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 24 or minute > 59 or (hour == 24 and minute > 0):
        return None
    return hour * 60 + minute


def _percentile_linear(values: list[float], percentile: float) -> float:
    """Return a percentile using numpy's default linear interpolation convention."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pct = max(0.0, min(1.0, percentile))
    position = (len(ordered) - 1) * pct
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _lanes_from_tokens(tokens: list[str]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    turn_lanes = {"left": 0, "through": 0, "right": 0}
    lanes: list[dict[str, Any]] = []
    for token in tokens:
        gb_code = gaode_token_to_gb(token)
        turns = GB_TURNS.get(gb_code, ())
        lanes.append(
            {
                "code": token,
                "gbCode": gb_code,
                "gbName": GB_LABELS.get(gb_code, "—") if gb_code else "—",
                "turns": list(turns),
            }
        )
        for turn in turns:
            turn_lanes[turn] += 1
    return lanes, turn_lanes


def _link_side_geometry_fields(link_role: str, geom: dict[str, Any]) -> dict[str, Any]:
    start_lon = geom.get("startLon")
    start_lat = geom.get("startLat")
    end_lon = geom.get("stopLon")
    end_lat = geom.get("stopLat")
    if link_role == "exit":
        return {
            "_positionLon": start_lon,
            "_positionLat": start_lat,
            "_travelFromLon": start_lon,
            "_travelFromLat": start_lat,
            "_travelToLon": end_lon,
            "_travelToLat": end_lat,
        }
    return {
        "_stopLon": end_lon,
        "_stopLat": end_lat,
        "_startLon": start_lon,
        "_startLat": start_lat,
    }


def _qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _fetch_inter_center(conn, inter_id: str, schema: str) -> tuple[float | None, float | None]:
    dim_inter = _qident(schema) + "." + _qident(os.getenv("PG_DIM_INTER_TABLE", "dim_inter_info"))
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT ST_X(geom_center::geometry) AS center_lon,
                       ST_Y(geom_center::geometry) AS center_lat
                FROM {dim_inter}
                WHERE inter_id::text = %s
                LIMIT 1
                """,
                (inter_id,),
            )
            center_row = cur.fetchone()
    except Exception:
        conn.rollback()
        return None, None
    if not center_row:
        return None, None
    return _to_float(center_row.get("center_lon")), _to_float(center_row.get("center_lat"))


def _fetch_link_geometry(
    conn,
    rows: list[dict[str, Any]],
    schema: str,
) -> dict[str, dict[str, float | int | None]]:
    link_ids = sorted({str(row.get("link_id") or "") for row in rows if row.get("link_id")})
    if not link_ids:
        return {}

    dim_link_table = os.getenv("PG_DIM_LINK_TABLE", "dim_link_info")
    candidates: list[str] = []
    for name in ("dim_link_info", dim_link_table):
        if name not in candidates:
            candidates.append(name)

    fetched: list[dict[str, Any]] = []
    for table_name in candidates:
        dim_link = _qident(schema) + "." + _qident(table_name)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT link_id, road_level, lane_num,
                           ST_X(ST_EndPoint(geom::geometry)) AS stop_lon,
                           ST_Y(ST_EndPoint(geom::geometry)) AS stop_lat,
                           ST_X(ST_StartPoint(geom::geometry)) AS start_lon,
                           ST_Y(ST_StartPoint(geom::geometry)) AS start_lat
                    FROM {dim_link}
                    WHERE link_id = ANY(%s)
                    """,
                    (link_ids,),
                )
                fetched = cur.fetchall()
            if fetched:
                break
        except Exception:
            conn.rollback()
            continue
    if not fetched:
        return {}

    out: dict[str, dict[str, float | int | None]] = {}
    for row in fetched:
        link_id = str(row.get("link_id") or "")
        if not link_id:
            continue
        out[link_id] = {
            "roadLevel": _to_int(row.get("road_level")),
            "laneNum": _to_int(row.get("lane_num")),
            "stopLon": _to_float(row.get("stop_lon")),
            "stopLat": _to_float(row.get("stop_lat")),
            "startLon": _to_float(row.get("start_lon")),
            "startLat": _to_float(row.get("start_lat")),
        }
    return out


def _strip_suffix(label: Any) -> str:
    return str(label or "").replace("进口", "").replace("出口", "").strip()


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
