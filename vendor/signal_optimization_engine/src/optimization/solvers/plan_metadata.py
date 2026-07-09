"""方案生成相关类型与契约常量（文档化，运行时以 dict 传递）."""

from __future__ import annotations

from typing import Any


def empty_plan_meta(algorithm: str, version: str = "0.1.0") -> dict[str, Any]:
    """算法元信息占位."""
    return {"algorithm": algorithm, "version": version, "notes": []}


# ---------- 单点方案建议字段 ----------
#
# 输入 request:
#   interId: str
#   phasePlanOfTimeList / parameter_json_str
#   strategy_instruction: dict  # 可选，控制策略输出
#   constraints: dict  # 可选，如 max_cycle_s, min_green_s
#
# 输出 plan:
#   isError / data / error
#   planType: "single_point"
#   intersectionId, cycleTime, phasePlanId, phasePlanName, phaseStageTimingList, meta


# ---------- 干线协调方案建议字段 ----------
#
# 输入 request:
#   corridor_id: str
#   intersection_ids: list[str]  # 沿走廊顺序
#   profile / strategy_instruction / constraints 同单点
#
# 输出 plan:
#   plan_type: "corridor_coordination"
#   corridor_id, coordination: { bandwidth_s, design_speed_kmh, nodes: [...] }, meta


def merge_request(base: dict[str, Any], **extra: Any) -> dict[str, Any]:
    """浅合并请求 dict，后者覆盖前者."""
    out = dict(base) if base else {}
    for k, v in extra.items():
        if v is not None:
            out[k] = v
    return out
