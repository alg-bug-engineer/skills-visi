"""溢出闭环顶层业务完成状态（区别于 pipeline_complete）。"""

from __future__ import annotations

from typing import Any


COMPLETION_STATUSES = (
    "completed_with_trial_plan",
    "completed_conditional",
    "completed_requires_verification",
    "completed_no_action",
    "failed",
)


def derive_completion_status(
    *,
    completed: bool,
    healthy: bool = False,
    decision: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
) -> str:
    if healthy:
        return "completed_no_action"
    if not completed:
        return "failed"

    decision = decision or {}
    plan = plan or {}
    recommended = plan.get("recommended") if isinstance(plan.get("recommended"), dict) else {}

    plan_status = (
        recommended.get("plan_status")
        or decision.get("plan_status")
        or plan.get("plan_status")
    )
    executable = recommended.get("executable")
    if executable is None:
        executable = decision.get("executable")
    decision_mode = decision.get("decision_mode") or plan.get("decision_mode")

    if plan_status == "requires_verification" or decision_mode == "verification_required":
        return "completed_requires_verification"
    if plan_status == "conditional" or (
        decision_mode == "verify_then_adjust" and executable is False
    ):
        return "completed_conditional"
    if plan_status == "trial_ready" and executable is True:
        return "completed_with_trial_plan"
    if executable is True and decision_mode in {
        "incremental_release",
        "incremental_release_trial",
        "downstream_protection",
        "upstream_coordination",
    }:
        return "completed_with_trial_plan"
    if decision_mode == "verify_then_adjust":
        return "completed_conditional"
    return "completed_with_trial_plan" if completed else "failed"


def build_trial_loop(
    *,
    decision: dict[str, Any] | None,
    diagnosis: dict[str, Any] | None,
    recommended: dict[str, Any] | None,
    ticket: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """试运行监测 / 成功判定 / 回滚结构化对象，供前端与反馈沉淀消费。"""
    decision = decision or {}
    diagnosis = diagnosis or {}
    recommended = recommended or {}
    ticket = ticket or {}
    downstream = diagnosis.get("downstream_state") or {}
    contract = recommended.get("plan_contract") or {}
    mechanism = (diagnosis.get("overflow_mechanism") or {}).get("primary")

    observation_cycles = int(
        contract.get("observation_cycles")
        or recommended.get("observation_cycles")
        or 5
    )
    monitoring = list(
        recommended.get("monitoring_metrics")
        or [
            "目标进口最大排队长度",
            "目标进口排队比",
            "目标方向每周期消散车辆数",
            "绿灯结束时剩余队列",
            "目标方向绿灯利用率",
            "直接下游排队长度",
            "直接下游排队比",
            "其他进口最大排队",
            "行人清空是否正常",
        ]
    )
    rollback_rules = list(
        recommended.get("rollback_rules")
        or [
            "直接下游排队持续增长",
            "目标方向有效绿增加后排队未改善",
            "其他进口排队逼近空间边界",
            "检测数据异常",
            "行人或安全约束异常",
        ]
    )
    if recommended.get("rollback_condition"):
        rollback_rules = [str(recommended["rollback_condition"]), *rollback_rules]

    system_prechecks = list(
        recommended.get("preconditions")
        or [
            "系统确认直接下游未达到排队红线",
            "系统确认现状配时与检测数据可用",
            "系统保存原方案用于一键回滚",
        ]
    )

    return {
        "plan_status": recommended.get("plan_status") or decision.get("plan_status"),
        "executable": bool(
            recommended.get("executable")
            if recommended.get("executable") is not None
            else decision.get("executable")
        ),
        "decision_mode": decision.get("decision_mode"),
        "mechanism": mechanism,
        "observation_cycles": observation_cycles,
        "monitoring_metrics": list(dict.fromkeys(monitoring)),
        "success_conditions": [
            "目标进口排队比明显下降",
            "目标队列每周期可正常消散",
            "直接下游排队未明显上升",
            "其他进口未形成新的高风险排队",
        ],
        "rollback_rules": list(dict.fromkeys(rollback_rules)),
        # 兼容旧前端字段，同时明确这些检查由系统在下发时完成，不再让用户先观察。
        "preconditions": system_prechecks,
        "system_prechecks": system_prechecks,
        "preconditions_satisfied": bool(decision.get("preconditions_satisfied")),
        "target_effective_green_delta_s": contract.get("target_effective_green_delta_s"),
        "cycle_delta_s": contract.get("cycle_delta_s", 0),
        "max_stage_change_ratio": contract.get("max_stage_change_ratio", 0.15),
        "direct_downstream_inter_id": downstream.get("direct_downstream_inter_id"),
        "direct_downstream_inter_name": downstream.get("direct_downstream_inter_name"),
        "target_label": f"{ticket.get('direction') or ''}{ticket.get('movement') or ''}".strip()
        or None,
        "feedback_record_template": {
            "mechanism": mechanism,
            "decision": decision.get("decision_mode"),
            "result": "accepted | rejected | rolled_back",
            "expert_comment": "",
        },
    }
