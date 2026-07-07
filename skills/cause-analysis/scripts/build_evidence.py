from __future__ import annotations

from typing import Any


def build_evidence(diagnosis: dict[str, Any]) -> dict[str, Any]:
    metrics = diagnosis.get("metrics", {})
    downstream = diagnosis.get("downstream_metrics", {})
    downstream_trace = diagnosis.get("downstream_trace", {})
    flow_trace = diagnosis.get("flow_trace", {})
    arterial = diagnosis.get("arterial_analysis", {})
    return {
        "target_queue_ratio": metrics.get("queue_ratio"),
        "target_saturation": metrics.get("saturation"),
        "target_green_utilization": metrics.get("green_utilization"),
        "downstream_queue_ratio": downstream.get("queue_ratio"),
        "downstream_saturation": downstream.get("saturation"),
        "downstream_intersections": [
            {
                "inter_id": n.get("inter_id"),
                "inter_name": n.get("inter_name"),
                "queue_ratio": (n.get("metrics") or {}).get("queue_storage_ratio_max"),
                "saturation": (n.get("metrics") or {}).get("saturation_rate"),
                "blocked": (n.get("capacity") or {}).get("blocked"),
            }
            for n in downstream_trace.get("adjacent_intersections", [])
        ],
        "upstream_entry_traces": flow_trace.get("entry_traces", []),
        "upstream_governance_hints": flow_trace.get("governance_hints", []),
        "arterial_summary": arterial.get("summary"),
        "need_upstream_metering": arterial.get("need_upstream_metering"),
        "need_downstream_dissipation_first": arterial.get("need_downstream_dissipation_first"),
        "downstream_release_answer": (diagnosis.get("downstream_diagnosis") or {}).get(
            "release_answer"
        ),
        "downstream_scenario": (diagnosis.get("downstream_diagnosis") or {}).get("scenario"),
        "downstream_narrative": (diagnosis.get("downstream_diagnosis") or {}).get("narrative"),
        "judgment_criteria": (diagnosis.get("downstream_diagnosis") or {}).get("judgment_criteria"),
        "bottleneck_type": diagnosis.get("bottleneck_analysis", {}).get("bottleneck_type"),
    }


def needs_arterial_coordination(diagnosis: dict[str, Any]) -> bool:
    arterial = diagnosis.get("arterial_analysis", {})
    if arterial.get("need_upstream_metering"):
        return True
    bottleneck = diagnosis.get("bottleneck_analysis", {})
    upstream = diagnosis.get("upstream_metrics", {})
    return (
        bottleneck.get("bottleneck_type") == "downstream_capacity"
        and upstream.get("arrival_intensity") == "high"
    )


def default_cause_ranking(diagnosis: dict[str, Any], llm_result: dict[str, Any]) -> list[dict[str, Any]]:
    bottleneck = diagnosis.get("bottleneck_analysis", {})
    downstream_nodes = diagnosis.get("downstream_trace", {}).get("adjacent_intersections", [])
    down_name = downstream_nodes[0].get("inter_name") if downstream_nodes else "下游信控节点"
    return [
        {
            "rank": 1,
            "cause": llm_result.get("primary_cause", f"{down_name}承接能力不足"),
            "role": "主因",
        },
        {"rank": 2, "cause": "东向西直行方向持续高饱和", "role": "次因"},
        {"rank": 3, "cause": "上游来车集中释放", "role": "诱因"},
    ]
