"""单路口优化方案生成算法.

规范化输入：
    - interId
    - phasePlanOfTimeList / parameter_json_str
    - phaseStageInfoList
    - phaseDirInfoDTOList
    - dir8No / turnDirNo
    - turnFlowTotal / laneCount / criticalLaneFlow

规范化输出：
    - isError / data / error
    - planType / intersectionId / cycleTime
    - phasePlanId / phasePlanName
    - phaseStageTimingList / meta

算法说明（v0.8.0）
------------------
求解器采用 SciPy SLSQP 文档模型。
无可识别放行流向的空阶段不参与绿灯再分配，按现状方案绿灯时长锁定
（min_green = max_green = 现状绿）并计入周期，避免优化结果丢失该段服务时间。
目标基于转向车道级供需强度 I_dir 与目标强度 I_obj 的综合偏差最小化：
    min Σ_dir[(1+(I_dir/I_obj)^3)·abs(I_dir−I_obj)] + λ·std(I_dir) + μ·Σ_dir max(0, (I_dir−I_obj)^3)
        + J_keep(g)

v0.8.0 新增搭接保形惩罚项 J_keep（详见 _detect_overlap_structure 与
_build_overlap_keep_objective）：对存在跨阶段放行（搭接/迟启/早断）的方案，
以现状方案的搭接深度比与搭接组内阶段绿信比为参照，偏差超出容差带后按
二次惩罚计入目标。该项同时消除切片阶段间绿灯分配的解简并（相邻切片阶段
机动车流向集合相同时，原目标对切片间分配不敏感，解会随机漂移）。
行人过街流（pedDirList）不参与流量目标，但参与搭接结构识别。

其中：
    - dir8No 按 8 方向顺时针编号：北=0，东北=1，东=2，东南=3，南=4，西南=5，西=6，西北=7
    - turnDirNo：掉头=0，左转=1，直行=2，右转=3
    - 转向流量优先使用 criticalLaneFlow；否则用 turnFlowTotal / laneCount 折算为车道级流量
"""

from __future__ import annotations

import json
import sys
from math import ceil, floor
from typing import Any

from optimization.solvers.plan_metadata import empty_plan_meta
from preprocessing.timing.dir8_encoding import DIR8_LABELS
from preprocessing.timing.stage_min_green import (
    DEFAULT_MOTOR_MIN_GREEN_S,
    HISTORY_GREEN_STABILITY_FLOOR_RATIO,
    apply_history_green_stability_floor,
)
from preprocessing.timing.overlap_structure import (
    detect_overlap_structure,
    structure_stage_nos_to_indices,
)


DEFAULT_SINGLE_POINT_CONFIG: dict[str, float | int | bool] = {
    "default_cycle_s": 120,
    "target_saturation": 0.8,
    "target_saturation_min": 0.5,
    "target_saturation_max": 0.98,
    # 最大周期基准值：实际生效值 = max(本路口历史方案最大周期, 该基准/约束值)
    "max_cycle_s": 190,
    # 最小绿无全局参数：按各阶段 min_green_s 执行，缺省见 _stage_min_green_s
    # 启动绿损，不包含黄灯；黄灯/全红单独计入周期插入间隔。
    "green_loss_s": 2,
    "saturation_flow_vph": 1500.0,
    "yellow_s": 0,
    "all_red_s": 0,
    "intensity_std_penalty_weight": 10.0,
    "over_target_penalty_weight": 20.0,
    "solver_multi_start_count": 20,
    "solver_random_seed": 42,
    "solver_max_iterations": 600,
    "solver_ftol": 1e-9,
    "debug_objective_terms": False,
    # ── 搭接保形（v0.8.0）──────────────────────────────────────
    # 跨阶段流向的搭接深度比偏差惩罚权重（0 关闭）
    "overlap_depth_keep_weight": 5.0,
    # 搭接组内阶段绿信比偏差惩罚权重（0 关闭）
    "split_ratio_keep_weight": 5.0,
    # 容差带：参照值的相对比例，带内零惩罚（另有绝对下限 0.02 防小值噪声）
    "keep_tolerance_rel": 0.15,
    # 搭接切片阶段绿灯硬下限 = max(min_green, 该比例 × 现状绿)，0 关闭
    "overlap_slice_min_green_ratio": 0.6,
}

ALGORITHM_VERSION = "0.8.0"
SHORT_OVERLAP_SLICE_MAX_HISTORY_GREEN_S = DEFAULT_MOTOR_MIN_GREEN_S
LONG_OVERLAP_SLICE_MIN_GREEN_RATIO = HISTORY_GREEN_STABILITY_FLOOR_RATIO
DEFAULT_PHASE_PLAN_NAME = "单路口优化默认相位方案"
NORMAL_STAGE_MAX_GREEN_HISTORY_FACTOR = 1.3
TURN_DIR_LABELS = {
    0: "掉头",
    1: "左转",
    2: "直行",
    3: "右转",
}
_CLEARANCE_TURN_DIRS = {1, 2}


def generate_single_point_plan(request: dict[str, Any]) -> dict[str, Any]:
    """生成单路口配时/相位优化方案."""
    constraints = _as_dict(request.get("constraints"))
    strategy_instruction = _as_dict(request.get("strategy_instruction"))
    parameter_payload = _extract_parameter_payload(request)
    obj_intensity = _to_float(request.get("obj_intensity"))
    if obj_intensity is not None and "target_saturation" not in strategy_instruction:
        strategy_instruction = {**strategy_instruction, "target_saturation": obj_intensity}

    history_max_cycle_s = _history_max_cycle_s(request, parameter_payload)
    config = _build_config(
        constraints,
        strategy_instruction,
        history_max_cycle_s=history_max_cycle_s,
    )
    stage_defs, stage_context = _normalize_stages(request, config, parameter_payload)
    inter_id = _resolve_inter_id(request, parameter_payload, stage_context)

    if not stage_defs:
        default_cycle_time = int(config["default_cycle_s"])
        empty_stage_outputs: list[dict[str, Any]] = []
        return {
            "isError": False,
            "data": empty_stage_outputs,
            "error": None,
            "planType": "single_point",
            "intersectionId": inter_id or "UNKNOWN",
            "cycleTime": default_cycle_time,
            "phasePlanId": stage_context.get("phasePlanId"),
            "phasePlanName": stage_context.get("phasePlanName", DEFAULT_PHASE_PLAN_NAME),
            "phaseStageTimingList": empty_stage_outputs,
            "meta": empty_plan_meta("single_point_optimizer", ALGORITHM_VERSION)
            | {
                "notes": [
                    "未提供可识别的相位阶段输入，返回默认周期占位方案。",
                    "请求体需包含 phasePlanOfTimeList 或 parameter_json_str。",
                ],
            },
        }

    solution = _solve_stage_timing(stage_defs, config)
    notes = list(solution["notes"])
    if "min_green_s" in constraints or "ped_min_s" in constraints:
        notes.append(
            "全局最小绿参数已取消，constraints.min_green_s 不再生效："
            f"最小绿按各阶段 min_green_s 执行，缺省机动车最小绿 {DEFAULT_MOTOR_MIN_GREEN_S}s"
            "（现状放行更短时取现状值）。"
        )
    if any(stage["used_virtual_flow"] for stage in stage_defs):
        notes.append("已对零流量阶段注入最小绿对应的虚拟流量，避免优化结果丢失服务。")
    fixed_stage_names = [stage["stage_name"] for stage in stage_defs if stage.get("fixed_green")]
    if fixed_stage_names:
        notes.append(
            "以下阶段无可识别放行流向，已按现状方案绿灯时长锁定参与周期计算："
            + "、".join(fixed_stage_names)
            + "。"
        )
    if solution["max_stage_saturation"] > config["target_saturation"]:
        notes.append("存在阶段饱和度高于目标值，建议复核流量或放宽周期上限。")

    max_cycle_s = int(config["max_cycle_s"])
    stage_outputs = [
        {
            "phaseStageId": stage["stage_id"],
            "phaseStageName": stage["stage_name"],
            "splitTime": solution["cycle_s"],
            "greenTime": solution["greens"][idx],
            "yellowTime": stage["yellow_s"],
            "redTime": max(solution["cycle_s"] - solution["greens"][idx] - stage["yellow_s"], 0),
            "allRedTime": stage["all_red_s"],
            "splitRatio": round(solution["greens"][idx] / solution["cycle_s"], 4),
            "phaseSaturation": round(solution["stage_saturation"][idx], 4),
            # 求解实际使用的绿灯上下限（max_green 缺省时回退为最大周期，与求解器一致）
            "minGreenTime": int(stage["min_green_s"]),
            "maxGreenTime": int(stage["max_green_s"]) if stage["max_green_s"] is not None else max_cycle_s,
            # 阶段流量：关键车道级流量（求解输入）与该阶段各转向总流量之和
            "stageCriticalFlowVph": round(stage["flow_vph"], 1),
            "stageTurnFlowTotalVph": round(stage["turn_flow_total_vph"], 1),
            "phaseDirInfoDTOList": stage["stage_dir_info_list"],
            # 空阶段：绿灯按现状方案时长锁定，未参与优化再分配
            "greenTimeFixed": bool(stage.get("fixed_green")),
        }
        for idx, stage in enumerate(stage_defs)
    ]

    # 路口转向总流量：同一转向跨阶段共享绿灯时只计一次（取最大值，与求解器口径一致）
    movement_flow_totals: dict[str, float] = {}
    for stage in stage_defs:
        for key, mdata in (stage.get("movement_flows") or {}).items():
            flow = float(mdata.get("turnFlowTotal") or 0.0)
            movement_flow_totals[key] = max(movement_flow_totals.get(key, 0.0), flow)
    total_turn_flow_vph = round(sum(movement_flow_totals.values()), 1)

    return {
        "isError": False,
        "data": stage_outputs,
        "error": None,
        "planType": "single_point",
        "intersectionId": inter_id or "UNKNOWN",
        "cycleTime": solution["cycle_s"],
        "phasePlanId": stage_context.get("phasePlanId"),
        "phasePlanName": stage_context.get("phasePlanName", DEFAULT_PHASE_PLAN_NAME),
        "phaseStageTimingList": stage_outputs,
        "meta": empty_plan_meta("single_point_optimizer", ALGORITHM_VERSION)
        | {
            "solver_preference": "scipy_slsqp_document_model",
            "solver_preference_met": solution.get("solver_family") == "scipy",
            "solver": solution["solver"],
            "solver_family": solution["solver_family"],
            "target_saturation": config["target_saturation"],
            "max_cycle_s": int(config["max_cycle_s"]),
            "min_cycle_s": solution.get("min_cycle_s"),
            "history_max_cycle_s": int(history_max_cycle_s),
            "default_stage_min_green_s": int(DEFAULT_MOTOR_MIN_GREEN_S),
            "saturation_flow_vph": float(config["saturation_flow_vph"]),
            "total_turn_flow_vph": total_turn_flow_vph,
            "lost_time_total_s": solution["lost_time_total_s"],
            "effective_green_total_s": solution["effective_green_total_s"],
            "max_phase_saturation": round(solution["max_stage_saturation"], 4),
            "notes": notes,
            "direction_intensity_list": solution["direction_intensity_list"],
            "overlap_keep_report": solution.get("overlap_keep_report"),
        },
    }


def solve_single_point_timing(request: dict[str, Any]) -> dict[str, Any]:
    """对外保留的直接调用接口，返回与 MCP/HTTP 一致的配时方案."""
    return generate_single_point_plan(request)


def _continuous_stage_loss(stage_indices: list[int], loss_stage: list[float]) -> float:
    """按连续放行块累计启动绿损；相邻阶段连续放行同一转向时只扣一次."""
    if not stage_indices:
        return 0.0
    total = 0.0
    block_max_loss = 0.0
    previous_idx: int | None = None
    for idx in sorted(set(stage_indices)):
        loss = loss_stage[idx] if 0 <= idx < len(loss_stage) else 0.0
        if previous_idx is None or idx != previous_idx + 1:
            total += block_max_loss
            block_max_loss = loss
        else:
            block_max_loss = max(block_max_loss, loss)
        previous_idx = idx
    return total + block_max_loss


def _build_config(
    constraints: dict[str, Any],
    strategy_instruction: dict[str, Any],
    *,
    history_max_cycle_s: float = 0.0,
) -> dict[str, float | int | bool]:
    default_cycle_s = int(_first_number(
        constraints.get("default_cycle_s"),
        strategy_instruction.get("default_cycle_s"),
        DEFAULT_SINGLE_POINT_CONFIG["default_cycle_s"],
    ))
    target_saturation = _first_number(
        strategy_instruction.get("target_saturation"),
        constraints.get("target_saturation"),
        constraints.get("goal_saturation"),
        DEFAULT_SINGLE_POINT_CONFIG["target_saturation"],
    )
    target_saturation_min = _first_number(
        strategy_instruction.get("target_saturation_min"),
        constraints.get("target_saturation_min"),
        DEFAULT_SINGLE_POINT_CONFIG["target_saturation_min"],
    )
    target_saturation_max = _first_number(
        strategy_instruction.get("target_saturation_max"),
        constraints.get("target_saturation_max"),
        DEFAULT_SINGLE_POINT_CONFIG["target_saturation_max"],
    )
    # 最大周期 = max(本路口历史方案最大周期, 约束/默认基准值[默认 190])
    max_cycle_base_s = _first_number(
        constraints.get("max_cycle_s"),
        DEFAULT_SINGLE_POINT_CONFIG["max_cycle_s"],
    )
    max_cycle_s = int(max(max(0.0, history_max_cycle_s), max_cycle_base_s))
    phase_green_loss_s = int(_first_number(
        constraints.get("green_loss_s"),
        DEFAULT_SINGLE_POINT_CONFIG["green_loss_s"],
    ))
    saturation_flow_vph = float(_first_number(
        constraints.get("saturation_flow_vph"),
        DEFAULT_SINGLE_POINT_CONFIG["saturation_flow_vph"],
    ))
    yellow_s = int(_first_number(
        constraints.get("yellow_s"),
        DEFAULT_SINGLE_POINT_CONFIG["yellow_s"],
    ))
    all_red_s = int(_first_number(
        constraints.get("all_red_s"),
        DEFAULT_SINGLE_POINT_CONFIG["all_red_s"],
    ))
    intensity_std_penalty_weight = float(_first_number(
        strategy_instruction.get("intensity_std_penalty_weight"),
        constraints.get("intensity_std_penalty_weight"),
        constraints.get("std_penalty_weight"),
        DEFAULT_SINGLE_POINT_CONFIG["intensity_std_penalty_weight"],
    ))
    over_target_penalty_weight = float(_first_number(
        strategy_instruction.get("over_target_penalty_weight"),
        constraints.get("over_target_penalty_weight"),
        constraints.get("overflow_penalty_weight"),
        DEFAULT_SINGLE_POINT_CONFIG["over_target_penalty_weight"],
    ))
    solver_multi_start_count = int(_first_number(
        strategy_instruction.get("solver_multi_start_count"),
        constraints.get("solver_multi_start_count"),
        constraints.get("multi_start_count"),
        DEFAULT_SINGLE_POINT_CONFIG["solver_multi_start_count"],
    ))
    solver_random_seed = int(_first_number(
        strategy_instruction.get("solver_random_seed"),
        constraints.get("solver_random_seed"),
        constraints.get("random_seed"),
        DEFAULT_SINGLE_POINT_CONFIG["solver_random_seed"],
    ))
    solver_max_iterations = int(_first_number(
        strategy_instruction.get("solver_max_iterations"),
        constraints.get("solver_max_iterations"),
        constraints.get("solver_maxiter"),
        DEFAULT_SINGLE_POINT_CONFIG["solver_max_iterations"],
    ))
    solver_ftol = float(_first_number(
        strategy_instruction.get("solver_ftol"),
        constraints.get("solver_ftol"),
        constraints.get("optimizer_ftol"),
        DEFAULT_SINGLE_POINT_CONFIG["solver_ftol"],
    ))
    debug_objective_terms = _to_bool(
        strategy_instruction.get("debug_objective_terms"),
        constraints.get("debug_objective_terms"),
        DEFAULT_SINGLE_POINT_CONFIG["debug_objective_terms"],
    )
    overlap_depth_keep_weight = float(_first_number(
        strategy_instruction.get("overlap_depth_keep_weight"),
        constraints.get("overlap_depth_keep_weight"),
        DEFAULT_SINGLE_POINT_CONFIG["overlap_depth_keep_weight"],
    ))
    split_ratio_keep_weight = float(_first_number(
        strategy_instruction.get("split_ratio_keep_weight"),
        constraints.get("split_ratio_keep_weight"),
        DEFAULT_SINGLE_POINT_CONFIG["split_ratio_keep_weight"],
    ))
    keep_tolerance_rel = float(_first_number(
        strategy_instruction.get("keep_tolerance_rel"),
        constraints.get("keep_tolerance_rel"),
        DEFAULT_SINGLE_POINT_CONFIG["keep_tolerance_rel"],
    ))
    overlap_slice_min_green_ratio = float(_first_number(
        strategy_instruction.get("overlap_slice_min_green_ratio"),
        constraints.get("overlap_slice_min_green_ratio"),
        DEFAULT_SINGLE_POINT_CONFIG["overlap_slice_min_green_ratio"],
    ))
    safe_target_saturation_min = max(0.3, min(float(target_saturation_min), 0.98))
    safe_target_saturation_max = max(
        safe_target_saturation_min,
        min(float(target_saturation_max), 0.99),
    )
    return {
        "default_cycle_s": max(30, default_cycle_s),
        "target_saturation": max(
            safe_target_saturation_min,
            min(float(target_saturation), safe_target_saturation_max),
        ),
        "target_saturation_min": safe_target_saturation_min,
        "target_saturation_max": safe_target_saturation_max,
        "max_cycle_s": max(30, max_cycle_s),
        "green_loss_s": max(0, phase_green_loss_s),
        "saturation_flow_vph": max(1.0, saturation_flow_vph),
        "yellow_s": max(0, yellow_s),
        "all_red_s": max(0, all_red_s),
        "intensity_std_penalty_weight": max(0.0, intensity_std_penalty_weight),
        "over_target_penalty_weight": max(0.0, over_target_penalty_weight),
        "solver_multi_start_count": max(1, solver_multi_start_count),
        "solver_random_seed": solver_random_seed,
        "solver_max_iterations": max(1, solver_max_iterations),
        "solver_ftol": max(1e-12, solver_ftol),
        "debug_objective_terms": debug_objective_terms,
        "overlap_depth_keep_weight": max(0.0, overlap_depth_keep_weight),
        "split_ratio_keep_weight": max(0.0, split_ratio_keep_weight),
        "keep_tolerance_rel": min(max(0.0, keep_tolerance_rel), 1.0),
        "overlap_slice_min_green_ratio": min(max(0.0, overlap_slice_min_green_ratio), 1.0),
    }


def _normalize_stages(
    request: dict[str, Any],
    config: dict[str, float | int],
    parameter_payload: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_stage_defs, stage_context = _extract_raw_stages(request, parameter_payload or {})
    out: list[dict[str, Any]] = []
    max_cycle_s = int(config["max_cycle_s"])
    target_saturation = float(config["target_saturation"])

    for idx, raw in enumerate(raw_stage_defs, start=1):
        if not isinstance(raw, dict):
            continue
        stage_id = str(raw.get("phaseStageId") or f"P{idx}").strip() or f"P{idx}"
        stage_name = str(raw.get("phaseStageName") or stage_id).strip() or stage_id
        flow_vph = 0.0
        saturation_flow_vph = max(
            1.0,
            _first_number(raw.get("saturation_flow_vph"), config["saturation_flow_vph"]),
        )
        min_green_s = _stage_min_green_s(raw)
        max_green_val = _to_float(raw.get("max_green_s"))
        max_green_s = int(max_green_val) if max_green_val is not None else None
        timing = raw.get("currentTiming")
        timing = timing if isinstance(timing, dict) else {}
        yellow_s = int(max(0, _first_number(raw.get("yellow_s"), timing.get("yellowSec"), config["yellow_s"])))
        all_red_s = int(max(0, _first_number(raw.get("all_red_s"), timing.get("allRedSec"), config["all_red_s"])))
        green_loss_s = int(max(0, _first_number(raw.get("green_loss_s"), config["green_loss_s"])))
        history_green_s = _stage_current_green_s(raw)
        ped_dirs = _stage_ped_dirs(raw)
        stage_dir_info_list = _normalize_stage_dir_info_list(raw, saturation_flow_vph)
        if not stage_dir_info_list:
            # 空阶段（无可识别放行流向，如“空阶段N”/行人专用阶段）：
            # 不参与绿灯再分配，按现状方案时长锁定（min_green = max_green = 现状绿），
            # 周期与时序中保留该阶段，避免优化结果丢失该段服务时间。
            history_green_raw = _stage_history_green_s(raw)
            if history_green_raw is None:
                continue
            fixed_green_s = int(history_green_raw)
            out.append(
                {
                    "stage_id": stage_id,
                    "stage_no": _to_int(raw.get("stageNo") or raw.get("stage_no")),
                    "stage_name": stage_name,
                    "movements": [],
                    "movement_flows": {},
                    "stage_dir_info_list": [],
                    "flow_vph": 0.0,
                    "turn_flow_total_vph": 0.0,
                    "effective_flow_vph": 0.0,
                    "virtual_flow_vph": 0.0,
                    "used_virtual_flow": False,
                    "saturation_flow_vph": saturation_flow_vph,
                    "critical_ratio": 0.0,
                    "min_green_s": fixed_green_s,
                    "max_green_s": fixed_green_s,
                    "yellow_s": yellow_s,
                    "all_red_s": all_red_s,
                    "phase_yellow_s": yellow_s,
                    "phase_all_red_s": all_red_s,
                    "green_loss_s": green_loss_s,
                    "fixed_green": True,
                    "history_green_s": fixed_green_s,
                    "ped_dirs": ped_dirs,
                }
            )
            continue
        movements = [item["movementKey"] for item in stage_dir_info_list]
        flow_vph = max((item["laneLevelFlow"] for item in stage_dir_info_list), default=0.0)

        virtual_flow_vph = 0.0
        used_virtual_flow = False
        if flow_vph <= 0.0:
            virtual_flow_vph = saturation_flow_vph * min_green_s / max_cycle_s * target_saturation
            flow_for_solver = virtual_flow_vph
            used_virtual_flow = True
        else:
            flow_for_solver = flow_vph

        # movement_flows：内部统一后的逐转向车道级流量结构，供 SQP 求解使用。
        movement_flows: dict[str, Any] = {}
        turn_flow_total_vph = 0.0
        if stage_dir_info_list:
            for item in stage_dir_info_list:
                movement_flows[item["movementKey"]] = {
                    "flow_vph": item["laneLevelFlow"],
                    "saturation_flow_vph": item["saturationFlowVph"],
                    "lanes": item["laneCount"],
                    "dir8No": item["dir8No"],
                    "turnDirNo": item["turnDirNo"],
                    "turnFlowTotal": item["turnFlowTotal"],
                    "criticalLaneFlow": item["criticalLaneFlow"],
                    "laneLevelFlow": item["laneLevelFlow"],
                    "label": item["label"],
                    "signalAtom": item.get("signalAtom"),
                    "sourceKey": item.get("sourceKey"),
                    "vendorTag": item.get("vendorTag"),
                    "laneGroupIds": item.get("laneGroupIds") or [],
                    "laneNos": item.get("laneNos") or [],
                    "flowMapping": item.get("flowMapping"),
                }
                turn_flow_total_vph += item["turnFlowTotal"]
        out.append(
            {
                "stage_id": stage_id,
                "stage_no": _to_int(raw.get("stageNo") or raw.get("stage_no")),
                "stage_name": stage_name,
                "movements": movements,
                "movement_flows": movement_flows,
                "stage_dir_info_list": stage_dir_info_list,
                "flow_vph": flow_vph,
                "turn_flow_total_vph": turn_flow_total_vph,
                "effective_flow_vph": flow_for_solver,
                "virtual_flow_vph": virtual_flow_vph,
                "used_virtual_flow": used_virtual_flow,
                "saturation_flow_vph": saturation_flow_vph,
                "critical_ratio": flow_for_solver / saturation_flow_vph,
                "min_green_s": min_green_s,
                "max_green_s": max_green_s,
                "yellow_s": yellow_s,
                "all_red_s": all_red_s,
                "phase_yellow_s": yellow_s,
                "phase_all_red_s": all_red_s,
                "green_loss_s": green_loss_s,
                "history_green_s": history_green_s,
                "ped_dirs": ped_dirs,
            }
        )

    _apply_stage_clearance_by_continuity(out)
    cached_overlap = _cached_overlap_structure(stage_context, out)
    if cached_overlap is not None:
        for stage in out:
            stage["_cached_overlap_structure"] = cached_overlap
    return out, stage_context


def _apply_stage_clearance_by_continuity(stage_defs: list[dict[str, Any]]) -> None:
    """按左转/直行机动车流是否延续到下一阶段，派生阶段黄灯与全红时间."""
    movement_sets = [_stage_clearance_movement_keys(stage) for stage in stage_defs]
    for idx, stage in enumerate(stage_defs):
        current_movements = movement_sets[idx]
        if not current_movements:
            stage["yellow_s"] = 0
            stage["all_red_s"] = 0
            stage["clearanceDerivedReason"] = "无左转/直行机动车流，黄灯/全红按全局默认 0s"
            continue

        next_movements = movement_sets[idx + 1] if idx + 1 < len(stage_defs) else set()
        if current_movements & next_movements:
            stage["yellow_s"] = 0
            stage["all_red_s"] = 0
            stage["clearanceDerivedReason"] = "存在左转/直行机动车流延续到下一阶段，黄灯/全红取 0s"
            continue

        stage["yellow_s"] = _stage_min_clearance_s(stage, "yellow")
        stage["all_red_s"] = _stage_min_clearance_s(stage, "all_red")
        stage["clearanceDerivedReason"] = "左转/直行机动车流在本阶段结束，取对应相位黄灯/全红最小值"


def _stage_clearance_movement_keys(stage: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for item in stage.get("stage_dir_info_list") or []:
        if int(item.get("turnDirNo", -1)) not in _CLEARANCE_TURN_DIRS:
            continue
        movement_key = str(item.get("movementKey") or "").strip()
        if movement_key:
            keys.add(movement_key)
    return keys


def _stage_min_clearance_s(stage: dict[str, Any], kind: str) -> int:
    stage_key = "phase_yellow_s" if kind == "yellow" else "phase_all_red_s"
    item_keys = (
        ("yellowSec", "yellow_s", "yellowTime")
        if kind == "yellow"
        else ("allRedSec", "all_red_s", "allRedTime")
    )
    values: list[float] = []
    stage_default = _to_float(stage.get(stage_key))
    for item in stage.get("stage_dir_info_list") or []:
        if int(item.get("turnDirNo", -1)) not in _CLEARANCE_TURN_DIRS:
            continue
        item_value = None
        for item_key in item_keys:
            item_value = _to_float(item.get(item_key))
            if item_value is not None:
                break
        if item_value is None:
            item_value = stage_default
        if item_value is not None:
            values.append(max(0.0, item_value))
    if not values:
        values.append(max(0.0, stage_default or 0.0))
    return int(min(values))


def _stage_current_green_s(raw: dict[str, Any]) -> int | None:
    """读取阶段现状方案绿灯时长（s），无可用现状配时时返回 None."""
    history = _stage_history_green_s(raw)
    if history is None or history <= 0:
        return None
    return int(history)


def _stage_history_green_s(raw: dict[str, Any]) -> float | None:
    """读取阶段现状方案绿灯（s），含 0；无可用配时返回 None."""
    timing = raw.get("currentTiming")
    if isinstance(timing, dict):
        green = _to_non_negative_float(timing.get("greenSec"))
        if green is not None:
            return green
    green = _to_non_negative_float(raw.get("greenTime"))
    if green is not None:
        return green
    return None


def _stage_ped_dirs(raw: dict[str, Any]) -> list[int]:
    """读取阶段行人过街流方位（0 基 dir8No），无数据时返回空列表."""
    items = raw.get("pedDirList") or raw.get("ped_dir_list") or []
    if not isinstance(items, list):
        return []
    out: list[int] = []
    for item in items:
        value = _to_float(item)
        if value is None:
            continue
        dir8_no = int(value)
        if dir8_no in DIR8_LABELS and dir8_no not in out:
            out.append(dir8_no)
    return out


def _overlap_slice_effective_min_green_s(history_green: float) -> int:
    """搭接切片（推导最小绿为 0）在优化器中的有效下限.

    短搭接（现状绿灯 ≤ 机动车最小绿，如 3s 母弧脉冲）：保留现状值。
    长搭接：取现状绿的固定比例，允许压缩同时保持时序稳定性。
    """
    if history_green <= SHORT_OVERLAP_SLICE_MAX_HISTORY_GREEN_S:
        return int(history_green)
    return max(1, int(ceil(history_green * LONG_OVERLAP_SLICE_MIN_GREEN_RATIO)))


def _stage_min_green_s(raw: dict[str, Any]) -> int:
    """阶段最小绿（无全局参数，逐阶段确定）.

    优先级：
        1. greenBounds.minGreenS（交通流推导结果，含 0）；
        2. 阶段自带 min_green_s（库内方案配置）；
        3. 机动车最小绿默认值（14s）兜底；现状实际放行更短时取实际值
           （与 preprocessing.timing.stage_min_green 规则 4 一致，避免
           最小绿约束高于现状导致不可行或被动拉长周期）。

    搭接切片：推导最小绿为 0 且现状绿灯为 0 时允许 0；推导为 0 但现状
    仍有短绿灯（如 3s 搭接母弧）时取现状绿灯；长搭接（现状绿 > 14s）时
    取现状绿的 60%（向上取整），允许优化压缩。

    稳定性：原方案绿灯 > 30s 时，最终最小绿不低于原方案绿灯的 60%。

    防御：显式 min_green_s 低于机动车默认最小绿、且无 greenBounds
    （非交通流推导结果）时视为可疑脏数据（如信号机相位级 3s 最小绿
    被错误套到机动车阶段），与规则 4 兜底值取较大者。
    """
    green_bounds = raw.get("greenBounds")
    derived = isinstance(green_bounds, dict)
    timing = raw.get("currentTiming") if isinstance(raw.get("currentTiming"), dict) else {}
    history_green = _to_float(timing.get("greenSec"))

    if derived and green_bounds.get("minGreenS") is not None:
        derived_min = int(green_bounds["minGreenS"])
        if derived_min >= DEFAULT_MOTOR_MIN_GREEN_S:
            base_min = derived_min
        elif derived_min <= 0:
            if history_green is not None and history_green <= 0:
                base_min = 0
            elif history_green is not None and history_green > 0:
                base_min = _overlap_slice_effective_min_green_s(history_green)
            else:
                base_min = 0
        else:
            base_min = derived_min
    else:
        fallback = float(DEFAULT_MOTOR_MIN_GREEN_S)
        if history_green is not None:
            if history_green <= 0:
                return 0
            if history_green < fallback:
                fallback = history_green

        explicit = _to_float(raw.get("min_green_s"))
        if explicit is not None:
            if explicit <= 0:
                base_min = 0
            elif explicit >= DEFAULT_MOTOR_MIN_GREEN_S or derived:
                base_min = int(explicit)
            else:
                base_min = int(max(1, explicit, fallback))
        else:
            base_min = int(max(1, fallback))

    return apply_history_green_stability_floor(base_min, history_green)


def _extract_raw_stages(
    request: dict[str, Any],
    parameter_payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    for candidate in (
        request.get("phasePlanOfTimeList"),
        parameter_payload.get("phasePlanOfTimeList"),
    ):
        raw_stage_defs, stage_context = _coerce_raw_stage_bundle(candidate)
        if raw_stage_defs:
            return raw_stage_defs, stage_context
    return [], {}


def _history_max_cycle_s(
    request: dict[str, Any],
    parameter_payload: dict[str, Any],
) -> float:
    """提取本路口历史方案中的最大周期（s），无可用历史方案时返回 0。

    优先读取各方案的 cycleLenSec/cycleTime/cycleLen；
    缺失时按各阶段 currentTiming（stageTotalSec 或 绿+黄+全红）求和回退。
    """
    max_cycle = 0.0
    for candidate in (
        request.get("phasePlanOfTimeList"),
        parameter_payload.get("phasePlanOfTimeList"),
    ):
        if isinstance(candidate, dict):
            plans: list[Any] = [candidate]
        elif isinstance(candidate, list):
            plans = candidate
        else:
            continue
        for plan in plans:
            if not isinstance(plan, dict):
                continue
            cycle = _plan_cycle_s(plan)
            if cycle > max_cycle:
                max_cycle = cycle
    return max_cycle


def _plan_cycle_s(plan: dict[str, Any]) -> float:
    for key in ("cycleLenSec", "cycleTime", "cycleLen", "cycle_len_sec"):
        cycle = _to_float(plan.get(key))
        if cycle is not None and cycle > 0:
            return cycle
    stages = plan.get("phaseStageInfoList")
    if not isinstance(stages, list):
        return 0.0
    total = 0.0
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        timing = stage.get("currentTiming")
        if not isinstance(timing, dict):
            continue
        stage_total = _to_float(timing.get("stageTotalSec"))
        if stage_total is None or stage_total <= 0:
            stage_total = sum(
                _to_float(timing.get(key)) or 0.0
                for key in ("greenSec", "yellowSec", "allRedSec")
            )
        total += max(0.0, stage_total)
    return total


def _extract_parameter_payload(
    request: dict[str, Any],
) -> dict[str, Any]:
    for candidate in (
        request.get("parameter_json_str"),
        request.get("parameterJsonStr"),
        request.get("parameter_json"),
        request.get("parameterJson"),
    ):
        if isinstance(candidate, dict):
            return candidate
        if isinstance(candidate, str) and candidate.strip():
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
    return {}


def _resolve_inter_id(
    request: dict[str, Any],
    parameter_payload: dict[str, Any],
    stage_context: dict[str, Any],
) -> str:
    for value in (
        request.get("interId"),
        parameter_payload.get("interId"),
        stage_context.get("interId"),
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _coerce_raw_stage_bundle(candidate: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if isinstance(candidate, dict):
        if isinstance(candidate.get("phaseStageInfoList"), list):
            return _extract_stage_plan_bundle(candidate)
        return [], {}
    if not isinstance(candidate, list):
        return [], {}
    items = [item for item in candidate if isinstance(item, dict)]
    if not items:
        return [], {}
    plan_candidate = next(
        (item for item in items if isinstance(item.get("phaseStageInfoList"), list)),
        None,
    )
    if plan_candidate is not None:
        return _extract_stage_plan_bundle(plan_candidate)
    return items, {}


def _extract_stage_plan_bundle(plan_candidate: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    phase_stage_info_list = plan_candidate.get("phaseStageInfoList")
    if not isinstance(phase_stage_info_list, list):
        return [], {}
    return (
        [item for item in phase_stage_info_list if isinstance(item, dict)],
        {
            "interId": str(plan_candidate.get("interId") or "").strip() or None,
            "phasePlanId": str(plan_candidate.get("phasePlanId") or "").strip() or None,
            "phasePlanName": str(
                plan_candidate.get("phasePlanName") or DEFAULT_PHASE_PLAN_NAME
            ).strip() or DEFAULT_PHASE_PLAN_NAME,
            "startTime": str(plan_candidate.get("startTime") or "").strip() or None,
            "endTime": str(plan_candidate.get("endTime") or "").strip() or None,
            "controlPlanId": plan_candidate.get("controlPlanId"),
            "overlapStructure": plan_candidate.get("overlapStructure"),
        },
    )


def _cached_overlap_structure(
    stage_context: dict[str, Any],
    stage_defs: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Convert plan-level persisted overlapStructure to optimizer stage indices."""
    raw = stage_context.get("overlapStructure")
    if not isinstance(raw, dict):
        return None
    stage_no_to_idx = {
        int(stage_no): idx
        for idx, stage in enumerate(stage_defs)
        if (stage_no := _to_int(stage.get("stage_no"))) is not None
    }
    if not stage_no_to_idx:
        return None
    converted = structure_stage_nos_to_indices(raw, stage_no_to_idx)
    if converted.get("depth_terms") or converted.get("ratio_groups") or converted.get("slice_stage_idxs"):
        converted["source"] = raw.get("source") or "dwd_ctl_inter_plan_overlap_cfg"
        return converted
    return None


def _normalize_stage_dir_info_list(
    raw: dict[str, Any],
    default_saturation_flow_vph: float,
) -> list[dict[str, Any]]:
    items = raw.get("phaseDirInfoDTOList") or raw.get("phase_dir_info_list") or []
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        dir8_no = int(_first_number(item.get("dir8No"), item.get("dir_no"), 0))
        turn_dir_no = int(_first_number(item.get("turnDirNo"), item.get("turn_dir_no"), -1))
        if dir8_no not in DIR8_LABELS or turn_dir_no not in TURN_DIR_LABELS:
            continue
        lane_count = max(1, int(_first_number(
            item.get("laneCount"),
            item.get("laneNum"),
            item.get("lanes"),
            1,
        )))
        turn_flow_total = max(0.0, _first_number(
            item.get("turnFlowTotal"),
            item.get("turnFlowTotalVph"),
            item.get("turn_flow_total_vph"),
            item.get("flowTotal"),
            0.0,
        ))
        critical_lane_flow_raw = _to_float(
            item.get("criticalLaneFlow")
            if item.get("criticalLaneFlow") is not None
            else item.get("criticalLaneFlowVph")
        )
        if critical_lane_flow_raw is None:
            critical_lane_flow_raw = _to_float(item.get("critical_lane_flow_vph"))
        critical_lane_flow = max(
            0.0,
            critical_lane_flow_raw if critical_lane_flow_raw is not None else turn_flow_total / lane_count,
        )
        saturation_flow_vph = max(1.0, _first_number(
            item.get("saturationFlowVph"),
            item.get("saturation_flow_vph"),
            default_saturation_flow_vph,
        ))
        movement_key = str(item.get("movementKey") or item.get("movement_key") or "").strip()
        if not movement_key:
            movement_key = _movement_key(dir8_no, turn_dir_no)
        label = str(item.get("signalAtom") or item.get("label") or "").strip()
        if not label:
            label = _movement_label(dir8_no, turn_dir_no)
        out.append(
            {
                "movementKey": movement_key,
                "dir8No": dir8_no,
                "turnDirNo": turn_dir_no,
                "turnFlowTotal": round(turn_flow_total, 3),
                "laneCount": lane_count,
                "criticalLaneFlow": round(critical_lane_flow, 3),
                "laneLevelFlow": round(critical_lane_flow, 3),
                "saturationFlowVph": saturation_flow_vph,
                "phaseId": item.get("phaseId"),
                "fridList": item.get("fridList"),
                "label": label,
                "signalAtom": item.get("signalAtom"),
                "sourceKey": item.get("sourceKey"),
                "vendorTag": item.get("vendorTag"),
                "yellowSec": _first_optional_number(
                    item.get("yellowSec"),
                    item.get("yellow_s"),
                    item.get("yellowTime"),
                ),
                "allRedSec": _first_optional_number(
                    item.get("allRedSec"),
                    item.get("all_red_s"),
                    item.get("allRedTime"),
                ),
                "laneGroupIds": item.get("laneGroupIds") or [],
                "laneNos": item.get("laneNos") or [],
                "flowMapping": item.get("flowMapping"),
            }
        )
    return out


def _cyclic_arc(indices: list[int], n: int) -> tuple[int, int] | None:
    """判断阶段索引集合是否为环上连续弧，返回 (起点索引, 弧长)，否则 None."""
    s = set(indices)
    if not s or n <= 0:
        return None
    if len(s) == n:
        return (min(s), n)
    for start in s:
        if (start - 1) % n not in s and all((start + k) % n in s for k in range(len(s))):
            return (start, len(s))
    return None


def _arc_stage_seq(arc: tuple[int, int], n: int) -> list[int]:
    return [(arc[0] + k) % n for k in range(arc[1])]


def _stage_movement_sets(stage_defs: list[dict[str, Any]]) -> list[set[str]]:
    """各阶段放行流向集合：机动车 movementKey + 行人 p{dir8No}."""
    out: list[set[str]] = []
    for stage in stage_defs:
        movs = set(stage.get("movements") or [])
        movs |= {f"p{d}" for d in (stage.get("ped_dirs") or [])}
        out.append(movs)
    return out


def _overlap_movement_label(key: str) -> str:
    if key.startswith("atom:"):
        parts = key.split(":")
        return parts[1] if len(parts) >= 2 and parts[1] else key
    if key.startswith("p"):
        try:
            return f"{DIR8_LABELS[int(key[1:])]}行人"
        except (KeyError, ValueError):
            return key
    try:
        dir8_no, turn_dir_no = key[1:].split("_t")
        return _movement_label(int(dir8_no), int(turn_dir_no))
    except (ValueError, KeyError):
        return key


def _detect_overlap_structure(stage_defs: list[dict[str, Any]]) -> dict[str, Any]:
    """识别方案中的搭接结构，并以现状方案绿灯为参照计算保形特征.

    识别两类结构（行人过街流参与结构识别，但不参与流量目标）：

    1. depth_terms —— 迟启/早断流向：流向 m 的放行弧被另一流向的母弧严格
       包含时，母弧内位于 m 之前/之后的阶段即迟启/早断切片。参照值为现状
       方案下切片时长占母弧时长的比例（搭接深度比，跨周期可比）。
       同一（弧, 母弧）组合的多个流向去重为一条记录。
    2. ratio_groups —— 搭接组：环上相邻且共享流向的阶段连通块（≥2 阶段）。
       参照值为现状方案下组内各阶段时长占组时长的比例（组内绿信比）。

    参照值依赖各相关阶段的现状绿灯（history_green_s），缺失时跳过该记录。
    """
    cached = next(
        (
            stage.get("_cached_overlap_structure")
            for stage in stage_defs
            if isinstance(stage.get("_cached_overlap_structure"), dict)
        ),
        None,
    )
    if cached is not None:
        return cached
    return detect_overlap_structure(stage_defs)


def _keep_deadband_penalty(deviation: float, reference: float, tol_rel: float) -> float:
    """容差带二次惩罚：|偏差| 超出 max(tol_rel×参照值, 0.02) 的部分平方."""
    tolerance = max(tol_rel * abs(reference), 0.02)
    excess = abs(deviation) - tolerance
    return excess * excess if excess > 0 else 0.0


def _scipy_minimize_available() -> bool:
    try:
        from scipy.optimize import minimize  # noqa: F401

        return True
    except Exception:
        return False


def _has_positive_movement_flow(stage_defs: list[dict[str, Any]]) -> bool:
    return any(
        float(mdata.get("flow_vph") or 0) > 0
        for p in stage_defs
        for mdata in (p.get("movement_flows") or {}).values()
    )


def _solve_stage_timing(
    stage_defs: list[dict[str, Any]],
    config: dict[str, float | int],
) -> dict[str, Any]:
    if not _scipy_minimize_available():
        raise RuntimeError(
            "单点配时按设计优选 SciPy SLSQP 文档模型，但当前解释器无法导入 scipy。"
            f"请在已安装项目依赖的环境中运行（例如 `.venv/bin/python -m uvicorn src.api.main:app`）。"
            f" 当前 sys.executable={sys.executable!r}"
        )
    if not _has_positive_movement_flow(stage_defs):
        raise RuntimeError(
            "SciPy 文档 SQP 需要至少一个 phaseDirInfoDTOList 转向在折算后车道级流量大于 0；"
            "请检查 turnFlowTotal/laneCount 或 criticalLaneFlow。"
        )
    result = _solve_stage_timing_document_sqp(stage_defs, config)
    if result is not None:
        return result
    raise RuntimeError(
        "SciPy SLSQP 文档模型在可行域内未得到可用解，请检查 min_green_s / max_green_s、"
        "max_cycle_s 与流量是否自洽，或暂时放宽周期与绿灯上下限。"
    )


def _solve_stage_timing_document_sqp(
    stage_defs: list[dict[str, Any]],
    config: dict[str, float | int],
) -> dict[str, Any] | None:
    """文档定义的 SQP 模型：最小化各方向交通供需强度与目标强度的综合偏差。

    数学模型（来自设计文档）
    -------------------------
    决策变量：g_j  —— 第 j 个阶段（相位）的绿灯显示时长（s）

    目标函数：
        min  Σ_dir [ (1 + (I_dir/I_obj)³) · abs(I_dir − I_obj) ]
             + λ·std(I_dir) + μ·Σ_dir max(0, (I_dir − I_obj)³)

    其中：
        I_dir = vol_dir / s_dir · cycle / (t_dir − loss_dir)
        t_dir = Σ_{j: dir ∈ stage_j}  g_j          （B 矩阵 × g 向量）
        cycle = Σ_j g_j + L_intergreen               （总周期 = 有效绿 + 全红黄灯时间）
        vol_dir = max(vol_dir_raw, vol_virtual, vol_hist)
        vol_virtual(cycle) = (Σ_{j: dir ∈ stage_j} min_green_j − Σ loss_j) / cycle · s_dir · I_obj
                    （动态虚拟流量：无流量方向在其覆盖相位的累计最小绿服务下恰好达到目标强度 I_obj）
        vol_hist = mean_f(T_dir / T_f) · mean_f(vol_f)
                    （历史绿信比虚拟流量：仅对无流量方向计算。T 为现状方案放行总时长，
                      f 遍历有真实流量的方向；按无数据方向与有数据方向的现状放行时间
                      平均比值，乘以有数据方向的平均车道级流量推算）

    约束：
        g_j ∈ [min_green_j, max_green_j]
        Σ_j g_j + L_intergreen ∈ [min_cycle, max_cycle]

    求解：SciPy SLSQP，20 次随机多初值，取目标最小解。
    """
    try:
        from scipy.optimize import minimize
        import random as _random
    except Exception:
        return None

    I_obj = float(config["target_saturation"])
    std_penalty_weight = float(config["intensity_std_penalty_weight"])
    over_target_penalty_weight = float(config["over_target_penalty_weight"])
    debug_objective_terms = bool(config.get("debug_objective_terms", False))
    max_cycle_s = int(config["max_cycle_s"])
    s_default = float(config["saturation_flow_vph"])
    solver_multi_start_count = int(config["solver_multi_start_count"])
    solver_random_seed = int(config["solver_random_seed"])
    solver_max_iterations = int(config["solver_max_iterations"])
    solver_ftol = float(config["solver_ftol"])
    keep_depth_weight = float(config.get("overlap_depth_keep_weight", 0.0))
    keep_ratio_weight = float(config.get("split_ratio_keep_weight", 0.0))
    keep_tolerance_rel = float(config.get("keep_tolerance_rel", 0.15))
    slice_min_green_ratio = float(config.get("overlap_slice_min_green_ratio", 0.0))
    eps = 1e-6
    n = len(stage_defs)

    # ── 常量预计算 ──────────────────────────────────────────────
    # 总插入间隔（黄灯 + 全红）：不是决策变量，但影响 cycle 计算
    L_intergreen = sum(
        float(p.get("yellow_s", 0)) + float(p.get("all_red_s", 0))
        for p in stage_defs
    )
    min_green = [float(p["min_green_s"]) for p in stage_defs]
    max_green = [
        float(p["max_green_s"]) if p["max_green_s"] is not None else float(max_cycle_s)
        for p in stage_defs
    ]
    loss_stage = [float(p["green_loss_s"]) for p in stage_defs]

    # ── 搭接保形：结构识别 + 切片阶段绿灯硬下限 ──────────────────
    overlap_structure = _detect_overlap_structure(stage_defs)
    normal_stage_max_green_adjustments: list[dict[str, Any]] = []
    overlap_slice_stage_idxs = set(overlap_structure["slice_stage_idxs"])
    for j, stage in enumerate(stage_defs):
        if stage.get("fixed_green") or j in overlap_slice_stage_idxs:
            continue
        history_green_s = _to_float(stage.get("history_green_s"))
        if history_green_s is None or history_green_s <= 0:
            continue
        required_max = ceil(history_green_s * NORMAL_STAGE_MAX_GREEN_HISTORY_FACTOR)
        if max_green[j] + eps >= required_max:
            continue
        old_max = max_green[j]
        max_green[j] = float(required_max)
        stage["max_green_s"] = int(required_max)
        normal_stage_max_green_adjustments.append(
            {
                "stage_id": stage["stage_id"],
                "stage_name": stage["stage_name"],
                "history_green_s": round(history_green_s, 1),
                "old_max_green_s": round(old_max, 1),
                "new_max_green_s": int(required_max),
            }
        )
    keep_enabled = bool(
        (keep_depth_weight > 0 and overlap_structure["depth_terms"])
        or (keep_ratio_weight > 0 and overlap_structure["ratio_groups"])
    )
    slice_floor_stages: list[dict[str, Any]] = []
    if slice_min_green_ratio > 0:
        for j in overlap_structure["slice_stage_idxs"]:
            history = _to_float(stage_defs[j].get("history_green_s"))
            if history is None or history <= 0 or stage_defs[j].get("fixed_green"):
                continue
            floor = min(max(min_green[j], slice_min_green_ratio * history), max_green[j])
            if floor > min_green[j]:
                slice_floor_stages.append(
                    {
                        "stage_id": stage_defs[j]["stage_id"],
                        "stage_index": j,
                        "old_min_green_s": min_green[j],
                        "new_min_green_s": round(floor, 1),
                    }
                )
                min_green[j] = floor

    min_cycle_s = sum(min_green) + L_intergreen
    max_cycle_eff = max(min_cycle_s, float(max_cycle_s))  # 实际用的最大周期

    # ── 守卫：要求至少一个方向有真实流量数据 ──────────────────
    # 若全部方向均为虚拟流量，优化器缺乏有效约束，结果不可信。
    has_real_mvt_flow = any(
        float(mdata.get("flow_vph") or 0) > 0
        for p in stage_defs
        for mdata in (p.get("movement_flows") or {}).values()
    )
    if not has_real_mvt_flow:
        return None

    # ── 提取各方向（dir）数据 ────────────────────────────────────
    # 每个方向 = 一个关键车流，可同时出现在多个阶段（共享绿灯）
    directions: list[dict[str, Any]] = []
    mvt_seen: dict[str, int] = {}  # movementKey -> index in directions
    key_flow_seen: dict[tuple[Any, ...], int] = {}  # 关键车流物理身份 -> index

    for stage_idx, stage in enumerate(stage_defs):
        mvt_flows = stage.get("movement_flows") or {}
        for mvt in stage.get("movements", []):
            mdata = mvt_flows.get(mvt) or {}
            vol_raw = float(mdata.get("flow_vph") or 0.0)
            s_dir = float(mdata.get("saturation_flow_vph") or s_default)
            dir8_no = int(mdata.get("dir8No"))
            turn_dir_no = int(mdata.get("turnDirNo"))
            label = str(mdata.get("label") or _movement_label(dir8_no, turn_dir_no))

            # 虚拟流量在 compute_I 中按当前周期动态计算。
            # 同一车流跨多个相位时，最小绿按覆盖相位累计；启动绿损按连续放行块计一次。
            min_green_for_virtual = min_green[stage_idx]
            lane_group_ids = tuple(sorted(str(value) for value in (mdata.get("laneGroupIds") or []) if value))
            key_flow = (
                dir8_no,
                turn_dir_no,
                lane_group_ids,
            )

            if key_flow in key_flow_seen:
                # 该关键车流已在其他阶段/信号原子出现，合并为一个服务对象。
                # 同一阶段重复出现时不重复累计绿灯，也不重复扣启动绿损。
                d = directions[key_flow_seen[key_flow]]
                if stage_idx not in d["stages"]:
                    d["stages"].append(stage_idx)
                    d["virtual_min_green_s"] += min_green_for_virtual
                d["vol_raw"] = max(d["vol_raw"], vol_raw)
                if mvt not in d["movement_keys"]:
                    d["movement_keys"].append(mvt)
                    mvt_seen[mvt] = key_flow_seen[key_flow]
                if label and label not in d["labels"]:
                    d["labels"].append(label)
            else:
                key_flow_seen[key_flow] = len(directions)
                mvt_seen[mvt] = len(directions)
                directions.append({
                    "mvt": mvt,
                    "movement_keys": [mvt],
                    "stages": [stage_idx],
                    "vol_raw": vol_raw,
                    "s_dir": s_dir,
                    "virtual_min_green_s": min_green_for_virtual,
                    "dir8No": dir8_no,
                    "turnDirNo": turn_dir_no,
                    "label": label or mvt,
                    "labels": [label] if label else [mvt],
                })

    if not directions:
        return None

    for d in directions:
        labels = [str(label) for label in d.get("labels", []) if str(label)]
        if labels:
            d["label"] = "/".join(dict.fromkeys(labels))
        loss_dir = _continuous_stage_loss(d["stages"], loss_stage)
        d["loss_dir"] = loss_dir
        d["virtual_loss_dir"] = loss_dir

    # ── 历史绿信比虚拟流量（仅对无流量数据的方向） ──────────────
    # 1. 比值 = 该方向现状放行总时长 / 各有流量方向现状放行总时长，取平均；
    # 2. 虚拟流量 = 平均比值 × 有流量方向的平均车道级流量；
    # 3. 求解时与最小绿动态虚拟流量取较大者（见 compute_I）。
    history_green = [_to_float(p.get("history_green_s")) for p in stage_defs]

    def _dir_history_green_s(d: dict[str, Any]) -> float | None:
        """方向在现状方案中的放行总时长（覆盖阶段绿灯之和），缺失任一阶段返回 None."""
        total = 0.0
        for j in d["stages"]:
            h = history_green[j]
            if h is None or h <= 0:
                return None
            total += h
        return total

    flow_dirs = [d for d in directions if d["vol_raw"] > 0]
    history_virtual_dirs: list[dict[str, Any]] = []
    for d in directions:
        d["history_virtual_vph"] = 0.0
        if d["vol_raw"] > 0 or not flow_dirs:
            continue
        t_dir = _dir_history_green_s(d)
        if t_dir is None:
            continue
        ratios: list[float] = []
        ref_flows: list[float] = []
        for f in flow_dirs:
            t_f = _dir_history_green_s(f)
            if t_f is None or t_f <= 0:
                continue
            ratios.append(t_dir / t_f)
            ref_flows.append(f["vol_raw"])
        if not ratios:
            continue
        avg_ratio = sum(ratios) / len(ratios)
        avg_flow = sum(ref_flows) / len(ref_flows)
        d["history_virtual_vph"] = avg_ratio * avg_flow
        history_virtual_dirs.append(
            {
                "movementKey": d["mvt"],
                "label": d.get("label") or d["mvt"],
                "historyGreenS": round(t_dir, 1),
                "avgGreenRatio": round(avg_ratio, 4),
                "refAvgFlowVph": round(avg_flow, 1),
                "historyVirtualFlowVph": round(d["history_virtual_vph"], 1),
            }
        )

    # ── 目标函数 ─────────────────────────────────────────────────
    def compute_I(g: list[float]) -> list[float]:
        cycle = sum(g) + L_intergreen
        result_I = []
        for d in directions:
            g_dir = sum(g[j] for j in d["stages"])
            eff = max(g_dir - d["loss_dir"], eps)
            vol_virtual = (
                max(0.0, d["virtual_min_green_s"] - d["virtual_loss_dir"])
                / max(cycle, eps)
                * d["s_dir"]
                * I_obj
            )
            vol_dir = max(d["vol_raw"], vol_virtual, d["history_virtual_vph"])
            intensity = vol_dir / d["s_dir"] * cycle / eff
            result_I.append(intensity)
        return result_I

    # ── 搭接保形惩罚 J_keep ──────────────────────────────────────
    def compute_keep_terms(g: list[float]) -> tuple[float, float, list[dict[str, Any]], list[dict[str, Any]]]:
        """返回 (深度惩罚[已归一加权], 比例惩罚[已归一加权], 深度明细, 比例明细)."""
        depth_terms = overlap_structure["depth_terms"]
        ratio_groups = overlap_structure["ratio_groups"]
        depth_details: list[dict[str, Any]] = []
        ratio_details: list[dict[str, Any]] = []

        depth_total = 0.0
        for term in depth_terms:
            parent_total = sum(g[j] for j in term["parent_stages"])
            if parent_total <= eps:
                continue
            late_ratio = sum(g[j] for j in term["late_stages"]) / parent_total
            early_ratio = sum(g[j] for j in term["early_stages"]) / parent_total
            penalty = (
                _keep_deadband_penalty(late_ratio - term["ref_late_ratio"], term["ref_late_ratio"], keep_tolerance_rel)
                + _keep_deadband_penalty(early_ratio - term["ref_early_ratio"], term["ref_early_ratio"], keep_tolerance_rel)
            )
            depth_total += penalty
            depth_details.append(
                {
                    "labels": term["labels"],
                    "refLateRatio": round(term["ref_late_ratio"], 4),
                    "refEarlyRatio": round(term["ref_early_ratio"], 4),
                    "newLateRatio": round(late_ratio, 4),
                    "newEarlyRatio": round(early_ratio, 4),
                    "penalty": round(penalty, 6),
                }
            )

        ratio_total = 0.0
        for group in ratio_groups:
            group_total = sum(g[j] for j in group["stages"])
            if group_total <= eps:
                continue
            new_ratios = [g[j] / group_total for j in group["stages"]]
            penalty = sum(
                _keep_deadband_penalty(new - ref, ref, keep_tolerance_rel)
                for new, ref in zip(new_ratios, group["ref_ratios"])
            ) / len(group["stages"])
            ratio_total += penalty
            ratio_details.append(
                {
                    "stageIds": [stage_defs[j]["stage_id"] for j in group["stages"]],
                    "refRatios": [round(r, 4) for r in group["ref_ratios"]],
                    "newRatios": [round(r, 4) for r in new_ratios],
                    "penalty": round(penalty, 6),
                }
            )

        depth_penalty = keep_depth_weight * depth_total / max(1, len(depth_terms))
        ratio_penalty = keep_ratio_weight * ratio_total / max(1, len(ratio_groups))
        return depth_penalty, ratio_penalty, depth_details, ratio_details

    def evaluate_objective_terms(
        g: list[float],
    ) -> tuple[float, float, float, float, float, list[tuple[str, float, float, float, float]]]:
        intensities = compute_I(g)
        base_total = 0.0
        over_target_total = 0.0
        term_details: list[tuple[str, float, float, float, float]] = []
        for idx, intensity in enumerate(intensities):
            overflow = max(0.0, (intensity - I_obj) ** 3)
            w = 1.0 + (intensity / I_obj) ** 3
            term_value = w * abs(intensity - I_obj)
            base_total += term_value
            over_target_total += overflow
            term_details.append((directions[idx]["mvt"], intensity, w, term_value, overflow))
        mean_I = sum(intensities) / max(len(intensities), 1)
        variance = sum((intensity - mean_I) ** 2 for intensity in intensities) / max(
            len(intensities),
            1,
        )
        std_penalty = std_penalty_weight * (variance + 1e-12) ** 0.5
        overflow_penalty = over_target_penalty_weight * over_target_total
        keep_penalty = 0.0
        if keep_enabled:
            depth_penalty, ratio_penalty, _, _ = compute_keep_terms(g)
            keep_penalty = depth_penalty + ratio_penalty
        total = base_total + std_penalty + overflow_penalty + keep_penalty
        return total, base_total, std_penalty, overflow_penalty, keep_penalty, term_details

    def print_objective_terms(tag: str, g: list[float]) -> None:
        total, base_total, std_penalty, overflow_penalty, keep_penalty, term_details = (
            evaluate_objective_terms(g)
        )
        cycle = sum(g) + L_intergreen
        greens_fmt = ", ".join(f"{value:.3f}" for value in g)
        print(f"[objective:{tag}] cycle={cycle:.3f}, greens=[{greens_fmt}]")
        for mvt, intensity, w, term_value, overflow in term_details:
            print(
                f"  term[{mvt}]: I={intensity:.6f}, weight={w:.6f}, "
                f"weighted_abs_error={term_value:.6f}, overflow={overflow:.6f}"
            )
        print(
            f"  base_total={base_total:.6f}, "
            f"std_penalty: weight={std_penalty_weight:.6f}, "
            f"std={std_penalty / max(std_penalty_weight, 1e-12):.6f}, "
            f"value={std_penalty:.6f}"
        )
        print(
            f"  overflow_penalty: weight={over_target_penalty_weight:.6f}, "
            f"sum_overflow_cubed={overflow_penalty / max(over_target_penalty_weight, 1e-12):.6f}, "
            f"value={overflow_penalty:.6f}"
        )
        if keep_enabled:
            depth_penalty, ratio_penalty, depth_details, ratio_details = compute_keep_terms(g)
            print(
                f"  keep_penalty: depth_weight={keep_depth_weight:.3f}, ratio_weight={keep_ratio_weight:.3f}, "
                f"tol_rel={keep_tolerance_rel:.3f}, depth={depth_penalty:.6f}, ratio={ratio_penalty:.6f}, "
                f"value={keep_penalty:.6f}"
            )
            for detail in depth_details:
                print(f"    depth[{'/'.join(detail['labels'])}]: {detail}")
            for detail in ratio_details:
                print(f"    ratio[{'/'.join(detail['stageIds'])}]: {detail}")
        print(f"  objective_total={total:.6f}")

    def objective(g: list[float]) -> float:
        total, _, _, _, _, _ = evaluate_objective_terms(g)
        return total

    # ── 约束 & 边界 ─────────────────────────────────────────────
    g_sum_min = max(0.0, min_cycle_s - L_intergreen)
    g_sum_max = max(g_sum_min, max_cycle_eff - L_intergreen)

    constraints = [
        {"type": "ineq", "fun": lambda g: sum(g) - g_sum_min},   # Σg ≥ g_sum_min
        {"type": "ineq", "fun": lambda g: g_sum_max - sum(g)},   # Σg ≤ g_sum_max
    ]
    bounds = [(min_green[j], max_green[j]) for j in range(n)]

    # ── 多初值（参考实现：每相位在可行域内独立均匀随机采样）────────
    rng = _random.Random(solver_random_seed)

    def make_random_init() -> list[float]:
        # 每相位在 [min_green_j, max_green_j] 内独立均匀随机，与其他相位无关
        return [
            min_green[j] + rng.random() * (max_green[j] - min_green[j])
            for j in range(n)
        ]

    initial_points: list[list[float]] = [
        [min_green[j] for j in range(n)],  # 第 0 次：全最小绿（确定性起点）
    ]
    # 第 1 次（搭接保形时）：现状方案绿灯裁剪到可行域（确定性起点）。
    # 保形惩罚下原方案邻域大概率是优质盆地，直接从原方案出发帮助收敛。
    history_greens = [_to_float(p.get("history_green_s")) for p in stage_defs]
    if keep_enabled and all(value is not None and value > 0 for value in history_greens):
        initial_points.append(
            [min(max(float(history_greens[j]), min_green[j]), max_green[j]) for j in range(n)]
        )
    initial_points.extend(
        make_random_init()
        for _ in range(max(0, solver_multi_start_count - len(initial_points)))
    )

    best_success_result: Any = None
    best_success_value: float | None = None
    best_fallback_result: Any = None
    best_fallback_value: float | None = None

    for idx, init in enumerate(initial_points):
        try:
            res = minimize(
                objective, init,
                method="SLSQP",
                bounds=bounds,
                constraints=constraints,
                options={"maxiter": solver_max_iterations, "ftol": solver_ftol, "disp": False},
            )
        except Exception:
            continue
        val = float(getattr(res, "fun", objective(list(res.x))))
        if val < 0:
            continue
        if debug_objective_terms:
            print(
                f"[minimize:{idx}] success={bool(getattr(res, 'success', False))}, "
                f"status={getattr(res, 'status', 'NA')}, "
                f"fun={val:.6f}, message={getattr(res, 'message', '')}"
            )
            print_objective_terms(f"minimize_{idx}", [float(x) for x in res.x])
        if bool(getattr(res, "success", False)):
            if best_success_value is None or val < best_success_value:
                best_success_result = res
                best_success_value = val
        if best_fallback_value is None or val < best_fallback_value:
            best_fallback_result = res
            best_fallback_value = val

    best_result = best_success_result if best_success_result is not None else best_fallback_result
    if best_result is None:
        return None
    if debug_objective_terms:
        selected_mode = "success_preferred"
        selected_value = best_success_value
        if best_success_result is None:
            selected_mode = "fallback_min_fun"
            selected_value = best_fallback_value
        print(
            f"[minimize:selected] mode={selected_mode}, "
            f"fun={(selected_value if selected_value is not None else float('nan')):.6f}, "
            f"success={bool(getattr(best_result, 'success', False))}, "
            f"status={getattr(best_result, 'status', 'NA')}, "
            f"message={getattr(best_result, 'message', '')}"
        )

    # ── 整数化并输出 ──────────────────────────────────────────────
    # 整数化沿用求解时生效的最小绿（含搭接切片硬下限），避免取整削掉切片
    rounding_defs = [
        dict(stage, min_green_s=min_green[j]) for j, stage in enumerate(stage_defs)
    ]
    greens = _round_greens_to_ints(rounding_defs, [float(x) for x in best_result.x], int(g_sum_max))
    cycle_s = int(round(sum(greens) + L_intergreen))
    G_eff = sum(greens)

    # 最终各方向供需强度
    final_I = compute_I([float(g) for g in greens])
    dir_intensity_list = [
        {
            "movementKey": d["mvt"],
            "label": d.get("label") or d["mvt"],
            "dir8No": d.get("dir8No"),
            "turnDirNo": d.get("turnDirNo"),
            "intensity": round(final_I[i], 4),
        }
        | (
            {"historyVirtualFlowVph": round(d["history_virtual_vph"], 1)}
            if d["history_virtual_vph"] > 0
            else {}
        )
        for i, d in enumerate(directions)
    ]

    # 各相位饱和度：取该阶段所有方向中最大供需强度
    stage_saturation: list[float] = []
    for stage_idx, stage in enumerate(stage_defs):
        stage_I = [
            final_I[mvt_seen[m]]
            for m in stage.get("movements", [])
            if m in mvt_seen
        ]
        stage_saturation.append(max(stage_I) if stage_I else 0.0)

    # ── 搭接保形报告 ──────────────────────────────────────────────
    overlap_keep_report: dict[str, Any] | None = None
    notes = [
        (
            f"使用文档 SQP 模型（{solver_multi_start_count}次多初值，"
            f"seed={solver_random_seed}）：各方向供需强度 I_dir 与目标强度 I_obj 综合偏差最小。"
        ),
        (
            "目标函数：min Σ[(1+(I/I_obj)³)·abs(I−I_obj)]"
            f" + {std_penalty_weight:.3f}·std(I)"
            f" + {over_target_penalty_weight:.3f}·Σmax(0,(I−I_obj)³)，共 {len(directions)} 个方向。"
        ),
    ]
    if history_virtual_dirs:
        notes.append(
            "以下无流量数据车流已按现状放行时间比值推算虚拟流量"
            "（与最小绿虚拟流量取较大者参与求解）："
            + "、".join(
                f"{item['label']} {item['historyVirtualFlowVph']:.0f}vph"
                f"（现状放行{item['historyGreenS']:.0f}s，平均比值{item['avgGreenRatio']:.2f}）"
                for item in history_virtual_dirs
            )
            + "。"
        )
    if normal_stage_max_green_adjustments:
        notes.append(
            "普通阶段最大绿已按原方案绿灯的"
            f"{NORMAL_STAGE_MAX_GREEN_HISTORY_FACTOR:.1f}倍下限放宽（迟启/早断切片阶段除外）："
            + "、".join(
                f"{item['stage_name']} {item['old_max_green_s']:.0f}s→{item['new_max_green_s']}s"
                for item in normal_stage_max_green_adjustments
            )
            + "。"
        )
    if keep_enabled:
        final_depth_penalty, final_ratio_penalty, depth_details, ratio_details = (
            compute_keep_terms([float(g) for g in greens])
        )
        overlap_keep_report = {
            "depthTerms": depth_details,
            "ratioGroups": ratio_details,
            "sliceMinGreenFloors": slice_floor_stages,
            "weights": {
                "overlapDepthKeepWeight": keep_depth_weight,
                "splitRatioKeepWeight": keep_ratio_weight,
                "keepToleranceRel": keep_tolerance_rel,
                "overlapSliceMinGreenRatio": slice_min_green_ratio,
            },
            "finalPenalty": round(final_depth_penalty + final_ratio_penalty, 6),
        }
        notes.append(
            "已启用搭接保形惩罚：以现状方案搭接深度比与组内绿信比为参照"
            f"（深度权重 {keep_depth_weight:.1f}、比例权重 {keep_ratio_weight:.1f}、"
            f"容差 ±{keep_tolerance_rel:.0%}），识别迟启/早断结构 {len(overlap_structure['depth_terms'])} 处、"
            f"搭接组 {len(overlap_structure['ratio_groups'])} 个。"
        )
        if slice_floor_stages:
            notes.append(
                "搭接切片阶段绿灯硬下限已生效（≥ 现状绿 ×"
                f"{slice_min_green_ratio:.0%}）："
                + "、".join(
                    f"{item['stage_id']} {item['old_min_green_s']:.0f}s→{item['new_min_green_s']:.0f}s"
                    for item in slice_floor_stages
                )
                + "。"
            )
    elif overlap_structure["depth_terms"] or overlap_structure["ratio_groups"]:
        notes.append(
            "检测到搭接结构但保形惩罚未启用"
            "（权重为 0 或现状方案绿灯缺失，无法构造参照值）。"
        )

    return {
        "solver": "scipy_slsqp_document_model",
        "solver_family": "scipy",
        "cycle_s": cycle_s,
        # 实际计算出的周期下限（Σ阶段最小绿 + Σ黄灯/全红）与生效上限
        "min_cycle_s": int(round(min_cycle_s)),
        "max_cycle_eff_s": int(round(max_cycle_eff)),
        "greens": greens,
        "lost_time_total_s": int(round(L_intergreen)),
        "effective_green_total_s": G_eff,
        "stage_saturation": stage_saturation,
        "max_stage_saturation": max(stage_saturation, default=0.0),
        "direction_intensity_list": dir_intensity_list,
        "overlap_keep_report": overlap_keep_report,
        "notes": notes,
    }


def _round_greens_to_ints(
    stage_defs: list[dict[str, Any]],
    greens: list[float],
    max_effective_green_s: int,
) -> list[int]:
    rounded: list[int] = []
    fractions: list[float] = []
    for idx, stage in enumerate(stage_defs):
        raw = float(greens[idx])
        lower = int(stage["min_green_s"])
        upper = int(stage["max_green_s"]) if stage["max_green_s"] is not None else max_effective_green_s
        clipped = min(max(raw, lower), upper)
        integer = int(floor(clipped))
        rounded.append(max(lower, integer))
        fractions.append(clipped - floor(clipped))

    while sum(rounded) > max_effective_green_s:
        candidates = [idx for idx, stage in enumerate(stage_defs) if rounded[idx] > int(stage["min_green_s"])]
        if not candidates:
            break
        candidate = min(
            candidates,
            key=lambda idx: (
                stage_defs[idx]["critical_ratio"],
                -rounded[idx],
                idx,
            ),
        )
        rounded[candidate] -= 1

    target_total = min(
        max_effective_green_s,
        max(sum(rounded), int(round(sum(greens)))),
    )
    while sum(rounded) < target_total:
        candidates = [
            idx
            for idx, stage in enumerate(stage_defs)
            if stage["max_green_s"] is None or rounded[idx] < int(stage["max_green_s"])
        ]
        if not candidates:
            break
        candidate = max(
            candidates,
            key=lambda idx: (
                fractions[idx],
                stage_defs[idx]["critical_ratio"],
                stage_defs[idx]["effective_flow_vph"],
            ),
        )
        rounded[candidate] += 1
        fractions[candidate] = 0.0

    return rounded


def _movement_key(dir8_no: int, turn_dir_no: int) -> str:
    return f"d{dir8_no}_t{turn_dir_no}"


def _movement_label(dir8_no: int, turn_dir_no: int) -> str:
    return f"{DIR8_LABELS.get(dir8_no, dir8_no)}-{TURN_DIR_LABELS.get(turn_dir_no, turn_dir_no)}"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_number(*values: Any) -> float:
    for value in values:
        parsed = _to_float(value)
        if parsed is not None:
            return parsed
    return 0.0


def _first_optional_number(*values: Any) -> float | None:
    for value in values:
        parsed = _to_float(value)
        if parsed is not None:
            return parsed
    return None


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_non_negative_float(value: Any) -> float | None:
    number = _to_float(value)
    if number is None or number < 0:
        return None
    return number


def _to_bool(*values: Any) -> bool:
    for value in values:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "y", "on"}:
                return True
            if normalized in {"0", "false", "no", "n", "off", ""}:
                return False
    return False
