"""把真实逐转向流量/饱和度/车道绑定到信号相位阶段。

对齐参考项目（signal_optimization_engine）的"需求驱动"优化输入：每个相位阶段
携带真实转向的 ``phaseDirInfoDTOList``（dir8No / turnDirNo / turnFlowTotal(vph) /
laneCount / turnSaturation），供单点优化器计算可信配时，而非占位常量。

数据真源约束（docs/rule.md 14/16）：
- 流量/饱和度/车道来自 PG 查询结果，禁止编造；
- 绑定不到真实流量的转向标注 ``flow_available=false``，阶段/信号记录降级原因；
- ``turn_flow_total`` 为"每 5 分钟切片的小时当量"（见 traffic_metrics_logic），
  时段内按均值折算为代表性 vph。
"""

from __future__ import annotations

from typing import Any

# PG turn_dir_no -> 优化引擎 turnDirNo（引擎：0=掉头,1=左,2=直,3=右）
# PG：1=左,2=直,3=右,4=掉头,0=方向聚合（非真实转向，跳过）
_PG_TURN_TO_ENGINE: dict[int, int] = {1: 1, 2: 2, 3: 3, 4: 0}


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    num = _to_float(value)
    return int(num) if num is not None else None


def _link_to_dir8(channel_rows: list[dict[str, Any]]) -> dict[str, int]:
    """进口 link_id -> dir8_code（0..7）。"""
    mapping: dict[str, int] = {}
    for row in channel_rows or []:
        if str(row.get("link_role", "")).lower() != "entrance":
            continue
        link = row.get("link_id")
        dir8 = _to_int(row.get("dir8_code"))
        if link is None or dir8 is None:
            continue
        mapping[str(link)] = dir8
    return mapping


def _aggregate_flow(flow_rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    """(link_id, pg_turn) -> {vph: 时段均值, lane: 最大车道数}。"""
    buckets: dict[tuple[str, int], dict[str, list[float]]] = {}
    for row in flow_rows or []:
        link = str(row.get("link_id") or "")
        turn = _to_int(row.get("turn_dir_no"))
        if not link or turn is None:
            continue
        bucket = buckets.setdefault((link, turn), {"flows": [], "lanes": []})
        flow = _to_float(row.get("turn_flow_total"))
        if flow is not None:
            bucket["flows"].append(flow)
        lane = _to_float(row.get("lane_count"))
        if lane and lane > 0:
            bucket["lanes"].append(lane)
    agg: dict[tuple[str, int], dict[str, Any]] = {}
    for key, bucket in buckets.items():
        flows = bucket["flows"]
        lanes = bucket["lanes"]
        agg[key] = {
            "vph": round(sum(flows) / len(flows), 1) if flows else None,
            "lane": int(max(lanes)) if lanes else None,
        }
    return agg


def _aggregate_saturation(sat_rows: list[dict[str, Any]]) -> dict[tuple[str, int], float]:
    buckets: dict[tuple[str, int], list[float]] = {}
    for row in sat_rows or []:
        link = str(row.get("link_id") or "")
        turn = _to_int(row.get("turn_dir_no"))
        if not link or turn is None:
            continue
        val = _to_float(row.get("turn_saturation"))
        if val is None:
            continue
        buckets.setdefault((link, turn), []).append(val)
    return {key: round(sum(vals) / len(vals), 4) for key, vals in buckets.items() if vals}


def _stage_movements_from_mapping(
    rows: list[dict[str, Any]],
    active_plan_no: Any,
) -> dict[str, list[tuple[str, int]]]:
    """stage_no(str) -> [(link_id, pg_turn), ...]，来自信控原子-车道映射。"""
    by_stage: dict[str, list[tuple[str, int]]] = {}
    for row in rows or []:
        stage = str(row.get("stage_no") or "")
        if not stage:
            continue
        plan_no = row.get("plan_no")
        if (
            plan_no is not None
            and active_plan_no is not None
            and str(plan_no) != str(active_plan_no)
        ):
            continue
        link = str(row.get("link_id") or "")
        turn = _to_int(row.get("turn_dir_no"))
        if not link or turn is None:
            continue
        pair = (link, turn)
        movements = by_stage.setdefault(stage, [])
        if pair not in movements:
            movements.append(pair)
    return by_stage


def _stage_movements_from_motor_flow(
    rows: list[dict[str, Any]],
    link_to_dir8: dict[str, int],
) -> dict[str, list[tuple[str, int]]]:
    """回退：stage_no -> [(link_id, pg_turn)]，来自阶段-机动车流关系。"""
    # flow_type_no: 1=直(2),2=左(1),3=右(3),4=掉(4)
    flow_type_to_pg = {1: 2, 2: 1, 3: 3, 4: 4}
    dir8_to_link = {dir8: link for link, dir8 in link_to_dir8.items()}
    by_stage: dict[str, list[tuple[str, int]]] = {}
    for row in rows or []:
        stage = str(row.get("stage_no") or "")
        if not stage:
            continue
        pg_turn = flow_type_to_pg.get(_to_int(row.get("flow_type_no")) or -1)
        dir8 = _to_int(row.get("f_dir8_no"))
        link = row.get("from_link_id") or dir8_to_link.get(dir8 if dir8 is not None else -1)
        if link is None or pg_turn is None:
            continue
        pair = (str(link), pg_turn)
        movements = by_stage.setdefault(stage, [])
        if pair not in movements:
            movements.append(pair)
    return by_stage


def bind_turn_flows_to_signal(
    signal: dict[str, Any],
    *,
    flow_rows: list[dict[str, Any]] | None,
    saturation_rows: list[dict[str, Any]] | None,
    signal_lane_mapping_rows: list[dict[str, Any]] | None,
    channel_rows: list[dict[str, Any]] | None,
    stage_motor_flow_rows: list[dict[str, Any]] | None = None,
    period: str | None = None,
) -> dict[str, Any]:
    """把真实转向流量绑定到 ``signal.phase_stage_timing_list`` 各阶段。

    就地写入每个阶段的 ``phaseDirInfoDTOList``/``stage_flow_vph``，并在
    ``signal.flow_binding`` 记录绑定结果与降级原因。返回同一 ``signal`` 引用。
    """
    stages = signal.get("phase_stage_timing_list") or []
    if not stages:
        signal["flow_binding"] = {
            "ok": False,
            "period": period,
            "reason": "信号无相位阶段，无法绑定流量",
            "source": "none",
        }
        return signal

    link_to_dir8 = _link_to_dir8(channel_rows or [])
    flow_agg = _aggregate_flow(flow_rows or [])
    sat_agg = _aggregate_saturation(saturation_rows or [])
    active_plan_no = signal.get("plan_no")

    stage_moves = _stage_movements_from_mapping(signal_lane_mapping_rows or [], active_plan_no)
    if not any(stage_moves.get(str(s.get("phase_stage_id"))) for s in stages):
        stage_moves = _stage_movements_from_motor_flow(stage_motor_flow_rows or [], link_to_dir8)

    bound_stages: list[str] = []
    unbound_stages: list[str] = []
    total_flow = 0.0

    for stage in stages:
        stage_id = str(stage.get("phase_stage_id") or "")
        movements = stage_moves.get(stage_id) or []
        dir_infos: list[dict[str, Any]] = []
        stage_flow = 0.0
        has_flow = False
        for link, pg_turn in movements:
            engine_turn = _PG_TURN_TO_ENGINE.get(pg_turn)
            if engine_turn is None:
                continue  # 方向聚合(0) 等非真实转向，跳过
            flow_info = flow_agg.get((link, pg_turn)) or {}
            vph = flow_info.get("vph")
            lane = flow_info.get("lane")
            sat = sat_agg.get((link, pg_turn))
            dir8 = link_to_dir8.get(link)
            dir_infos.append(
                {
                    "dir8No": dir8,
                    "turnDirNo": engine_turn,
                    "linkId": link,
                    "turnFlowTotal": int(round(vph)) if vph is not None else None,
                    "laneCount": lane,
                    "turnSaturation": sat,
                    "flow_available": vph is not None,
                }
            )
            if vph is not None:
                stage_flow += vph
                has_flow = True

        stage["phaseDirInfoDTOList"] = dir_infos
        stage["stage_flow_vph"] = int(round(stage_flow)) if has_flow else None
        if has_flow:
            total_flow += stage_flow
            bound_stages.append(stage_id)
        else:
            unbound_stages.append(stage_id)

    ok = len(bound_stages) > 0
    if not ok:
        reason = (
            "目标时段无可绑定的真实转向流量"
            if not flow_agg
            else "相位阶段与真实转向流量无法匹配（检查信控映射/渠化 dir8）"
        )
    elif unbound_stages:
        reason = f"部分阶段缺少真实流量：{','.join(unbound_stages)}"
    else:
        reason = None

    signal["flow_binding"] = {
        "ok": ok,
        "period": period,
        "bound_stages": bound_stages,
        "unbound_stages": unbound_stages,
        "total_flow_vph": int(round(total_flow)) if ok else None,
        "source": "pg_turn_flow" if ok else "none",
        "reason": reason,
    }
    return signal
