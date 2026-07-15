from __future__ import annotations

import copy
from typing import Any


PACKAGE_STRATEGIES = {
    "downstream_protection": {
        "strategy": "downstream_protection",
        "target_green_delta": -2,
        "cycle_delta": 0,
        "upstream_control": False,
        "rollback_condition": "下游排队比持续上升时回滚至原方案",
    },
    "incremental_release": {
        "strategy": "incremental_release",
        "target_green_delta": 5,
        "cycle_delta": 0,
        "upstream_control": False,
        "rollback_condition": "下游排队比持续上升或目标方向绿灯利用率异常下降时回滚",
    },
    "arterial_coordination": {
        "strategy": "arterial_coordination",
        "target_green_delta": 2,
        "cycle_delta": 10,
        "upstream_control": True,
        "rollback_condition": "下游排队比持续上升、上游排队超过安全边界时回滚",
    },
    "verification_plan": {
        "strategy": "verification_plan",
        "target_green_delta": 0,
        "cycle_delta": 0,
        "upstream_control": False,
        "rollback_condition": "核验未通过时不实施配时调整",
    },
    "conditional_incremental_release": {
        "strategy": "conditional_incremental_release",
        "target_green_delta": 5,
        "cycle_delta": 0,
        "upstream_control": False,
        "rollback_condition": "核验未通过或下游排队比持续上升时回滚至原方案",
    },
}

_DIR8_LABEL = {0: "北", 1: "东北", 2: "东", 3: "东南", 4: "南", 5: "西南", 6: "西", 7: "西北"}
_TURN_LABEL = {0: "掉头", 1: "左转", 2: "直行", 3: "右转", 4: "掉头"}


def _number_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_stage_movements(stage: dict[str, Any]) -> list[dict[str, Any]]:
    """把 PG 原始 phaseDirInfoDTOList 转成前端审计字段，值只取真实绑定结果。"""
    raw = stage.get("movements")
    if not isinstance(raw, list) or not raw:
        raw = stage.get("phaseDirInfoDTOList")
    if not isinstance(raw, list):
        return []

    movements: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        dir8 = item.get("dir8No")
        turn = item.get("turnDirNo")
        try:
            dir8_no = int(dir8) if dir8 is not None else None
            turn_no = int(turn) if turn is not None else None
        except (TypeError, ValueError):
            dir8_no, turn_no = None, None
        key = item.get("movement_key") or item.get("movementKey")
        if not key and dir8_no is not None and turn_no is not None:
            key = f"d{dir8_no}_t{turn_no}"
        label = item.get("label")
        if not label and dir8_no is not None and turn_no is not None:
            label = f"{_DIR8_LABEL.get(dir8_no, '')}进口{_TURN_LABEL.get(turn_no, '')}" or None
        saturation = item.get("saturation")
        if saturation is None:
            saturation = item.get("turnSaturation")
        movements.append(
            {
                "movement_key": key,
                "movementKey": key,
                "label": label,
                "dir8No": dir8_no,
                "turnDirNo": turn_no,
                "turnFlowTotal": _number_or_none(item.get("turnFlowTotal")),
                "laneCount": _number_or_none(item.get("laneCount")),
                "saturation": _number_or_none(saturation),
                "flow_available": item.get("flow_available"),
                "source": item.get("source") or "pg_turn_flow_binding",
            }
        )
    return movements


def _build_trial_evidence_meta(
    stages: list[dict[str, Any]],
    *,
    current_cycle_s: int,
) -> dict[str, Any]:
    """从真实转向饱和度构建供需强度；不以固定值或前端占位补齐。"""
    by_key: dict[str, dict[str, Any]] = {}
    for stage in stages:
        for movement in stage.get("movements") or []:
            key = str(movement.get("movementKey") or movement.get("movement_key") or "")
            if not key:
                continue
            row = by_key.setdefault(key, dict(movement))
            saturation = _number_or_none(movement.get("saturation"))
            if saturation is not None:
                existing = _number_or_none(row.get("saturation"))
                row["saturation"] = saturation if existing is None else max(existing, saturation)
            flow = _number_or_none(movement.get("turnFlowTotal"))
            if flow is not None:
                existing_flow = _number_or_none(row.get("turnFlowTotal"))
                row["turnFlowTotal"] = flow if existing_flow is None else max(existing_flow, flow)

    direction_intensity = []
    for key, row in by_key.items():
        intensity = _number_or_none(row.get("saturation"))
        if intensity is None:
            continue
        direction_intensity.append(
            {
                "movementKey": key,
                "label": row.get("label"),
                "dir8No": row.get("dir8No"),
                "turnDirNo": row.get("turnDirNo"),
                "intensity": intensity,
                "flow_source": "pg_turn_saturation",
            }
        )

    unique_flows = [
        _number_or_none(row.get("turnFlowTotal"))
        for row in by_key.values()
    ]
    total_flow = sum(value for value in unique_flows if value is not None)
    return {
        "direction_intensity_list": direction_intensity,
        "total_turn_flow_vph": total_flow if any(value is not None for value in unique_flows) else None,
        "data_quality": {
            "current_timing_source": "pg_signal_plan",
            "movement_source": "pg_turn_flow_binding",
            "intensity_source": "pg_turn_saturation",
            "current_cycle_s": current_cycle_s,
        },
    }


def build_strategy_instruction(strategy: dict[str, Any], plan_id: str) -> dict[str, Any]:
    # 候选必须按自身 plan_id 取参，禁止共享上游 strategy_package 导致三案同参
    package = plan_id
    base = copy.deepcopy(
        PACKAGE_STRATEGIES.get(package)
        or PACKAGE_STRATEGIES.get(strategy.get("strategy_package") or "", PACKAGE_STRATEGIES["downstream_protection"])
    )
    base["strategy"] = package
    base["package"] = package
    base["plan_id"] = plan_id
    return base


def adjust_phase_timing(
    *,
    signal: dict[str, Any],
    strategy_instruction: dict[str, Any],
    ticket: dict[str, Any],
    diagnosis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lightweight deterministic phase adjustment with min/max green bounds.

    输出带 current_timing / optimized_timing / green_delta_s，便于前端阶段卡展示借绿。
    """
    diagnosis = diagnosis or {}
    raw_stages = signal.get("phase_stage_timing_list") or []
    stages = [copy.deepcopy(s) for s in raw_stages]
    if not stages:
        return {"ok": False, "reason": "signal 缺少 phase_stage_timing_list"}

    # 统一字段，便于借绿计算。
    # 注意：部分上游会把 greenTime 写成等于 minGreen，真实绿时应优先读 current_timing / green_time_s。
    for stage in stages:
        stage["greenTime"] = _read_green_s(stage)
        if stage.get("minGreenTime") is None and stage.get("min_green_time_s") is not None:
            stage["minGreenTime"] = int(stage["min_green_time_s"])
        if stage.get("maxGreenTime") is None and stage.get("max_green_time_s") is not None:
            stage["maxGreenTime"] = int(stage["max_green_time_s"])
        cur = stage.get("current_timing") if isinstance(stage.get("current_timing"), dict) else {}
        if stage.get("yellowTime") is None:
            stage["yellowTime"] = int(
                cur.get("yellow_time_s") or stage.get("yellow_time_s") or 3
            )
        if stage.get("allRedTime") is None:
            stage["allRedTime"] = int(
                cur.get("all_red_time_s") or stage.get("all_red_time_s") or 2
            )

    baselines = [
        {
            "green": int(s.get("greenTime") or s.get("green_time_s") or 0),
            "yellow": int(s.get("yellowTime") or s.get("yellow_time_s") or 3),
            "all_red": int(s.get("allRedTime") or s.get("all_red_time_s") or 2),
            # PG 联调返回的是 phaseDirInfoDTOList；在方案层统一输出 movements，
            # 避免“数据库有释放方向，前端却被判为缺证据”。
            "movements": _normalize_stage_movements(s),
            "source_stage_atoms": s.get("source_stage_atoms"),
            "flow_combo": s.get("flow_combo"),
            "phase_saturation": s.get("phase_saturation"),
        }
        for s in stages
    ]

    direction = ticket.get("direction", "东向西")
    movement = ticket.get("movement", "直行")
    target_key = f"{direction}{movement}"
    target_idx = _find_target_stage_index(stages, target_key)
    if target_idx is None:
        return {"ok": False, "reason": f"未找到目标相位: {target_key}"}

    target_delta = int(strategy_instruction.get("target_green_delta") or 0)
    cycle_delta = int(strategy_instruction.get("cycle_delta") or 0)
    donor_idx = _find_donor_stage_index(stages, skip_idx=target_idx)

    if target_delta > 0 and donor_idx is not None:
        borrow = min(target_delta, _borrowable(stages[donor_idx]))
        stages[donor_idx]["greenTime"] = int(stages[donor_idx]["greenTime"]) - borrow
        stages[target_idx]["greenTime"] = int(stages[target_idx]["greenTime"]) + borrow
    elif target_delta != 0:
        stages[target_idx]["greenTime"] = int(stages[target_idx]["greenTime"]) + target_delta

    _clamp_stage(stages[target_idx])
    if donor_idx is not None:
        _clamp_stage(stages[donor_idx])

    current_cycle_s = sum(
        b["green"] + b["yellow"] + b["all_red"] for b in baselines
    )
    cycle_s = _sum_cycle(stages) + cycle_delta
    timing_list = []
    for idx, stage in enumerate(stages):
        row = _normalize_stage(stage, cycle_s)
        base = baselines[idx]
        opt_green = int(row["green_time_s"])
        cur_green = int(base["green"])
        yellow = int(base["yellow"])
        all_red = int(base["all_red"])
        cur_total = cur_green + yellow + all_red
        opt_total = opt_green + int(row["yellow_time_s"]) + int(row["all_red_time_s"])
        row["current_timing"] = {
            "green_time_s": cur_green,
            "yellow_time_s": yellow,
            "all_red_time_s": all_red,
            "stage_total_s": cur_total,
        }
        row["optimized_timing"] = {
            "green_time_s": opt_green,
            "yellow_time_s": int(row["yellow_time_s"]),
            "all_red_time_s": int(row["all_red_time_s"]),
            "stage_total_s": opt_total,
        }
        row["green_delta_s"] = opt_green - cur_green
        row["stage_delta_s"] = opt_total - cur_total
        if base.get("movements"):
            row["movements"] = base["movements"]
        if base.get("source_stage_atoms") is not None:
            row["source_stage_atoms"] = base["source_stage_atoms"]
        if base.get("flow_combo") is not None:
            row["flow_combo"] = base["flow_combo"]
        if base.get("phase_saturation") is not None:
            row["phase_saturation"] = base["phase_saturation"]
        if idx == target_idx:
            row["role"] = "target"
        elif donor_idx is not None and idx == donor_idx:
            row["role"] = "donor"
        timing_list.append(row)

    upstream_control = _build_upstream_control(strategy_instruction, diagnosis)
    downstream_risk = _assess_downstream_risk(diagnosis)

    timing_out = {
        "available": True,
        "cycle_s": cycle_s,
        "current_cycle_s": current_cycle_s,
        "cycle_delta_s": cycle_s - current_cycle_s,
        "phase_stage_timing_list": timing_list,
        "meta": _build_trial_evidence_meta(timing_list, current_cycle_s=current_cycle_s),
        "target_stage_index": target_idx,
        "donor_stage_index": donor_idx,
        "requested_target_green_delta_s": target_delta,
    }
    missing_fields: list[str] = []
    if not any(stage.get("movements") for stage in timing_list):
        missing_fields.append("timing.phase_stage_timing_list.movements")
    if not timing_out["meta"].get("direction_intensity_list"):
        missing_fields.append("timing.meta.direction_intensity_list")
    if missing_fields:
        # 可选审计维度缺失不应抹掉已经存在的现状/试运行配时；前端分别降级展示。
        timing_out["missing_fields"] = missing_fields
    timing_out.update(summarize_proposed_deltas(timing_out))

    return {
        "ok": True,
        "timing": timing_out,
        "phaseStageTimingList": timing_list,
        "cycle_s": cycle_s,
        "upstream_control": upstream_control,
        "phase_offset_sec": 15 if strategy_instruction.get("upstream_control") else 0,
        "pedestrian_constraints": {"satisfied": True, "violations": []},
        "downstream_risk": downstream_risk,
    }


def _read_green_s(stage: dict[str, Any]) -> int:
    cur = stage.get("current_timing") if isinstance(stage.get("current_timing"), dict) else {}
    for source in (cur.get("green_time_s"), stage.get("green_time_s"), stage.get("greenTime")):
        if source is None:
            continue
        try:
            return int(source)
        except (TypeError, ValueError):
            continue
    return 0


def _opposite_dir_char(dir_char: str) -> str:
    return {"北": "南", "南": "北", "东": "西", "西": "东"}.get(dir_char, "")


def _find_target_stage_index(stages: list[dict[str, Any]], target_key: str) -> int | None:
    """匹配目标方向相位；多命中时优先「专向、绿时长」更高的阶段。"""
    if not stages:
        return None
    dir_char = target_key[0] if target_key else ""
    turn_token = "直" if "直行" in target_key else ("左" if "左" in target_key else ("右" if "右" in target_key else ""))
    atom_key = f"{dir_char}{turn_token}" if dir_char and turn_token else ""
    aliases = [target_key]
    if atom_key:
        aliases.append(atom_key)
    opp = _opposite_dir_char(dir_char)
    opp_atom = f"{opp}{turn_token}" if opp and turn_token else ""

    scored: list[tuple[int, int]] = []
    for idx, stage in enumerate(stages):
        movement_key = str(stage.get("movement_key") or "")
        name = str(stage.get("phase_stage_name") or stage.get("phaseStageName") or "")
        atoms = [str(x) for x in (stage.get("source_stage_atoms") or [])]
        atom_blob = " ".join(atoms)
        blob = f"{movement_key} {name} {atom_blob}"
        matched = movement_key == target_key or any(a and a in blob for a in aliases)
        if not matched and dir_char and turn_token:
            matched = any(dir_char in a and turn_token in a for a in atoms) or (
                dir_char in name and turn_token in name
            )
        if not matched:
            continue
        green = int(stage.get("greenTime") or _read_green_s(stage) or 0)
        if green <= 0:
            continue
        min_green = int(stage.get("minGreenTime") or stage.get("min_green_time_s") or 0)
        max_green = int(stage.get("maxGreenTime") or stage.get("max_green_time_s") or green + 30)
        score = green
        if atom_key and (atom_key in atoms or atom_key in name):
            score += 500
        if opp_atom and (opp_atom in atoms or opp_atom in name):
            score -= 200  # 共享对向直行相位降权
        if min_green and green < min_green:
            score -= 1000  # 现状已低于最小绿的残余相位，不宜作加绿目标
        if max_green and green >= max_green:
            score -= 800  # 已达上限无法再加
        scored.append((score, idx))
    if scored:
        scored.sort(reverse=True)
        return scored[0][1]
    # 禁止静默落到阶段 0：匹配失败应由上游显式降级
    return None


def summarize_proposed_deltas(timing: dict[str, Any] | None) -> dict[str, int]:
    """从拟实施配时阶段列表读取实际目标绿差、借绿差、周期差（禁止用 instruction 盖写）。"""
    timing = timing or {}
    stages = timing.get("phase_stage_timing_list") or []
    target_d = 0
    donor_d = 0
    saw_target_role = False
    saw_donor_role = False
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        try:
            delta = int(stage.get("green_delta_s") or 0)
        except (TypeError, ValueError):
            delta = 0
        role = stage.get("role")
        if role == "target":
            target_d = delta
            saw_target_role = True
        elif role == "donor":
            donor_d = delta
            saw_donor_role = True
        elif not saw_target_role and delta > target_d:
            target_d = delta
        elif not saw_donor_role and delta < donor_d:
            donor_d = delta
    try:
        cycle_d = int(timing.get("cycle_delta_s") or 0)
    except (TypeError, ValueError):
        cycle_d = 0
    return {
        "target_green_delta_s": target_d,
        "donor_green_delta_s": donor_d,
        "cycle_delta_s": cycle_d,
    }


def attach_proposed_timing_fields(
    timing: dict[str, Any] | None,
    *,
    requested_target_green_delta: int | None = None,
) -> dict[str, Any]:
    """为门控后拟实施配时补齐可展示摘要字段。"""
    base = dict(timing or {})
    summary = summarize_proposed_deltas(base)
    out = {
        **base,
        **summary,
        "available": True,
        "gate": "verification_passed",
        "label": "门控通过后拟实施",
    }
    if requested_target_green_delta is not None:
        out["requested_target_green_delta_s"] = int(requested_target_green_delta)
    return out


def _find_donor_stage_index(stages: list[dict[str, Any]], *, skip_idx: int) -> int | None:
    best_idx = None
    best_rank = None
    for idx, stage in enumerate(stages):
        if idx == skip_idx:
            continue
        spare = _borrowable(stage)
        if spare <= 0:
            continue
        green = int(stage.get("greenTime") or 0)
        rank = (spare, green)
        if best_rank is None or rank > best_rank:
            best_rank = rank
            best_idx = idx
    return best_idx


def _borrowable(stage: dict[str, Any]) -> int:
    green = int(stage.get("greenTime") or 0)
    min_green = int(stage.get("minGreenTime") or stage.get("min_green_time_s") or 0)
    return max(0, green - min_green)


def _clamp_stage(stage: dict[str, Any]) -> None:
    green = int(stage.get("greenTime") or 0)
    min_green = int(stage.get("minGreenTime") or 0)
    max_green = int(stage.get("maxGreenTime") or green + 30)
    stage["greenTime"] = max(min_green, min(max_green, green))


def _sum_cycle(stages: list[dict[str, Any]]) -> int:
    total = 0
    for stage in stages:
        total += int(stage.get("greenTime") or 0)
        total += int(stage.get("yellowTime") or stage.get("yellow_time_s") or 3)
        total += int(stage.get("allRedTime") or stage.get("all_red_time_s") or 2)
    return total


def _normalize_stage(stage: dict[str, Any], cycle_s: int) -> dict[str, Any]:
    green = int(stage.get("greenTime") or stage.get("green_time_s") or 0)
    yellow = int(stage.get("yellowTime") or stage.get("yellow_time_s") or 3)
    all_red = int(stage.get("allRedTime") or stage.get("all_red_time_s") or 2)
    min_green = int(stage.get("minGreenTime") or stage.get("min_green_time_s") or 0)
    max_green = int(stage.get("maxGreenTime") or stage.get("max_green_time_s") or green)
    return {
        "phase_stage_id": stage.get("phase_stage_id") or stage.get("phaseStageId"),
        "phase_stage_name": stage.get("phase_stage_name") or stage.get("phaseStageName"),
        "green_time_s": green,
        "yellow_time_s": yellow,
        "all_red_time_s": all_red,
        "min_green_time_s": min_green,
        "max_green_time_s": max_green,
        "greenTime": green,
        "yellowTime": yellow,
        "allRedTime": all_red,
        "minGreenTime": min_green,
        "maxGreenTime": max_green,
        "split_ratio": round(green / max(cycle_s, 1), 4),
        "movement_key": stage.get("movement_key"),
    }


def _build_upstream_control(
    strategy_instruction: dict[str, Any],
    diagnosis: dict[str, Any],
) -> dict[str, Any]:
    if not strategy_instruction.get("upstream_control"):
        return {"enabled": False, "control_points": []}

    points = []
    for trace in (diagnosis.get("flow_trace") or {}).get("entry_traces") or []:
        points.append(
            {
                "inter_id": trace.get("upstream_inter_id"),
                "inter_name": trace.get("upstream_inter_name"),
                "lng": trace.get("upstream_lng"),
                "lat": trace.get("upstream_lat"),
                "green_ratio_delta": -0.08,
            }
        )
    return {"enabled": True, "control_points": points}


def _assess_downstream_risk(diagnosis: dict[str, Any]) -> dict[str, Any]:
    blocked = (diagnosis.get("downstream_trace") or {}).get("governance", {}).get(
        "downstream_blocked", False
    )
    reasons = []
    if blocked:
        reasons.append("下游节点饱和，继续放量存在外溢风险")
    down_queue = (diagnosis.get("downstream_metrics") or {}).get("queue_ratio")
    if down_queue is not None and down_queue >= 0.8:
        reasons.append(f"下游排队比={down_queue:.2f}")
    return {
        "level": "high" if reasons else "medium",
        "reasons": reasons or ["需持续监测下游承接能力"],
    }
