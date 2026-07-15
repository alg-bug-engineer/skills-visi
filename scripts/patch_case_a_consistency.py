#!/usr/bin/env python3
"""Patch Case A demo fixture for requirement 35 copy/field consistency."""

from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "frontend/src/mock/cases/case_a_demo_fixture.json"
DIRECT = "永绥路与齐音路路口"
WRONG = "奥体西路与解放东路路口"


def _load_adjust():
    path = ROOT / "skills/plan-generation/scripts/adjust_phase_timing.py"
    spec = importlib.util.spec_from_file_location("adjust_phase_timing", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def baseline_timing(timing: dict) -> dict:
    if not timing:
        return timing
    out = deepcopy(timing)
    stages = out.get("phase_stage_timing_list") or []
    for stage in stages:
        current = stage.get("current_timing") or {}
        if current:
            stage["optimized_timing"] = dict(current)
            stage["green_time_s"] = current.get("green_time_s", stage.get("green_time_s"))
        stage["green_delta_s"] = 0
        stage["stage_delta_s"] = 0
    current_cycle = out.get("current_cycle_s")
    out["cycle_s"] = current_cycle
    out["cycle_delta_s"] = 0
    out["verification_baseline"] = True
    out["timing_source"] = "baseline_no_change"
    return out


def build_proposed_timing(baseline: dict, ticket: dict | None = None) -> dict:
    """门控后拟实施：实际绿差摘要，写满阶段对照字段。"""
    adjust = _load_adjust()
    stages = deepcopy(baseline.get("phase_stage_timing_list") or [])
    signal = {"phase_stage_timing_list": stages}
    ticket = ticket or {"direction": "北向南", "movement": "直行"}
    instr = adjust.build_strategy_instruction({}, "conditional_incremental_release")
    result = adjust.adjust_phase_timing(
        signal=signal,
        strategy_instruction=instr,
        ticket=ticket,
        diagnosis={},
    )
    if not result.get("ok"):
        return {
            "available": False,
            "gate": "verification_passed",
            "label": "门控通过后拟实施",
            "reason": result.get("reason") or "未能生成拟实施借绿配时",
            "target_green_delta_s": 0,
            "donor_green_delta_s": 0,
            "cycle_delta_s": 0,
        }
    timing = result.get("timing") or {}
    # 保留现状 movements / atoms / saturation（adjust 已尽量带回）
    base_by_id = {
        (s.get("phase_stage_id") or i): s for i, s in enumerate(stages)
    }
    for i, row in enumerate(timing.get("phase_stage_timing_list") or []):
        key = row.get("phase_stage_id") if row.get("phase_stage_id") is not None else i
        base = base_by_id.get(key) or (stages[i] if i < len(stages) else {})
        for field in ("movements", "source_stage_atoms", "flow_combo", "phase_saturation", "phase_stage_name"):
            if row.get(field) is None and base.get(field) is not None:
                row[field] = base[field]
    return {
        **adjust.attach_proposed_timing_fields(
            timing,
            requested_target_green_delta=int(instr.get("target_green_delta") or 5),
        ),
        "meta": deepcopy(baseline.get("meta") or {}),
    }


def patch_candidate(candidate: dict) -> None:
    if candidate.get("plan_id") != "verification_plan":
        return
    if candidate.get("timing"):
        candidate["timing"] = baseline_timing(candidate["timing"])
    if candidate.get("cycle_s") is not None and candidate.get("timing", {}).get("current_cycle_s"):
        candidate["cycle_s"] = candidate["timing"]["current_cycle_s"]
    candidate["timing_source"] = "controlled_phase_borrow"
    if candidate.get("timing"):
        candidate["timing"] = build_proposed_timing(candidate["timing"])
        candidate["cycle_s"] = candidate["timing"].get("cycle_s")
    candidate.pop("proposed_timing", None)
    candidate.pop("proposed_timing_source", None)
    candidate["plan_id"] = "conditional_incremental_release"
    candidate["name"] = "小步增绿试运行方案"
    candidate["scenario"] = f"对北向南直行立即试行小步增绿，并同步监测{DIRECT}"
    candidate["expected_effect"] = "用 5 个周期验证并缓解目标进口排队，不加重下游拥堵"
    candidate["risk"] = "目标排队未改善或下游排队增长时自动回滚"
    candidate["execution_order"] = ["下发小步增绿", "连续监测目标与下游", "达标保留、异常回滚"]
    candidate["executable"] = True
    candidate["plan_status"] = "trial_ready"


def trial_signal_rows(timing: dict) -> list[dict]:
    rows: list[dict] = []
    for stage in timing.get("phase_stage_timing_list") or []:
        delta = int(stage.get("green_delta_s") or 0)
        if not delta:
            continue
        name = stage.get("phase_stage_name") or f"阶段{stage.get('phase_stage_id') or ''}"
        rows.append({
            "kind": "timing",
            "action": f"{name}绿灯 {'+' if delta > 0 else ''}{delta}s",
            "where": name,
            "green_delta_s": delta,
            "executable_now": True,
        })
    cycle_delta = int(timing.get("cycle_delta_s") or 0)
    rows.append({
        "kind": "timing",
        "action": f"信号周期 {'±0s' if cycle_delta == 0 else f'{cycle_delta:+d}s'}",
        "where": "解放东路与齐川路路口",
        "cycle_delta_s": cycle_delta,
        "executable_now": True,
    })
    rows.append({
        "kind": "monitor",
        "action": f"下发后试运行 5 个周期；{DIRECT}排队比>0.9 或目标排队未改善时自动回滚",
        "where": DIRECT,
    })
    return rows


def patch_action_packages(node, rows: list[dict]) -> None:
    if isinstance(node, list):
        for item in node:
            patch_action_packages(item, rows)
        return
    if not isinstance(node, dict):
        return
    schemes = node.get("schemes")
    if isinstance(schemes, dict) and "signal_control" in schemes:
        schemes["signal_control"] = deepcopy(rows)
        layers = node.get("layers")
        if isinstance(layers, dict):
            layers["proposed_timing"] = deepcopy([r for r in rows if r.get("kind") == "timing"])
        node["headline"] = "；".join(r["action"] for r in rows if r.get("kind") == "timing")
        node["execution_order"] = [r["action"] for r in rows]
        node["decision_mode"] = "incremental_release_trial"
    for value in node.values():
        patch_action_packages(value, rows)


def main() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cause = data.get("phases", {}).get("cause") or data.get("cause") or {}
    analysis = cause.get("cause_analysis") or {}
    analysis["primary_cause"] = "本路口放行过程异常"
    analysis["narrative"] = (
        "北向南直行排队比 0.9731、绿灯利用率 0.2731，呈现高排队、低有效放行。"
        f"直接下游 {DIRECT} 尚有 115m 蓄车空间，建议用 +5s 小步增绿试运行验证放行效果。"
    )
    analysis["cause_ranking"] = [
        {"rank": 1, "role": "主因", "cause": "本路口放行过程异常"},
        {"rank": 2, "role": "次因", "cause": "交通需求压力"},
        {"rank": 3, "role": "诱因", "cause": "通行供给不足"},
    ]
    analysis["data_gaps"] = [
        str(g).replace(WRONG, DIRECT) for g in (analysis.get("data_gaps") or [])
    ]
    cause["cause_ranking"] = analysis["cause_ranking"]
    cause["cause_analysis"] = analysis

    strategy = data.get("phases", {}).get("strategy") or data.get("strategy") or {}
    strategy["decision"] = {
        "decision_mode": "incremental_release_trial",
        "allowed_plan_types": ["conditional_incremental_release"],
        "forbidden_plan_types": ["downstream_protection", "arterial_coordination", "aggressive_retiming"],
        "preconditions_satisfied": True,
        "executable": True,
        "plan_status": "trial_ready",
        "strategy_package": "incremental_release",
        "reason": "目标进口高排队、低绿灯利用率且下游有余量，建议立即开展小步增绿试运行",
    }
    strategy["decision_mode"] = "incremental_release_trial"
    body = strategy.get("strategy") or {}
    body["recommended"] = [
        "立即试运行北向南直行有效绿 +5s，相位内借绿，周期保持不变",
        f"系统连续监测 5 个周期的目标排队与 {DIRECT} 排队",
        "目标排队未改善或下游排队比超过 0.9 时自动回滚",
    ]
    body["hard_constraints"] = [
        "本次目标阶段仅增加 5s，任一阶段调整幅度不得超过现状的 20%",
        "信号周期保持现状 224s，不得在本次试运行中延长",
        f"直接下游{DIRECT}排队比超过 0.9 时立即回滚",
        "所有优化动作须保留回退预案，确保30秒内可恢复原方案",
        "各机动车相位不得低于对应最小绿，黄灯、全红与行人清空时长保持不变",
        "单相位绿灯不得超过该阶段真实上限 116s",
        "现状周期高于配置上限 180s，需另案整改，不在本次小步试运行中扩大风险",
    ]
    body["principles"] = [
        "直接交付可回滚的试运行方案，不以人工核验代替系统处置",
        "目标流向有效绿 +5s（周期不变，相位内借绿），试运行 5 个周期",
        "系统监测目标与下游排队，达到红线立即恢复原方案",
    ]
    contrast = strategy.get("experience_contrast") or {}
    for item in contrast.get("items") or []:
        if item.get("dimension") == "策略选择":
            item["without_experience"] = {
                "summary": "仅依赖实时指标可能直接小步释放",
                "source": "package_scores",
            }
            item["with_experience"] = {
                **(item.get("with_experience") or {}),
                "summary": "小步增绿试运行 → 系统监测并自动回滚",
            }
        if item.get("dimension") == "成因判断":
            item["without_experience"] = {"summary": "信号控制不当", "source": "cause_scores"}
            item["with_experience"] = {
                **(item.get("with_experience") or {}),
                "summary": "本路口放行过程异常",
            }
        if item.get("dimension") == "下游承接":
            item["with_experience"] = {
                **(item.get("with_experience") or {}),
                "summary": "下游有余量，可开展小步试运行",
            }
    strategy["experience_contrast"] = contrast
    strategy["strategy"] = body

    plan = data.get("plan") or {}
    source = next((c for c in plan.get("candidates") or [] if c.get("plan_id") == "verification_plan"), None)
    source = deepcopy(source or plan.get("recommended") or {})
    patch_candidate(source)
    plan["candidates"] = [source]
    plan["recommended"] = deepcopy(source)
    plan["recommended_plan_id"] = "conditional_incremental_release"
    rec = plan.get("recommendation") or {}
    rec["rationale"] = (
        "北向南直行排队接近蓄车边界，当前绿灯有效利用率偏低，直接下游仍有承接空间。"
        "推荐立即试运行目标相位 +5s、借绿相位 -5s、周期不变。"
        f"下发后连续运行 5 个周期；目标排队未改善或 {DIRECT} 排队比超过 0.9 时自动回滚。"
    )
    rec["recommended_plan_id"] = "conditional_incremental_release"
    rec["execution_order"] = [
        "下发目标相位 +5s、借绿相位 -5s，周期不变",
        f"连续监测 5 个周期的目标进口与 {DIRECT}",
        "目标排队改善且下游稳定则保留，否则自动恢复原方案",
    ]
    plan["recommendation"] = rec
    plan["optimizer_engine"] = None
    plan["plan_status"] = "trial_ready"
    plan["executable"] = True
    loop = plan.get("trial_loop") or {}
    loop.update({
        "plan_status": "trial_ready",
        "executable": True,
        "decision_mode": "incremental_release_trial",
        "preconditions_satisfied": True,
        "target_effective_green_delta_s": 5,
        "cycle_delta_s": 0,
        "max_stage_change_ratio": 0.2,
        "system_prechecks": [
            "系统确认直接下游未达到排队红线",
            "系统确认现状配时与检测数据可用",
            "系统保存原方案用于一键回滚",
        ],
    })
    loop["rollback_rules"] = [
        f"{DIRECT}排队比超过 0.9 或持续增长",
        "目标进口排队在试运行后未改善",
        "其他进口排队逼近空间边界",
        "检测数据或行人安全约束异常",
    ]
    loop["feedback_record_template"]["decision"] = "incremental_release_trial"
    loop["preconditions"] = loop["system_prechecks"]
    plan["trial_loop"] = loop

    scenes = (
        data.get("phases", {}).get("diagnosis", {}).get("map_scenes")
        or data.get("phases", {}).get("intent", {}).get("spatial_scenes")
        or {}
    )
    if scenes.get("cause_spatial"):
        scenes["cause_spatial"]["primary_cause"] = "本路口放行过程异常"
    if scenes.get("plan_preview"):
        scenes["plan_preview"]["plan_id"] = "conditional_incremental_release"
        scenes["plan_preview"]["plan_name"] = "小步增绿试运行方案"
        scenes["plan_preview"]["cycle_delta_s"] = 0
        scenes["plan_preview"]["phase_changes"] = []

    diag = data.get("phases", {}).get("diagnosis") or {}
    dd = diag.get("downstream_diagnosis") or {}
    jc = dd.get("judgment_criteria") or {}
    jc["downstream_queue_high"] = False
    jc["downstream_near_saturation"] = False
    jc["add_green_spillback_risk"] = False
    dd["judgment_criteria"] = jc
    dd["release_answer"] = "下游有余量，可开展小步增绿试运行"
    dd["narrative"] = (
        "目标方向排队高但绿灯利用率不高，直接下游仍有承接空间。"
        "采用 +5s 小步增绿试运行，在运行中同步监测目标队列、出口通行和下游排队。"
    )
    diag["downstream_diagnosis"] = dd

    data["completion_status"] = "completed_with_trial_plan"
    patch_action_packages(data, trial_signal_rows(plan["recommended"]["timing"]))

    FIXTURE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Patched {FIXTURE}")


if __name__ == "__main__":
    main()
