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
    candidate["timing_source"] = "baseline_no_change"
    candidate["executable"] = False
    candidate["plan_status"] = "conditional"
    if candidate.get("timing"):
        candidate["proposed_timing"] = build_proposed_timing(candidate["timing"])
        candidate["proposed_timing_source"] = "conditional_incremental_release"


def main() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cause = data.get("phases", {}).get("cause") or data.get("cause") or {}
    analysis = cause.get("cause_analysis") or {}
    analysis["primary_cause"] = "放行效率异常，待核验"
    analysis["narrative"] = (
        "溢出机制为放行效率异常，待核验：排队比 0.9731 与绿灯利用率 0.2731 呈高排队低放行特征。"
        f"直接下游 {DIRECT} 初步有余量，需先完成出口/检测/绿灯末端队列核验，不宜在未核验前加绿。"
    )
    analysis["cause_ranking"] = [
        {"rank": 1, "role": "主因", "cause": "放行效率异常，待核验"},
        {"rank": 2, "role": "次因", "cause": "交通需求压力"},
        {"rank": 3, "role": "诱因", "cause": "通行供给不足"},
    ]
    analysis["data_gaps"] = [
        str(g).replace(WRONG, DIRECT) for g in (analysis.get("data_gaps") or [])
    ]
    cause["cause_ranking"] = analysis["cause_ranking"]
    cause["cause_analysis"] = analysis

    strategy = data.get("phases", {}).get("strategy") or data.get("strategy") or {}
    body = strategy.get("strategy") or {}
    body["recommended"] = [
        f"开展直接下游 {DIRECT} 出口通行与检测有效性核验",
        "记录绿灯末端目标队列是否仍残留，确认放行效率异常根因",
        "核验通过后再评估是否对北向南直行试行小步增绿（+5s，周期不变）",
        "联动监测直接下游排队比与剩余蓄车空间",
    ]
    body["hard_constraints"] = [
        f"任何配时调整不得导致下游{DIRECT}排队比超过0.9",
        "单次绿灯时长调整幅度不得超过原时长的15%",
        "未获取下游实时排队或饱和度数据前，禁止执行超过两轮的连续加绿操作",
        "所有优化动作须保留回退预案，确保30秒内可恢复原方案",
        "各相位最小绿不得低于 7s（含黄灯全红、行人过街清空）",
        "单相位绿灯不得超过 60s（最大绿上限）",
        "信号周期不得超过 180s（最大周期约束）",
    ]
    body["principles"] = [
        "先验后调：先核验出口/检测/绿灯末端队列，再决定是否小步增绿",
        "核验通过前维持现状配时，不直接改绿信比",
        "绿灯调节以目标有效绿微增为主，周期尽量不变，并监测直接下游排队比",
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
                "summary": "先验后调 → 核验通过后再小步增绿",
            }
        if item.get("dimension") == "成因判断":
            item["without_experience"] = {"summary": "信号控制不当", "source": "cause_scores"}
            item["with_experience"] = {
                **(item.get("with_experience") or {}),
                "summary": "放行效率异常，待核验",
            }
        if item.get("dimension") == "下游承接":
            item["with_experience"] = {
                **(item.get("with_experience") or {}),
                "summary": "放行效率异常，待核验",
            }
    strategy["experience_contrast"] = contrast
    strategy["strategy"] = body

    plan = data.get("plan") or {}
    for candidate in plan.get("candidates") or []:
        patch_candidate(candidate)
    if plan.get("recommended"):
        patch_candidate(plan["recommended"])
    rec = plan.get("recommendation") or {}
    rec["rationale"] = (
        "当前北向南直行处于溢出预警，直接下游具备承接余量，但放行效率异常尚未核验。"
        "推荐先验核验方案：维持现状配时，完成出口/检测/绿灯末端队列核验后再决定是否小步增绿。"
        f"监测窗口内重点关注 {DIRECT} 排队比，超过 0.9 即回滚。"
    )
    rec["execution_order"] = [
        f"核验 {DIRECT} 出口通行与剩余蓄车空间",
        "确认检测器有效性与绿灯末端目标队列",
        "连续观察 5 个周期后再评估条件性小步增绿",
        "触发回滚条件时立即恢复原方案",
    ]
    plan["recommendation"] = rec
    plan["optimizer_engine"] = None

    scenes = (
        data.get("phases", {}).get("diagnosis", {}).get("map_scenes")
        or data.get("phases", {}).get("intent", {}).get("spatial_scenes")
        or {}
    )
    if scenes.get("cause_spatial"):
        scenes["cause_spatial"]["primary_cause"] = "放行效率异常，待核验"
    if scenes.get("plan_preview"):
        scenes["plan_preview"]["plan_id"] = "verification_plan"
        scenes["plan_preview"]["plan_name"] = "先验核验方案"
        scenes["plan_preview"]["cycle_delta_s"] = 0
        scenes["plan_preview"]["phase_changes"] = []

    diag = data.get("phases", {}).get("diagnosis") or {}
    dd = diag.get("downstream_diagnosis") or {}
    jc = dd.get("judgment_criteria") or {}
    jc["downstream_queue_high"] = False
    jc["downstream_near_saturation"] = False
    jc["add_green_spillback_risk"] = False
    dd["judgment_criteria"] = jc
    dd["release_answer"] = "放行效率异常，待核验"
    dd["narrative"] = (
        "目标方向排队高但绿灯利用率不高，需优先核验出口通行、检测有效性与绿灯末端队列，"
        "不宜在未完成先验前简单加绿。"
    )
    diag["downstream_diagnosis"] = dd

    FIXTURE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Patched {FIXTURE}")


if __name__ == "__main__":
    main()
