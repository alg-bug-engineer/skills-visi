"""单路口完整诊断包装（信控视角，无 LLM / 无 SSE）。

复用 backend 服务，按 orchestrator 的真实装配顺序串联：

    DataFetcher.fetch            指标骨架（饱和度 / 失衡 / 绿灯利用率 / 粒度）
    IntersectionCognition.fetch  认知（渠化 / 进口画像）
    TimingProfileService.build   配时画像（提供流量-绿信比 verdict，信控核心）
    ProblemEvidenceService.build 证据链
    SustainedMetricsService.build 持续性指标
    RuleEngine.diagnose_comprehensive  规则诊断（control_ceiling）
    FlowTimingGovernanceService.build  信控问题检测 + 治理建议

产出统一 ``IntersectionDiagnosis`` 字典。单路口任何子步骤异常都被隔离：
核心指标缺失 → ``has_data=False``；可选增强失败 → 记 ``data_quality_tags``，不抛出。
"""

from __future__ import annotations

import logging
from typing import Any

from intersection_agent.models.domain import NluResult, TimePeriod
from intersection_agent.services.data_fetcher import DataFetcher
from intersection_agent.services.flow_timing_governance_service import (
    FlowTimingGovernanceService,
)
from intersection_agent.services.intersection_cognition_service import (
    IntersectionCognitionService,
)
from intersection_agent.services.problem_evidence_service import ProblemEvidenceService
from intersection_agent.services.rule_engine import RuleEngine
from intersection_agent.services.sustained_metrics_service import SustainedMetricsService
from intersection_agent.services.timing_profile_service import TimingProfileService
from intersection_agent.utils.thresholds_loader import threshold_value

logger = logging.getLogger(__name__)

# 区域扫描时段 → (start, end, dow 识别用 label)。
# "白平峰" 用底层 label "平峰" 以命中工作日 day_of_week 过滤。
PERIOD_TIME_MAP: dict[str, tuple[str, str, str]] = {
    "早高峰": ("07:00", "09:00", "早高峰"),
    "白平峰": ("10:00", "11:00", "平峰"),
    "晚高峰": ("16:00", "18:00", "晚高峰"),
}

_SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1, "none": 0}


def _nlu_for_period(period: str) -> NluResult:
    start, end, label = PERIOD_TIME_MAP.get(period, ("07:00", "09:00", "早高峰"))
    return NluResult(
        time_period=TimePeriod(start=start, end=end, label=label),
        problem_type="congestion",
    )


def _max_severity(severities: list[str]) -> str:
    best = "none"
    for sev in severities:
        if _SEVERITY_RANK.get(sev, 0) > _SEVERITY_RANK.get(best, 0):
            best = sev
    return best


def _pressure_level(sat: float | None, sat_high: float, sat_over: float) -> str | None:
    if sat is None:
        return None
    if sat >= sat_over:
        return "高压"
    if sat >= sat_high:
        return "中压"
    if sat >= 0.6:
        return "中低压"
    return "低压"


def _control_ceiling(
    sat: float | None,
    detected_categories: set[str],
    sat_over: float,
    rule_ceiling: str | None,
) -> str:
    """信控改善上限：过饱和/工程冲突 → low；配时类问题 → high；其余 medium。"""
    if rule_ceiling == "low":
        return "low"
    if sat is not None and sat >= sat_over:
        return "low"
    if detected_categories & {"imbalance", "empty_green"}:
        return "high"
    return "medium"


async def diagnose_one(
    pool: Any,
    settings: Any,
    inter: dict[str, Any],
    period: str,
) -> dict[str, Any]:
    """对 ``(inter, period)`` 跑完整诊断，返回统一结果字典。"""
    inter_id = str(inter["inter_id"])
    inter_name = str(inter.get("inter_name") or inter_id)
    base = getattr(settings, "base", settings)
    nlu = _nlu_for_period(period)
    tags: list[str] = []

    result: dict[str, Any] = {
        "inter_id": inter_id,
        "inter_name": inter_name,
        "lon": inter.get("lon"),
        "lat": inter.get("lat"),
        "period": period,
        "scene_type": None,
        "pressure_level": None,
        "metrics": {"saturation_max": None, "unbalance_index": None, "green_utilization": None},
        "top_issues": [],
        "severity": "none",
        "control_improvement_ceiling": "medium",
        "governance_summary": "",
        "governance_actions": [],
        "match_verdict": "insufficient",
        "has_data": False,
        "data_quality_tags": tags,
    }

    # 1) 指标骨架 —— 缺失即视为该时段无数据。
    try:
        data = await DataFetcher(pool, base).fetch(inter_id, inter_name, nlu)
    except Exception as exc:  # noqa: BLE001
        logger.warning("diagnose_one data_fetch failed %s/%s: %s", inter_id, period, exc)
        tags.append("data_fetch_failed")
        return result

    if data.get("meta", {}).get("missing_dws_coverage"):
        tags.append("missing_dws_coverage")
        return result

    tf = data.get("traffic_flow") or {}
    ev = data.get("evaluation") or {}
    sat = tf.get("saturation_rate")
    if sat is None:
        sat = tf.get("turn_saturation_max")
    if sat is None:
        tags.append("no_saturation_metric")
        return result

    result["has_data"] = True
    result["metrics"] = {
        "saturation_max": _round(sat),
        "unbalance_index": _round(ev.get("imbalance_index")),
        "green_utilization": _round(ev.get("green_utilization")),
    }

    # 2) 认知（场景/压力画像，可选增强）
    try:
        cognition = await IntersectionCognitionService(pool, base).fetch(
            inter_id, inter_name, nlu
        )
        data["cognition"] = cognition
        result["scene_type"] = (cognition.get("intersection") or {}).get("inter_form") or "未知"
    except Exception as exc:  # noqa: BLE001
        logger.info("cognition failed %s: %s", inter_id, exc)
        tags.append("cognition_failed")
        result["scene_type"] = "未知"

    # 3) 配时画像 —— 提供流量-绿信比 verdict（信控视角核心）
    try:
        timing_profile = await TimingProfileService(pool, base).build(
            inter_id, nlu, data_payload=data
        )
        flow_green = timing_profile.get("flow_green_fit") or {}
        data["timing_profile"] = timing_profile
        data["timing"] = {
            "cycle_length": timing_profile.get("cycle_length"),
            "green_deficit_ratio_max": timing_profile.get("green_deficit_ratio_max"),
            "flow_green_verdict": flow_green.get("verdict"),
            "flow_green_tau": flow_green.get("spearman_tau"),
        }
    except Exception as exc:  # noqa: BLE001
        logger.info("timing_profile failed %s: %s", inter_id, exc)
        tags.append("timing_profile_failed")

    # 4) 证据链（可选增强）
    try:
        data["problem_evidence"] = await ProblemEvidenceService(pool, base).build(
            inter_id, inter_name, nlu, data_payload=data
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("problem_evidence failed %s: %s", inter_id, exc)
        tags.append("problem_evidence_failed")

    # 5) 持续性指标（可选增强）
    try:
        data["sustained_metrics"] = await SustainedMetricsService(pool, base).build(
            inter_id, nlu, data_payload=data
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("sustained_metrics failed %s: %s", inter_id, exc)
        tags.append("sustained_metrics_failed")

    # 6) 规则诊断（信控改善上限）
    rules = RuleEngine(base)
    rule_ceiling: str | None = None
    try:
        diagnosis = rules.diagnose_comprehensive(data)
        rule_ceiling = diagnosis.control_ceiling
    except Exception as exc:  # noqa: BLE001
        logger.info("rule_engine failed %s: %s", inter_id, exc)
        tags.append("rule_engine_failed")

    # 7) 信控治理（问题检测 + 治理建议）
    try:
        governance = FlowTimingGovernanceService(rules).build(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("governance failed %s: %s", inter_id, exc)
        tags.append("governance_failed")
        governance = {}

    detected = [p for p in (governance.get("problems") or []) if p.get("detected")]
    detected.sort(key=lambda p: _SEVERITY_RANK.get(p.get("severity", "none"), 0), reverse=True)
    detected_categories = {p.get("category") for p in detected}

    result["top_issues"] = [p["label"] for p in detected]
    result["severity"] = _max_severity([p.get("severity", "none") for p in detected])
    result["governance_summary"] = governance.get("summary") or ""
    result["governance_actions"] = [
        {
            "category": p.get("category"),
            "label": p.get("label"),
            "severity": p.get("severity"),
            "governance": p.get("governance"),
            "evidence": p.get("evidence") or [],
        }
        for p in detected
    ]
    result["match_verdict"] = governance.get("match_verdict") or "insufficient"
    for gap in governance.get("data_gaps") or []:
        if gap not in tags:
            tags.append(gap)

    sat_high = threshold_value("saturation", "high", default=0.80)
    sat_over = threshold_value("saturation", "oversaturation", default=0.90)
    result["pressure_level"] = _pressure_level(_round(sat), sat_high, sat_over)
    result["control_improvement_ceiling"] = _control_ceiling(
        _round(sat), detected_categories, sat_over, rule_ceiling
    )
    return result


def _round(value: Any, digits: int = 3) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None
