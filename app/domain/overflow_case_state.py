"""溢出专用状态对象：Identity / evidence / mechanism / decision 全链路单一事实。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OverflowCaseState:
    identity: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    overflow_status: dict[str, Any] = field(default_factory=dict)
    downstream_state: dict[str, Any] = field(default_factory=dict)
    upstream_state: dict[str, Any] = field(default_factory=dict)
    discharge_state: dict[str, Any] = field(default_factory=dict)
    mechanism: dict[str, Any] = field(default_factory=dict)
    decision: dict[str, Any] = field(default_factory=dict)
    plan_contract: dict[str, Any] = field(default_factory=dict)
    plan_result: dict[str, Any] = field(default_factory=dict)
    case_status: str = "open"

    def freeze_identity_from_ticket(self, ticket: dict[str, Any]) -> None:
        ticket = ticket or {}
        downstream = self.downstream_state or {}
        self.identity = {
            "inter_id": ticket.get("inter_id"),
            "intersection_name": ticket.get("intersection_name"),
            "direction": ticket.get("direction"),
            "dir8_code": ticket.get("dir8_code"),
            "movement": ticket.get("movement"),
            "turn_dir_no": ticket.get("turn_dir_no"),
            "movement_key": (
                f"d{ticket['dir8_code']}_t{ticket['turn_dir_no']}"
                if ticket.get("dir8_code") is not None and ticket.get("turn_dir_no") is not None
                else ticket.get("movement_key")
            ),
            "time_window": ticket.get("time_window") or ticket.get("period"),
            "direct_downstream_inter_id": downstream.get("direct_downstream_inter_id"),
            "direct_downstream_inter_name": downstream.get("direct_downstream_inter_name"),
        }


def seed_overflow_state_from_artifacts(artifacts: dict[str, Any]) -> OverflowCaseState:
    state = OverflowCaseState()
    intent = artifacts.get("intent_understanding") or {}
    ticket = intent.get("diagnosis_ticket") or {}
    diagnosis = artifacts.get("data_analysis_diagnosis") or {}
    state.downstream_state = dict(diagnosis.get("downstream_state") or {})
    state.mechanism = dict(diagnosis.get("overflow_mechanism") or {})
    state.overflow_status = dict(diagnosis.get("overflow_verification") or {})
    state.upstream_state = dict(diagnosis.get("upstream_metrics") or {})
    state.freeze_identity_from_ticket(ticket)
    # 用诊断 target 补齐 identity
    target = diagnosis.get("target") or {}
    if state.identity.get("dir8_code") is None and target.get("dir8_code") is not None:
        state.identity["dir8_code"] = target.get("dir8_code")
    if state.identity.get("turn_dir_no") is None and target.get("turn_dir_no") is not None:
        state.identity["turn_dir_no"] = target.get("turn_dir_no")
    strategy = artifacts.get("strategy_generation") or {}
    if strategy.get("decision"):
        state.decision = dict(strategy["decision"])
    plan = artifacts.get("plan_generation") or {}
    if plan:
        state.plan_result = {
            "recommended_plan_id": (plan.get("recommended") or {}).get("plan_id"),
            "candidates": plan.get("candidates") or [],
        }
    return state


def update_overflow_state_after_skill(
    state: OverflowCaseState | None,
    *,
    skill_id: str,
    output: dict[str, Any],
    artifacts: dict[str, Any],
) -> OverflowCaseState:
    state = state or seed_overflow_state_from_artifacts(artifacts)
    if skill_id == "intent_understanding":
        state.freeze_identity_from_ticket(output.get("diagnosis_ticket") or {})
    elif skill_id == "data_analysis_diagnosis":
        state.downstream_state = dict(output.get("downstream_state") or state.downstream_state)
        state.mechanism = dict(output.get("overflow_mechanism") or state.mechanism)
        state.overflow_status = dict(output.get("overflow_verification") or state.overflow_status)
        state.upstream_state = dict(output.get("upstream_metrics") or state.upstream_state)
        ticket = (artifacts.get("intent_understanding") or {}).get("diagnosis_ticket") or {}
        state.freeze_identity_from_ticket(ticket)
    elif skill_id == "strategy_generation":
        if output.get("decision"):
            state.decision = dict(output["decision"])
    elif skill_id == "plan_generation":
        state.plan_result = {
            "recommended_plan_id": (output.get("recommended") or {}).get("plan_id"),
            "candidates": output.get("candidates") or [],
        }
        if state.decision.get("plan_status"):
            state.case_status = str(state.decision.get("plan_status"))
    return state
