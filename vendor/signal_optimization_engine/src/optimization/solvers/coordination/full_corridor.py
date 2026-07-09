"""干线绿波协调求解器（完整版）.

实现计划中的六步流程：
1. 逐路口调用 single_point 得 C_i^* 与绿信比
2. 关键路口按供需均衡选出
3. 公共周期夹紧 → 关键路口可二次单点锁周期
4. 非关键路口绿时分配（非协调强度贴近目标 + 富余给协调）
5. 偏移优化（单向/双向/带双停抑制）
6. 组装输出

策略：oneway_forward / oneway_reverse / bidirectional / bidirectional_no_double_stop
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from scipy.optimize import minimize

from optimization.solvers.coordination.arterial_bandwidth import (
    ArterialLink,
    _modular_pen,
    _webster_approach_delay_s,
)
from optimization.solvers.single_intersection import generate_single_point_plan

# ---------------------------------------------------------------------------
# 数据类型
# ---------------------------------------------------------------------------

VALID_STRATEGIES = frozenset({
    "oneway_forward",
    "oneway_reverse",
    "bidirectional",
    "bidirectional_no_double_stop",
})


# ---------------------------------------------------------------------------
# 1) 逐路口单点优化
# ---------------------------------------------------------------------------

def _run_single_point_per_intersection(
    intersections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """对每个路口调用 generate_single_point_plan，返回每路口的单点结果."""
    results: list[dict[str, Any]] = []
    for ix_data in intersections:
        req = _build_single_point_request(ix_data)
        plan = generate_single_point_plan(req)
        results.append(plan)
    return results


def _build_single_point_request(ix_data: dict[str, Any]) -> dict[str, Any]:
    """从走廊输入的 per-intersection 数据构造单点请求."""
    req: dict[str, Any] = {}
    req["interId"] = ix_data.get("intersection_id", ix_data.get("id", ""))
    if "phasePlanOfTimeList" in ix_data:
        req["phasePlanOfTimeList"] = ix_data["phasePlanOfTimeList"]
    elif "phaseStageInfoList" in ix_data:
        req["phasePlanOfTimeList"] = [
            {
                "interId": req["interId"],
                "phasePlanId": f"{req['interId']}-PLAN",
                "phasePlanName": "走廊内嵌方案",
                "startTime": "00:00",
                "endTime": "24:00",
                "phaseStageInfoList": ix_data["phaseStageInfoList"],
            }
        ]
    if "constraints" in ix_data:
        req["constraints"] = ix_data["constraints"]
    if "obj_intensity" in ix_data:
        req["obj_intensity"] = ix_data["obj_intensity"]
    return req


def _movement_key_from_dir_info(item: dict[str, Any]) -> str:
    movement_key = item.get("movementKey")
    if movement_key:
        return str(movement_key)
    dir8 = item.get("dir8No")
    turn = item.get("turnDirNo")
    return f"{dir8}_{turn}"


def _build_phase_stage_snapshot(
    phase_stage_timing_list: list[dict[str, Any]],
    *,
    cycle_s: float,
) -> list[dict[str, Any]]:
    snapshot: list[dict[str, Any]] = []
    for stage in phase_stage_timing_list:
        green_s = float(stage.get("greenTime", stage.get("green_s", 0.0)))
        green_ratio = stage.get("splitRatio", stage.get("green_ratio"))
        if green_ratio is None:
            green_ratio = green_s / cycle_s if cycle_s > 0 else 0.0
        snapshot.append(
            {
                "phase_stage_id": stage.get("phaseStageId", stage.get("phase_stage_id", "")),
                "phase_stage_name": stage.get("phaseStageName", stage.get("phase_stage_name", "")),
                "green_s": round(green_s, 1),
                "green_ratio": round(float(green_ratio), 4),
                "phase_saturation": round(float(stage.get("phaseSaturation", stage.get("phase_saturation", 0.0))), 4),
                "phase_dir_info_list": stage.get("phaseDirInfoDTOList", stage.get("phase_dir_info_list", [])),
            }
        )
    return snapshot


def _snapshot_from_single_point(sp_result: dict[str, Any], *, source: str) -> dict[str, Any]:
    cycle_s = float(sp_result.get("cycleTime", 0.0))
    stages = sp_result.get("phaseStageTimingList") or sp_result.get("data") or []
    meta = sp_result.get("meta", {}) if isinstance(sp_result.get("meta"), dict) else {}
    return {
        "source": source,
        "cycle_s": cycle_s,
        "phase_stage_timing_list": _build_phase_stage_snapshot(stages, cycle_s=cycle_s),
        "direction_intensity_list": meta.get("direction_intensity_list", []),
    }


def _estimate_second_pass_snapshot(
    sp_result: dict[str, Any],
    alloc: dict[str, Any],
    *,
    public_cycle: float,
    source: str,
) -> dict[str, Any]:
    first_cycle = max(float(sp_result.get("cycleTime", public_cycle)), 1.0)
    stages = sp_result.get("phaseStageTimingList") or sp_result.get("data") or []
    first_meta = sp_result.get("meta", {}) if isinstance(sp_result.get("meta"), dict) else {}
    first_dir_list = first_meta.get("direction_intensity_list", [])
    first_dir_map = {
        str(item.get("movementKey")): item
        for item in first_dir_list
        if item.get("movementKey") is not None
    }
    new_green_map = {
        str(stage.get("phase_stage_id", "")): float(stage.get("green_s", 0.0))
        for stage in alloc.get("phase_stage_timing", [])
    }

    direction_intensity_list: list[dict[str, Any]] = []
    phase_stage_timing_list: list[dict[str, Any]] = []
    stage_intensity_map: dict[str, float] = {}

    for stage in stages:
        stage_id = str(stage.get("phaseStageId", ""))
        stage_name = stage.get("phaseStageName", stage_id)
        old_green = max(float(stage.get("greenTime", 0.0)), 1.0)
        new_green = max(new_green_map.get(stage_id, old_green), 1.0)
        phase_dir_info_list = stage.get("phaseDirInfoDTOList", [])
        movement_intensities: list[float] = []
        for movement in phase_dir_info_list:
            movement_key = _movement_key_from_dir_info(movement)
            first_item = first_dir_map.get(movement_key, {})
            first_intensity = float(first_item.get("intensity", stage.get("phaseSaturation", 0.0)))
            est_intensity = first_intensity * (public_cycle / first_cycle) * (old_green / new_green)
            label = movement.get("label") or first_item.get("label") or movement_key
            direction_intensity_list.append(
                {
                    "movementKey": movement_key,
                    "label": label,
                    "dir8No": movement.get("dir8No"),
                    "turnDirNo": movement.get("turnDirNo"),
                    "intensity": round(est_intensity, 4),
                    "phase_stage_id": stage_id,
                }
            )
            movement_intensities.append(est_intensity)

        stage_sat = max(movement_intensities) if movement_intensities else 0.0
        stage_intensity_map[stage_id] = stage_sat
        phase_stage_timing_list.append(
            {
                "phase_stage_id": stage_id,
                "phase_stage_name": stage_name,
                "green_s": round(new_green, 1),
                "green_ratio": round(new_green / public_cycle, 4) if public_cycle > 0 else 0.0,
                "phase_saturation": round(stage_sat, 4),
                "phase_dir_info_list": phase_dir_info_list,
            }
        )

    return {
        "source": source,
        "cycle_s": float(public_cycle),
        "phase_stage_timing_list": phase_stage_timing_list,
        "direction_intensity_list": direction_intensity_list,
    }


# ---------------------------------------------------------------------------
# 2) 关键路口判别（各方向供需均衡最优）
# ---------------------------------------------------------------------------

def _compute_balance_score(sp_result: dict[str, Any]) -> float:
    """从单点输出中计算供需均衡度（越小越均衡）.

    使用各阶段 phaseSaturation 的极差作为度量。
    """
    stages = sp_result.get("phaseStageTimingList") or sp_result.get("data") or []
    sats = [float(s.get("phaseSaturation", 0.0)) for s in stages if isinstance(s, dict)]
    if len(sats) < 2:
        return 0.0
    return max(sats) - min(sats)


def _select_critical_intersection(
    sp_results: list[dict[str, Any]],
    intersection_ids: list[str],
) -> tuple[int, str, float]:
    """返回 (关键路口索引, 关键路口 ID, 均衡度分数)."""
    if not sp_results:
        return 0, intersection_ids[0] if intersection_ids else "", 0.0

    scores = [_compute_balance_score(r) for r in sp_results]
    best_idx = 0
    best_score = scores[0]
    for i, s in enumerate(scores):
        if s < best_score:
            best_score = s
            best_idx = i
        elif abs(s - best_score) < 1e-6:
            c_i = int(sp_results[i].get("cycleTime", 0))
            c_best = int(sp_results[best_idx].get("cycleTime", 0))
            if c_i > c_best:
                best_idx = i
                best_score = s

    iid = intersection_ids[best_idx] if best_idx < len(intersection_ids) else ""
    return best_idx, iid, best_score


# ---------------------------------------------------------------------------
# 3) 公共周期夹紧 + 可选关键路口二次单点
# ---------------------------------------------------------------------------

def _clamp_cycle(
    critical_cycle: float,
    min_cycle_s: float,
    max_cycle_s: float,
    per_intersection_limits: list[tuple[float, float]] | None = None,
) -> float:
    lo, hi = min_cycle_s, max_cycle_s
    if per_intersection_limits:
        for ix_lo, ix_hi in per_intersection_limits:
            lo = max(lo, ix_lo)
            hi = min(hi, ix_hi)
    if lo > hi:
        lo = hi = critical_cycle
    return float(np.clip(critical_cycle, lo, hi))


def _rerun_single_point_locked_cycle(
    ix_data: dict[str, Any],
    locked_cycle: float,
) -> dict[str, Any]:
    """以锁定周期重新调用单点优化."""
    req = _build_single_point_request(ix_data)
    c = req.get("constraints", {})
    c = dict(c)
    c["max_cycle_s"] = int(locked_cycle)
    c["default_cycle_s"] = int(locked_cycle)
    req["constraints"] = c
    return generate_single_point_plan(req)


# ---------------------------------------------------------------------------
# 4) 非关键路口绿时分配
# ---------------------------------------------------------------------------

def _allocate_non_critical_greens(
    sp_result: dict[str, Any],
    public_cycle: float,
    coord_phase_id: str | None,
    target_non_coord_intensity: float = 0.8,
) -> dict[str, Any]:
    """在公共周期下，非协调相位供需强度贴近目标，富余给协调相位.

    返回 {phase_id: green_s, ...} 与 coordinated_green_s。
    """
    stages = sp_result.get("phaseStageTimingList") or sp_result.get("data") or []
    if not stages:
        return {"greens": {}, "coordinated_green_s": 0.0, "phase_stage_timing": []}

    orig_cycle = max(1, int(sp_result.get("cycleTime", public_cycle)))
    n_stages = len(stages)
    loss_per_stage = 5.0
    total_loss = loss_per_stage * n_stages
    available = max(0.0, public_cycle - total_loss)

    greens: dict[str, float] = {}
    non_coord_total = 0.0

    for s in stages:
        pid = s.get("phaseStageId", "")
        orig_green = float(s.get("greenTime", 20))
        orig_ratio = float(s.get("splitRatio", orig_green / orig_cycle if orig_cycle else 0.25))

        if pid == coord_phase_id:
            continue

        sat = float(s.get("phaseSaturation", 0.5))
        if sat < 1e-6:
            sat = 0.5
        desired_green = orig_ratio * public_cycle
        if sat > 0 and target_non_coord_intensity > 0:
            scaling = target_non_coord_intensity / max(sat, 0.01)
            desired_green = orig_green * scaling
        desired_green = max(desired_green, 12.0)
        desired_green = min(desired_green, available * 0.8)
        greens[pid] = desired_green
        non_coord_total += desired_green

    coord_green = max(12.0, available - non_coord_total)
    if coord_phase_id:
        greens[coord_phase_id] = coord_green

    total_green = sum(greens.values())
    if total_green > available and total_green > 0:
        factor = available / total_green
        for k in greens:
            greens[k] = max(12.0, greens[k] * factor)
        coord_green = greens.get(coord_phase_id, coord_green) if coord_phase_id else coord_green

    phase_stage_timing = []
    for s in stages:
        pid = s.get("phaseStageId", "")
        g = greens.get(pid, float(s.get("greenTime", 20)))
        phase_stage_timing.append({
            "phase_stage_id": pid,
            "phase_stage_name": s.get("phaseStageName", pid),
            "green_s": round(g, 1),
            "green_ratio": round(g / public_cycle, 4) if public_cycle > 0 else 0.0,
        })

    return {
        "greens": greens,
        "coordinated_green_s": round(coord_green, 1),
        "phase_stage_timing": phase_stage_timing,
    }


# ---------------------------------------------------------------------------
# 5) 偏移优化
# ---------------------------------------------------------------------------

def _compute_oneway_bandwidth(
    offsets: np.ndarray,
    greens: np.ndarray,
    travel_times: np.ndarray,
    cycle: float,
) -> float:
    """计算单向带宽：沿行程时间链的绿灯窗口模周期交集宽度."""
    n = len(offsets)
    if n < 2:
        return float(greens[0]) if n == 1 else 0.0

    bw = float(greens[0])
    for i in range(n - 1):
        arrival = offsets[i] + travel_times[i]
        arrival_mod = arrival % cycle
        start_next = offsets[i + 1] % cycle

        overlap = _green_overlap(arrival_mod, arrival_mod + bw, start_next, greens[i + 1], cycle)
        bw = min(bw, overlap)
        if bw <= 0:
            return 0.0
    return bw


def _green_overlap(arr_start: float, arr_end: float, green_start: float, green_dur: float, cycle: float) -> float:
    """两个窗口在模周期上的重叠长度."""
    def normalize(t: float) -> float:
        return t % cycle

    best = 0.0
    for k in range(-1, 2):
        gs = normalize(green_start) + k * cycle
        ge = gs + green_dur
        a = normalize(arr_start)
        for j in range(-1, 2):
            a_s = a + j * cycle
            a_e = a_s + (arr_end - arr_start)
            ov = max(0.0, min(ge, a_e) - max(gs, a_s))
            best = max(best, ov)
    return best


def _count_double_stops(
    offsets: np.ndarray,
    greens: np.ndarray,
    travel_times_fwd: np.ndarray,
    cycle: float,
    samples: int = 36,
) -> float:
    """统计正向名义轨迹在周期内采样点处的相邻双停事件数."""
    n = len(offsets)
    if n < 2:
        return 0.0
    count = 0.0
    for s in range(samples):
        t0 = cycle * s / samples
        stopped_prev = False
        for i in range(n):
            arrival = t0 + sum(travel_times_fwd[:i]) if i > 0 else t0
            arr_mod = arrival % cycle
            off_mod = offsets[i] % cycle
            end_mod = (offsets[i] + greens[i]) % cycle
            if end_mod > off_mod:
                in_green = off_mod <= arr_mod < end_mod
            else:
                in_green = arr_mod >= off_mod or arr_mod < end_mod
            stopped = not in_green
            if stopped and stopped_prev and i > 0:
                count += 1.0
            stopped_prev = stopped
    return count / samples


def solve_offsets(
    n: int,
    greens: np.ndarray,
    cycle: float,
    tau_f: np.ndarray,
    tau_b: np.ndarray,
    strategy: str = "bidirectional",
    progression_weight: float = 0.08,
    double_stop_weight: float = 0.5,
) -> np.ndarray:
    """在固定 C、g 下优化偏移 θ_1..θ_{n-1}（θ_0=0）."""
    if n <= 1:
        return np.zeros(1)

    def objective(f_inner: np.ndarray) -> float:
        offsets = np.zeros(n)
        offsets[1:] = np.clip(f_inner, 0, 1 - 1e-9) * cycle

        bw_fwd = _compute_oneway_bandwidth(offsets, greens, tau_f, cycle)
        bw_rev = _compute_oneway_bandwidth(offsets[::-1], greens[::-1], tau_b[::-1], cycle)

        pen = 0.0
        for i in range(n - 1):
            d_f = offsets[i + 1] - offsets[i] - tau_f[i]
            pen += _modular_pen(d_f, cycle)
            d_b = offsets[i] - offsets[i + 1] - tau_b[i]
            pen += _modular_pen(d_b, cycle)

        if strategy == "oneway_forward":
            obj = -bw_fwd + progression_weight * pen * 0.1
        elif strategy == "oneway_reverse":
            obj = -bw_rev + progression_weight * pen * 0.1
        elif strategy == "bidirectional_no_double_stop":
            ds = _count_double_stops(offsets, greens, tau_f, cycle)
            obj = -(bw_fwd + bw_rev) / 2.0 + progression_weight * pen + double_stop_weight * ds
        else:  # bidirectional
            obj = -(bw_fwd + bw_rev) / 2.0 + progression_weight * pen

        return obj

    rng = np.random.default_rng(42)
    best_x = np.linspace(0.0, 0.5, n - 1)
    best_obj = objective(best_x)
    bounds = [(0.0, 1.0 - 1e-9)] * (n - 1)

    for trial in range(8):
        if trial == 0:
            x0 = np.linspace(0.0, 0.5, n - 1)
        elif trial == 1:
            x0 = np.array([tau_f[i] / cycle % 1.0 for i in range(n - 1)])
        else:
            x0 = rng.uniform(0, 1, n - 1)

        res = minimize(objective, x0, method="SLSQP", bounds=bounds,
                       options={"maxiter": 300, "ftol": 1e-7})
        if res.fun < best_obj:
            best_obj = res.fun
            best_x = res.x.copy()

    offsets = np.zeros(n)
    offsets[1:] = np.clip(best_x, 0, 1 - 1e-9) * cycle
    return offsets


# ---------------------------------------------------------------------------
# 6) 主入口
# ---------------------------------------------------------------------------

def solve_corridor_full(
    intersection_ids: list[str],
    intersections: list[dict[str, Any]],
    links: Sequence[ArterialLink],
    *,
    min_cycle_s: float = 60.0,
    max_cycle_s: float = 120.0,
    strategy: str = "bidirectional",
    target_non_coord_intensity: float = 0.8,
    coord_phase_ids: list[str | None] | None = None,
    progression_weight: float = 0.08,
    double_stop_weight: float = 0.5,
) -> dict[str, Any]:
    """完整干线协调求解.

    Parameters
    ----------
    intersection_ids : 有序路口 ID
    intersections : 每路口数据（含 phasePlanOfTimeList 或 phaseStageInfoList 等）
    links : ArterialLink 序列
    strategy : 协调策略
    coord_phase_ids : 每路口主协调相位 ID（可选，None 自动取第一阶段）
    """
    n = len(intersection_ids)
    if n == 0:
        return {"ok": False, "error": "intersection_ids 为空", "nodes": [], "kpis": {}}

    if strategy not in VALID_STRATEGIES:
        strategy = "bidirectional"

    # --- Step 1: 逐路口单点优化 ---
    if intersections and any("phasePlanOfTimeList" in ix or "phaseStageInfoList" in ix for ix in intersections):
        first_pass_results = _run_single_point_per_intersection(intersections)
    else:
        first_pass_results = [{"cycleTime": 90, "phaseStageTimingList": [], "data": [], "meta": {}}] * n
    effective_sp_results = list(first_pass_results)

    # --- Step 2: 关键路口判别 ---
    critical_idx, critical_id, balance_score = _select_critical_intersection(first_pass_results, intersection_ids)
    critical_cycle = float(first_pass_results[critical_idx].get("cycleTime", 90))

    # --- Step 3: 公共周期夹紧 ---
    public_cycle = _clamp_cycle(critical_cycle, min_cycle_s, max_cycle_s)

    if abs(public_cycle - critical_cycle) > 0.5 and intersections and critical_idx < len(intersections):
        effective_sp_results[critical_idx] = _rerun_single_point_locked_cycle(
            intersections[critical_idx], public_cycle
        )

    # --- Step 4: 非关键路口绿时分配 ---
    coord_pids: list[str | None] = list(coord_phase_ids) if coord_phase_ids else [None] * n
    while len(coord_pids) < n:
        coord_pids.append(None)

    per_node_timing: list[dict[str, Any]] = []
    coordinated_greens = np.zeros(n)

    for i in range(n):
        sp = effective_sp_results[i] if i < len(effective_sp_results) else {}
        stages = sp.get("phaseStageTimingList") or sp.get("data") or []
        cpid = coord_pids[i]
        if cpid is None and stages:
            cpid = stages[0].get("phaseStageId", "A")
            coord_pids[i] = cpid

        alloc = _allocate_non_critical_greens(sp, public_cycle, cpid, target_non_coord_intensity)
        coordinated_greens[i] = alloc["coordinated_green_s"]
        per_node_timing.append(alloc)

    coordinated_greens = np.clip(coordinated_greens, 12.0, public_cycle - 10.0)

    # --- Step 5: 偏移优化 ---
    if n >= 2 and len(links) == n - 1:
        tau_f = np.array([lk.forward_travel_s() for lk in links])
        tau_b = np.array([lk.reverse_travel_s() for lk in links])
        offsets = solve_offsets(
            n, coordinated_greens, public_cycle, tau_f, tau_b,
            strategy=strategy,
            progression_weight=progression_weight,
            double_stop_weight=double_stop_weight,
        )
        bw_fwd = _compute_oneway_bandwidth(offsets, coordinated_greens, tau_f, public_cycle)
        bw_rev = _compute_oneway_bandwidth(offsets[::-1], coordinated_greens[::-1], tau_b[::-1], public_cycle)
        ds_count = _count_double_stops(offsets, coordinated_greens, tau_f, public_cycle)
    else:
        offsets = np.zeros(n)
        tau_f = np.array([])
        tau_b = np.array([])
        bw_fwd = float(coordinated_greens[0]) if n > 0 else 0.0
        bw_rev = bw_fwd
        ds_count = 0.0

    # --- Step 6: 组装输出 ---
    nodes = []
    total_delay = 0.0
    for i in range(n):
        first_pass = _snapshot_from_single_point(
            first_pass_results[i] if i < len(first_pass_results) else {},
            source="single_point_initial",
        )
        if i == critical_idx:
            if abs(public_cycle - critical_cycle) > 0.5:
                second_pass = _snapshot_from_single_point(
                    effective_sp_results[i],
                    source="single_point_locked_cycle",
                )
            else:
                second_pass = _snapshot_from_single_point(
                    effective_sp_results[i],
                    source="single_point_initial_reused",
                )
        else:
            second_pass = _estimate_second_pass_snapshot(
                effective_sp_results[i] if i < len(effective_sp_results) else {},
                per_node_timing[i],
                public_cycle=public_cycle,
                source="corridor_green_reallocation",
            )
        x_i = 0.5
        d_i = _webster_approach_delay_s(public_cycle, float(coordinated_greens[i]), x_i)
        total_delay += d_i
        node: dict[str, Any] = {
            "intersection_id": intersection_ids[i],
            "cycle_s": public_cycle,
            "offset_s": round(float(offsets[i]), 2),
            "main_coordination_offset_s": round(float(offsets[i]), 2),
            "main_coordination_phase_id": coord_pids[i] or "",
            "coordinated_green_s": round(float(coordinated_greens[i]), 1),
            "green_ratio": round(float(coordinated_greens[i]) / public_cycle, 4) if public_cycle > 0 else 0.0,
            "webster_delay_s": round(d_i, 2),
            "phase_stage_timing_list": per_node_timing[i].get("phase_stage_timing", []),
            "first_optimization": first_pass,
            "second_optimization": second_pass,
        }
        nodes.append(node)

    bandwidth = min(bw_fwd, bw_rev) if strategy.startswith("bidirectional") else max(bw_fwd, bw_rev)

    return {
        "ok": True,
        "cycle_s": public_cycle,
        "strategy": strategy,
        "bandwidth_s": round(bandwidth, 2),
        "bandwidth_forward_s": round(bw_fwd, 2),
        "bandwidth_reverse_s": round(bw_rev, 2),
        "total_delay_s": round(total_delay, 2),
        "nodes": nodes,
        "kpis": {
            "bandwidth_s": round(bandwidth, 2),
            "bandwidth_forward_s": round(bw_fwd, 2),
            "bandwidth_reverse_s": round(bw_rev, 2),
            "total_webster_delay_s": round(total_delay, 2),
            "adjacent_double_stop_proxy": round(ds_count, 3),
        },
        "meta": {
            "solver": "corridor_full_solver",
            "strategy": strategy,
            "critical_intersection_id": critical_id,
            "critical_balance_score": round(balance_score, 4),
            "bandwidth_definition": "computed_overlap",
        },
    }
