"""LLM-based timing-period segmentation over pre-smoothed flow profiles."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np

from preprocessing.timing.period_segmentation import (
    SLOTS_PER_DAY,
    SLOT_MINUTES,
    SegmentationConfig,
    _adjacent_pair_metrics,
    _build_slot_profile,
    _config_to_dict,
    _constraint_checks,
    _evaluate_segment,
    _movement_series_kind,
    _public_period,
    _slot_to_time,
    _summary,
    build_flow_chart_payload,
    final_smooth_pass_field,
)

_PROMPT_PATH = (
    Path(__file__).resolve().parents[3] / "docs" / "period_segmentation_llm_prompt.md"
)


def build_period_segmentation_llm_input(
    flow_series: dict[str, Any],
    *,
    config: SegmentationConfig | None = None,
) -> dict[str, Any]:
    """Package twice-smoothed turn flows for LLM period segmentation."""

    cfg = config or SegmentationConfig()
    flow_chart = build_flow_chart_payload(flow_series, config=cfg)
    times = flow_chart.get("times") or [_slot_to_time(i) for i in range(SLOTS_PER_DAY)]
    series_items = flow_chart.get("series") or []
    smooth_field = final_smooth_pass_field(cfg)

    total = np.zeros(SLOTS_PER_DAY, dtype=float)
    compact_series: list[dict[str, Any]] = []
    for item in series_items:
        smooth = [
            round(float(v or 0.0), 1)
            for v in (item.get(smooth_field) or [])[:SLOTS_PER_DAY]
        ]
        if len(smooth) < SLOTS_PER_DAY:
            smooth = smooth + [0.0] * (SLOTS_PER_DAY - len(smooth))
        total += np.asarray(smooth, dtype=float)
        compact_series.append(
            {
                "label": item.get("label") or "",
                "dirName": item.get("dirName") or "",
                "turn": item.get("turn") or "through",
                "smoothedVph": smooth,
            }
        )

    cumulative = np.cumsum(total)
    return {
        "task": "period_segmentation",
        "interId": flow_series.get("interId"),
        "interName": flow_series.get("interName", ""),
        "date": flow_series.get("date"),
        "flowDateMeta": flow_series.get("flowDateMeta") or {},
        "intervalMinutes": int(flow_series.get("intervalMinutes") or SLOT_MINUTES),
        "slotCount": SLOTS_PER_DAY,
        "times": times[:SLOTS_PER_DAY],
        "preprocessing": {
            "smoothWindowMinutes": flow_chart.get("smoothWindowMinutes")
            or cfg.outlier_smooth_window_minutes,
            "smoothPasses": flow_chart.get("smoothPasses") or cfg.outlier_smooth_passes,
            "excludedTurns": ["right"],
            "seriesKind": _movement_series_kind(flow_series),
        },
        "aggregate": {
            "totalVph": [round(float(v), 1) for v in total.tolist()],
            "cumulativeFlow": [round(float(v), 1) for v in cumulative.tolist()],
        },
        "series": compact_series,
        "constraints": {
            "minPeriodMinutes": cfg.min_period_minutes,
            "maxPeriodMinutes": cfg.max_period_minutes,
            "minPeriods": cfg.min_periods,
            "maxPeriods": cfg.max_periods,
        },
    }


def segment_timing_periods_via_llm(
    flow_series: dict[str, Any],
    *,
    config: SegmentationConfig | None = None,
) -> dict[str, Any]:
    """Run LLM period segmentation and normalize to the standard result shape."""

    cfg = config or SegmentationConfig()
    llm_input = build_period_segmentation_llm_input(flow_series, config=cfg)
    llm_output = _call_llm_period_segmentation(llm_input)
    return normalize_llm_period_result(
        llm_output,
        flow_series,
        llm_input,
        config=cfg,
    )


def normalize_llm_period_result(
    llm_output: dict[str, Any],
    flow_series: dict[str, Any],
    llm_input: dict[str, Any],
    *,
    config: SegmentationConfig | None = None,
) -> dict[str, Any]:
    """Convert LLM JSON into the same envelope as ``segment_timing_periods``."""

    cfg = config or SegmentationConfig()
    profile = _build_slot_profile(flow_series, cfg)
    slot_periods = _llm_periods_to_slots(llm_output.get("periods") or [], cfg)
    evaluated_full = [
        _evaluate_segment(profile, start, end, cfg) for start, end in slot_periods
    ]
    for metric, llm_period in zip(evaluated_full, llm_output.get("periods") or [], strict=False):
        reason = llm_period.get("boundaryReason")
        if reason:
            metric["boundaryReason"] = str(reason)
        dominant = llm_period.get("dominantMovements")
        if isinstance(dominant, list) and dominant and isinstance(dominant[0], str):
            metric["dominantMovements"] = [
                {"movement": name, "meanVph": 0.0} for name in dominant
            ]

    evaluated = [_public_period(item) for item in evaluated_full]
    pair_metrics = _adjacent_pair_metrics(evaluated_full, cfg)
    constraints = _constraint_checks(evaluated, pair_metrics, cfg)
    llm_summary_text = str(llm_output.get("summary") or "").strip()
    result: dict[str, Any] = {
        "plan_type": "period_segmentation_llm",
        "engine": "llm",
        "interId": flow_series.get("interId") or llm_output.get("interId"),
        "interName": flow_series.get("interName") or llm_output.get("interName") or "",
        "date": flow_series.get("date") or llm_output.get("date"),
        "flowDateMeta": flow_series.get("flowDateMeta") or llm_input.get("flowDateMeta") or {},
        "sourceIntervalMinutes": flow_series.get("intervalMinutes"),
        "slotMinutes": SLOT_MINUTES,
        "seriesKind": profile["seriesKind"],
        "config": _config_to_dict(cfg),
        "llmInput": llm_input,
        "llmRaw": llm_output,
        "dataQuality": {
            "observedSlotCount": int(profile["observed"].sum()),
            "totalSlotCount": SLOTS_PER_DAY,
            "completeRate": round(float(profile["observed"].mean()), 4),
            "movementCount": len(profile["movementLabels"]),
            "approachCount": len(profile["movementLabels"]),
        },
        "periodCount": len(evaluated),
        "constraints": constraints,
        "periods": evaluated,
        "adjacentPairs": pair_metrics,
        "movementLabels": profile["movementLabels"],
        "flowChart": build_flow_chart_payload(flow_series, config=cfg),
    }
    result["summary"] = _summary(
        {
            "constraints": constraints,
            "periodCount": len(evaluated),
            "dataQuality": {
                "completeRate": round(float(profile["observed"].mean()), 4),
            },
        }
    )
    if llm_summary_text:
        result["summary"]["llmSummary"] = llm_summary_text
    return result


def _llm_periods_to_slots(
    periods: list[dict[str, Any]],
    cfg: SegmentationConfig,
) -> list[tuple[int, int]]:
    if not periods:
        raise ValueError("大模型未返回 periods")

    slot_bounds: list[tuple[int, int]] = []
    for item in periods:
        start = _time_to_slot(str(item.get("startTime") or "00:00"))
        end = _time_to_slot(str(item.get("endTime") or "24:00"))
        if end <= start:
            raise ValueError(f"无效时段：{item.get('startTime')}-{item.get('endTime')}")
        if end - start < cfg.min_slots:
            raise ValueError(
                f"时段过短（{item.get('startTime')}-{item.get('endTime')}），"
                f"最短 {cfg.min_period_minutes} 分钟"
            )
        slot_bounds.append((start, end))

    slot_bounds.sort(key=lambda pair: pair[0])
    if slot_bounds[0][0] != 0:
        raise ValueError("首个时段必须从 00:00 开始")
    if slot_bounds[-1][1] != SLOTS_PER_DAY:
        raise ValueError("末时段必须到 24:00 结束")
    for idx in range(len(slot_bounds) - 1):
        if slot_bounds[idx][1] != slot_bounds[idx + 1][0]:
            raise ValueError("时段之间存在空隙或重叠")
    if not (cfg.min_periods <= len(slot_bounds) <= cfg.max_periods):
        raise ValueError(
            f"时段数 {len(slot_bounds)} 不在允许范围 "
            f"{cfg.min_periods}..{cfg.max_periods}"
        )
    return slot_bounds


def _time_to_slot(time_text: str) -> int:
    text = str(time_text or "").strip()
    if text in {"24:00", "24:00:00"}:
        return SLOTS_PER_DAY
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", text)
    if not match:
        raise ValueError(f"无法解析时刻：{time_text}")
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour == 24 and minute == 0:
        return SLOTS_PER_DAY
    if hour > 23 or minute % SLOT_MINUTES != 0:
        raise ValueError(f"时刻须为 5 分钟对齐：{time_text}")
    return hour * (60 // SLOT_MINUTES) + minute // SLOT_MINUTES


def _load_prompt_rules() -> str:
    if not _PROMPT_PATH.is_file():
        raise RuntimeError(f"未找到提示词文档：{_PROMPT_PATH}")
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _call_llm_period_segmentation(llm_input: dict[str, Any]) -> dict[str, Any]:
    api_base = (os.getenv("LLM_API_BASE") or "").rstrip("/")
    api_key = os.getenv("LLM_API_KEY") or ""
    if not api_base or not api_key:
        raise RuntimeError("未配置 LLM_API_BASE / LLM_API_KEY，无法调用大模型")

    rules = _load_prompt_rules()
    user_prompt = (
        "请根据《信号配时时段划分》规则，对以下已预处理流量包划分配时时段。\n\n"
        "说明：\n"
        "- series[].smoothedVph 与 aggregate.totalVph 均已按配置完成多遍平滑，无需再处理\n"
        "- 严格按曲线特征切分，禁止使用固定时刻表\n"
        "- 仅输出 JSON，包含 interId、interName、date、periodCount、periods、summary\n"
        "- 每个时段除首段外，在 boundaryReason 中说明起点切分依据\n\n"
        f"流量数据：\n{json.dumps(llm_input, ensure_ascii=False)}"
    )
    payload = {
        "model": os.getenv("LLM_MODEL", "qwen-plus"),
        "messages": [
            {"role": "system", "content": rules},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.2")),
        "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "4096")),
    }
    req = urllib.request.Request(
        f"{api_base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    timeout = int(os.getenv("LLM_TIMEOUT_SEC", "120"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"大模型 API 错误 HTTP {exc.code}: {detail[:500]}") from exc
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, TimeoutError) as exc:
        raise RuntimeError(f"大模型调用失败: {exc}") from exc

    parsed = _extract_json_object(content)
    if not isinstance(parsed, dict):
        raise RuntimeError("大模型返回内容不是 JSON 对象")
    return parsed


def _extract_json_object(text: str) -> Any:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    if fenced:
        return json.loads(fenced.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("无法从模型输出中解析 JSON")
