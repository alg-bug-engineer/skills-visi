"""溢出机制判别与决策契约（确定性，不经 LLM）。"""

from __future__ import annotations

from typing import Any

from app.metrics.traffic import THRESHOLDS


MECHANISM_CODES = (
    "downstream_blocked",
    "local_release_insufficient",
    "discharge_anomaly",
    "upstream_arrival_shock",
    "evidence_insufficient",
)


def classify_overflow_mechanism(
    *,
    downstream_state: dict[str, Any],
    target_queue_ratio: float | None,
    target_saturation: float | None,
    target_green_utilization: float | None,
    upstream_arrival_intense: bool = False,
    green_end_queue_remains: bool | None = None,
    signal_available: bool = True,
) -> dict[str, Any]:
    """按固定顺序输出唯一主机制。"""
    ds = (downstream_state or {}).get("decision")
    supporting: list[str] = []
    contradicting: list[str] = []
    missing: list[str] = []

    if ds == "blocked":
        return {
            "primary": "downstream_blocked",
            "secondary": None,
            "status": "supported",
            "confidence": float((downstream_state or {}).get("confidence") or 0.85),
            "supporting_evidence": list((downstream_state or {}).get("reasons") or ["直接下游承接受限"]),
            "contradicting_evidence": [],
            "missing_evidence": list((downstream_state or {}).get("missing_metrics") or []),
        }

    if ds == "unknown" or ds is None:
        return {
            "primary": "evidence_insufficient",
            "secondary": None,
            "status": "unknown",
            "confidence": 0.3,
            "supporting_evidence": ["下游承接指标不足，无法完成机制分流"],
            "contradicting_evidence": [],
            "missing_evidence": ["直接下游排队比", "直接下游饱和度"],
        }

    if not signal_available or target_queue_ratio is None:
        return {
            "primary": "evidence_insufficient",
            "secondary": None,
            "status": "unknown",
            "confidence": 0.35,
            "supporting_evidence": [],
            "contradicting_evidence": [],
            "missing_evidence": ["目标进口排队或现状配时"],
        }

    high_queue = target_queue_ratio >= THRESHOLDS["queue_ratio_warning"]
    sat = float(target_saturation) if target_saturation is not None else None
    util = float(target_green_utilization) if target_green_utilization is not None else None
    high_demand = (
        sat is not None
        and util is not None
        and sat >= THRESHOLDS["saturation_high"]
        and util >= THRESHOLDS["green_utilization_high"]
    )
    low_util = util is not None and util < THRESHOLDS["green_utilization_low"]

    # 下游 slack：继续判断目标放行状态
    if high_queue and high_demand and (green_end_queue_remains is not False):
        if green_end_queue_remains is None:
            missing.append("逐周期绿灯末端剩余队列核验")
        supporting.append("高需求且高绿灯利用率，下游有承接余量")
        return {
            "primary": "local_release_insufficient",
            "secondary": "upstream_arrival_pressure" if upstream_arrival_intense else None,
            "status": "hypothesis" if green_end_queue_remains is None else "supported",
            "confidence": 0.7 if green_end_queue_remains else 0.55,
            "supporting_evidence": supporting,
            "contradicting_evidence": contradicting,
            "missing_evidence": missing,
        }

    if high_queue and low_util:
        supporting.append("目标进口高排队")
        supporting.append(f"绿灯利用率偏低（{util:.2f}）")
        supporting.append("直接下游初步有承接余量")
        contradicting.append("尚不支持下游整体承接不足")
        missing.extend(
            [
                "逐周期绿灯末端剩余队列核验",
                "出口通行与渠化核验",
                "检测器有效性核验",
            ]
        )
        secondary = "upstream_arrival_pressure" if upstream_arrival_intense else None
        return {
            "primary": "discharge_anomaly",
            "secondary": secondary,
            "status": "hypothesis",
            "confidence": 0.58,
            "supporting_evidence": supporting,
            "contradicting_evidence": contradicting,
            "missing_evidence": missing,
        }

    if upstream_arrival_intense and high_queue:
        return {
            "primary": "upstream_arrival_shock",
            "secondary": None,
            "status": "hypothesis",
            "confidence": 0.55,
            "supporting_evidence": ["上游到达强度高且目标进口排队高"],
            "contradicting_evidence": [],
            "missing_evidence": ["上游车团到达时序与目标相位匹配核验"],
        }

    return {
        "primary": "evidence_insufficient",
        "secondary": None,
        "status": "unknown",
        "confidence": 0.4,
        "supporting_evidence": supporting,
        "contradicting_evidence": contradicting,
        "missing_evidence": ["放行效率或上游冲击的补充证据"],
    }


def map_mechanism_to_decision(
    *,
    primary_mechanism: str,
    verification_passed: bool = False,
    reason: str | None = None,
) -> dict[str, Any]:
    """机制 → DecisionContract；禁止 LLM 自由选择策略包。"""
    mechanism = primary_mechanism or "evidence_insufficient"

    if mechanism == "downstream_blocked":
        return _contract(
            decision_mode="downstream_protection",
            allowed=["downstream_protection", "arterial_coordination"],
            forbidden=["incremental_release", "aggressive_retiming", "conditional_incremental_release"],
            preconditions_satisfied=True,
            executable=True,
            plan_status="trial_ready",
            strategy_package="downstream_protection",
            reason=reason or "直接下游承接受限，先保护下游",
        )

    if mechanism == "local_release_insufficient":
        return _contract(
            decision_mode="incremental_release",
            allowed=["incremental_release"],
            forbidden=["downstream_protection", "aggressive_retiming"],
            preconditions_satisfied=True,
            executable=True,
            plan_status="trial_ready",
            strategy_package="incremental_release",
            reason=reason or "下游有余量且目标方向放行不足，小步增绿",
        )

    if mechanism == "discharge_anomaly":
        if verification_passed:
            return _contract(
                decision_mode="incremental_release_trial",
                allowed=["incremental_release", "conditional_incremental_release"],
                forbidden=["downstream_protection", "arterial_coordination", "aggressive_retiming"],
                preconditions_satisfied=True,
                executable=True,
                plan_status="trial_ready",
                strategy_package="incremental_release",
                reason=reason or "核验通过后进入目标方向小步增绿试验",
            )
        # 高排队 + 低绿灯利用率且直接下游有余量时，继续“只观察不处置”并不能
        # 产生新的因果证据。将核验放进受控试运行：小步借绿、连续监测、自动回滚。
        # 这里的 executable 表示“可下发为限时试运行”，不是直接固化为正式方案。
        contract = _contract(
            decision_mode="incremental_release_trial",
            allowed=["conditional_incremental_release"],
            forbidden=["downstream_protection", "arterial_coordination", "aggressive_retiming"],
            preconditions_satisfied=True,
            executable=True,
            plan_status="trial_ready",
            strategy_package="incremental_release",
            reason=reason or "目标进口高排队、低绿灯利用率且下游有余量，建议立即开展小步增绿试运行",
        )
        contract["max_stage_change_ratio"] = 0.2
        return contract

    if mechanism == "upstream_arrival_shock":
        return _contract(
            decision_mode="upstream_coordination",
            allowed=["arterial_coordination", "incremental_release"],
            forbidden=["aggressive_retiming"],
            preconditions_satisfied=True,
            executable=True,
            plan_status="trial_ready",
            strategy_package="arterial_coordination",
            reason=reason or "上游冲击显著，需削峰并小步释放目标方向",
        )

    return _contract(
        decision_mode="verification_required",
        allowed=["verification_plan"],
        forbidden=[
            "incremental_release",
            "downstream_protection",
            "arterial_coordination",
            "aggressive_retiming",
            "conditional_incremental_release",
        ],
        preconditions_satisfied=False,
        executable=False,
        plan_status="requires_verification",
        strategy_package="downstream_protection",
        reason=reason or "证据不足，仅输出补证与核验任务",
    )


def _contract(
    *,
    decision_mode: str,
    allowed: list[str],
    forbidden: list[str],
    preconditions_satisfied: bool,
    executable: bool,
    plan_status: str,
    strategy_package: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "decision_mode": decision_mode,
        "allowed_plan_types": list(allowed),
        "forbidden_plan_types": list(forbidden),
        "preconditions_satisfied": preconditions_satisfied,
        "executable": executable,
        "plan_status": plan_status,
        "strategy_package": strategy_package,
        "reason": reason,
    }
