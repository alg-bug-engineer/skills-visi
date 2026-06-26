from __future__ import annotations

from typing import Any

from traffic_signal_agent.planning.single_point import generate_single_point_plan
from traffic_signal_agent.runtime.database import read_mysql_rows


def generate_single_point_optimization_plan(
    strategy_instruction: dict[str, Any],
    task: dict[str, Any],
    profile: dict[str, Any] | None = None,
    diagnosis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Plan-generation script entrypoint for single-intersection optimization."""
    context_data = _load_plan_generation_data(task)
    request = _build_single_point_request(
        strategy_instruction=strategy_instruction,
        task=_merge_task_data(task, context_data),
        profile=profile or {},
        diagnosis=diagnosis or {},
    )
    try:
        plan = generate_single_point_plan(request)
    except Exception as exc:
        return _error_payload("generate_single_point_optimization_plan", exc, request)
    return {
        "ok": True,
        "tool": "generate_single_point_optimization_plan",
        "request": request,
        "plan": plan,
        "context_management": {
            "script": "intersection.plan_generation.generate_single_point_optimization",
            "loaded_data_keys": sorted(context_data.keys()),
            "used_profile": bool(profile),
            "used_diagnosis": bool(diagnosis),
            "strategy_adjustments": request.get("meta", {}).get("strategy_adjustments", []),
        },
    }


def _build_single_point_request(
    *,
    strategy_instruction: dict[str, Any],
    task: dict[str, Any],
    profile: dict[str, Any],
    diagnosis: dict[str, Any],
) -> dict[str, Any]:
    signal = _as_dict(task.get("signal"))
    constraints = _build_constraints(strategy_instruction, task, profile, diagnosis)
    request: dict[str, Any] = {
        "interId": _extract_intersection_id(task),
        "constraints": constraints,
        "strategy_instruction": strategy_instruction,
        "meta": {
            "profile_scene_type": profile.get("scene_type"),
            "diagnosis_priority_order": diagnosis.get("priority_order", []),
            "strategy_adjustments": constraints.pop("_strategy_adjustments", []),
        },
    }
    for key in (
        "phasePlanOfTimeList",
        "parameter_json_str",
        "parameterJsonStr",
        "parameter_json",
        "parameterJson",
    ):
        if key in signal:
            request[key] = signal[key]
        elif key in task:
            request[key] = task[key]
    if "phaseStageInfoList" in signal and "phasePlanOfTimeList" not in request:
        request["phasePlanOfTimeList"] = [
            {
                "interId": request["interId"],
                "phasePlanId": signal.get("phasePlanId", f"{request['interId']}-PLAN"),
                "phasePlanName": signal.get("phasePlanName", "DeepAgent 单点优化输入方案"),
                "phaseStageInfoList": signal["phaseStageInfoList"],
            }
        ]
    if "obj_intensity" in signal:
        request["obj_intensity"] = signal["obj_intensity"]
    elif "target_saturation" in request["constraints"]:
        request["obj_intensity"] = request["constraints"]["target_saturation"]
    return request


def _build_constraints(
    strategy_instruction: dict[str, Any],
    task: dict[str, Any],
    profile: dict[str, Any],
    diagnosis: dict[str, Any],
) -> dict[str, Any]:
    constraints = dict(_as_dict(task.get("constraints")))
    constraints.update(_as_dict(strategy_instruction.get("constraints")))
    adjustments: list[str] = []

    for key in ("target_saturation", "target_saturation_min", "target_saturation_max"):
        if key in strategy_instruction and key not in constraints:
            constraints[key] = strategy_instruction[key]

    priority_order = [str(item) for item in diagnosis.get("priority_order", [])]
    problem_set = [str(item) for item in strategy_instruction.get("problem_set", [])]
    issue_tokens = set(priority_order + problem_set)
    pressure = str(profile.get("pressure_level", "")).lower()

    if {"oversaturation", "spillback", "overflow", "溢流"}.intersection(issue_tokens) or pressure == "high":
        constraints.setdefault("target_saturation", 0.78)
        constraints.setdefault("over_target_penalty_weight", 35.0)
        constraints.setdefault("solver_multi_start_count", 24)
        adjustments.append("高压力/溢流风险：降低目标饱和度并提高超目标惩罚。")
    if {"empty_green", "imbalance", "green_loss"}.intersection(issue_tokens):
        constraints.setdefault("intensity_std_penalty_weight", 16.0)
        adjustments.append("空放/失衡问题：提高供需强度均衡惩罚。")

    traffic_state = _as_dict(profile.get("traffic_state"))
    saturation = _to_float(traffic_state.get("saturation"))
    if saturation is not None and saturation > 1.0:
        constraints.setdefault("max_cycle_s", 180)
        adjustments.append("场景认知饱和度超过 1.0：放宽最大周期。")

    constraints["_strategy_adjustments"] = adjustments
    return constraints


def _load_plan_generation_data(task: dict[str, Any]) -> dict[str, Any]:
    context = _as_dict(task.get("context"))
    data = _as_dict(context.get("plan_generation_data"))
    sql = context.get("plan_generation_sql")
    if isinstance(sql, str) and sql.strip():
        try:
            data["db_rows"] = read_mysql_rows(sql, _as_dict(context.get("plan_generation_sql_params")), limit=200)
        except Exception as exc:
            data["db_error"] = str(exc)
    return data


def _merge_task_data(task: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    if not data:
        return task
    merged = dict(task)
    signal = dict(_as_dict(task.get("signal")))
    if "phasePlanOfTimeList" in data and "phasePlanOfTimeList" not in signal:
        signal["phasePlanOfTimeList"] = data["phasePlanOfTimeList"]
    if "phaseStageInfoList" in data and "phaseStageInfoList" not in signal:
        signal["phaseStageInfoList"] = data["phaseStageInfoList"]
    merged["signal"] = signal
    return merged


def _extract_intersection_id(task: dict[str, Any]) -> str:
    scope = _as_dict(task.get("scope"))
    signal = _as_dict(task.get("signal"))
    for value in (scope.get("intersection_id"), signal.get("interId"), signal.get("intersection_id"), scope.get("id")):
        if value:
            return str(value)
    ids = scope.get("ids")
    if isinstance(ids, list) and ids:
        return str(ids[0])
    return str(task.get("task_id", "UNKNOWN"))


def _error_payload(tool_name: str, exc: Exception, request: dict[str, Any]) -> dict[str, Any]:
    return {"ok": False, "tool": tool_name, "error": str(exc), "request": request, "plan": None}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

