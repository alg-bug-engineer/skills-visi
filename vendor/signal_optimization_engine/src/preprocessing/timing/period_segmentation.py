"""Automatic timing-period segmentation from 5-minute turn flow profiles.

Preprocesses raw flow with centered moving average (default
15-minute window, three passes), aggregates per-approach max-lane flow (excluding
right-turn lanes), then applies cumulative-flow piecewise linear fitting:
time on the x-axis, cumulative flow on the y-axis. Flow-rate changes appear as
slope changes; Douglas–Peucker recursively splits chord segments when
normalized deviation exceeds threshold.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from math import inf
from typing import Any

import numpy as np

SLOTS_PER_DAY = 288
SLOT_MINUTES = 5
DEFAULT_MIN_PERIOD_MINUTES = 15
DEFAULT_MIN_PERIODS = 3
DEFAULT_MAX_PERIODS = 15
DEFAULT_OUTLIER_SMOOTH_WINDOW_MINUTES = 15
DEFAULT_OUTLIER_SMOOTH_PASSES = 3


@dataclass(frozen=True)
class SegmentationConfig:
    """Cumulative-flow piecewise linear segmentation over denoised 5-minute profiles."""

    min_period_minutes: int = DEFAULT_MIN_PERIOD_MINUTES
    min_periods: int = DEFAULT_MIN_PERIODS
    max_periods: int = DEFAULT_MAX_PERIODS
    outlier_smooth_window_minutes: int = DEFAULT_OUTLIER_SMOOTH_WINDOW_MINUTES
    outlier_smooth_passes: int = DEFAULT_OUTLIER_SMOOTH_PASSES
    outlier_deviation_ratio: float = 1.0
    cumulative_deviation_threshold: float = 0.032
    movement_deviation_threshold: float = 0.04
    cumulative_rate_merge_threshold: float = 0.25
    level_change_threshold: float = 0.14
    structure_change_threshold: float = 0.16
    quiet_flow_vph: float = 700.0
    quiet_flow_absolute_gap_vph: float = 220.0
    boundary_window_minutes: int = 45
    uniform_flow_cv_threshold: float = 0.02
    total_flow_weight: float = 1.8
    structure_weight: float = 0.65
    elbow_weight: float = 0.55
    mutation_weight: float = 0.45
    min_relative_loss_drop: float = 0.015
    intra_weight: float = 1.0
    inter_weight: float = 1.25
    boundary_penalty: float = 0.32
    complexity_penalty: float = 0.28
    change_point_weight: float = 0.75
    low_flow_vph: float = 120.0
    low_flow_boundary_extra: float = 0.55
    merge_dissimilarity_threshold: float = 0.35
    heterogeneous_split_threshold: float = 0.42
    split_gain_threshold: float = 0.04
    merge_intra_degradation_tolerance: float = 0.08
    short_fragment_minutes: int = 30
    max_period_minutes: int = 240
    flow_level_deviation_threshold: float = 0.10
    long_period_merge_dissimilarity_threshold: float = 0.10
    short_boundary_window_minutes: int = 15
    dominant_abs_gap_vph: float = 120.0
    dominant_rel_gap: float = 0.18
    dominant_share_change_threshold: float = 0.04
    dominant_share_deviation_threshold: float = 0.035
    merge_structure_gap_ratio: float = 0.80
    compound_structure_gap_ratio: float = 0.75
    dominant_abs_gap_ratio: float = 0.10
    turn_mix_rel_gap: float = 0.35
    turn_mix_abs_gap_vph: float = 100.0
    internal_split_min_minutes: int = 90
    internal_compound_score_threshold: float = 0.85
    ramp_monotonic_score_factor: float = 0.35
    ramp_min_trend_vph: float = 8.0
    ramp_window_monotonic_fraction: float = 0.60
    ramp_structure_threshold_multiplier: float = 2.0
    ramp_turn_mix_structure_multiplier: float = 1.5
    inflection_half_window_slots: int = 3
    inflection_score_threshold: float = 0.30
    climb_boundary_cluster_slots: int = 12
    spike_bracket_max_minutes: int = 25
    spike_boundary_relocate_slots: int = 6

    @property
    def max_period_slots(self) -> int:
        return max(self.min_slots, -(-self.max_period_minutes // SLOT_MINUTES))

    @property
    def min_slots(self) -> int:
        return max(1, -(-self.min_period_minutes // SLOT_MINUTES))

    @property
    def short_fragment_slots(self) -> int:
        return max(self.min_slots, -(-self.short_fragment_minutes // SLOT_MINUTES))

    @property
    def outlier_smooth_slots(self) -> int:
        slots = max(1, round(self.outlier_smooth_window_minutes / SLOT_MINUTES))
        return slots if slots % 2 == 1 else slots + 1

    @property
    def boundary_window_slots(self) -> int:
        return max(self.min_slots, round(self.boundary_window_minutes / SLOT_MINUTES))

    @property
    def short_boundary_window_slots(self) -> int:
        return max(self.min_slots, round(self.short_boundary_window_minutes / SLOT_MINUTES))

    @property
    def internal_split_min_slots(self) -> int:
        return max(self.min_slots * 4, round(self.internal_split_min_minutes / SLOT_MINUTES))


def segment_timing_periods(
    flow_series: dict[str, Any],
    *,
    config: SegmentationConfig | None = None,
) -> dict[str, Any]:
    """Segment one full-day 5-minute turn-flow profile into timing periods."""

    cfg = config or SegmentationConfig()
    _validate_config(cfg)
    profile = _build_slot_profile(flow_series, cfg)
    segment_metrics = _precompute_segment_metrics(profile, cfg)
    periods, objective, k_selection = _solve_cumulative_piecewise(profile, segment_metrics, cfg)
    periods = _refine_cumulative_slope_splits(periods, profile, cfg)
    periods = _snap_period_boundaries(periods, profile, cfg)
    periods = _merge_similar_periods(periods, segment_metrics, cfg, profile=profile)
    periods = _absorb_short_fragments(periods, segment_metrics, cfg, profile=profile)
    periods = _merge_similar_periods(periods, segment_metrics, cfg, profile=profile)
    periods = _refine_long_period_splits(periods, profile, segment_metrics, cfg)
    periods = _refine_internal_compound_splits(periods, profile, cfg)
    periods = _snap_period_boundaries(periods, profile, cfg)
    periods = _refine_semantic_boundaries(periods, profile, segment_metrics, cfg)
    objective = sum(
        segment_metrics[(start, end)]["fisherLoss"]
        for start, end in periods
    )
    evaluated_periods_full = [segment_metrics[(start, end)] for start, end in periods]
    evaluated_periods = [_public_period(item) for item in evaluated_periods_full]
    pair_metrics = _adjacent_pair_metrics(evaluated_periods_full, cfg)
    baseline = _baseline_4_periods(segment_metrics, cfg)
    constraints = _constraint_checks(evaluated_periods, pair_metrics, cfg)
    result = {
        "plan_type": "period_segmentation",
        "interId": flow_series.get("interId"),
        "interName": flow_series.get("interName", ""),
        "date": flow_series.get("date"),
        "flowDateMeta": flow_series.get("flowDateMeta") or {},
        "sourceIntervalMinutes": flow_series.get("intervalMinutes"),
        "slotMinutes": SLOT_MINUTES,
        "seriesKind": profile["seriesKind"],
        "config": _config_to_dict(cfg),
        "dataQuality": {
            "observedSlotCount": int(profile["observed"].sum()),
            "totalSlotCount": SLOTS_PER_DAY,
            "completeRate": round(float(profile["observed"].mean()), 4),
            "movementCount": len(profile["movementLabels"]),
            "approachCount": len(profile["movementLabels"]),
        },
        "periodCount": len(evaluated_periods),
        "objective": round(objective, 6),
        "kSelection": k_selection,
        "constraints": constraints,
        "periods": evaluated_periods,
        "adjacentPairs": pair_metrics,
        "baseline": baseline,
        "movementLabels": profile["movementLabels"],
        "flowChart": build_flow_chart_payload(flow_series, config=cfg),
    }
    result["summary"] = _summary(result)
    return result


def _resolve_chart_series(flow_series: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn/lane-group series for charts: critical lane flow with movement labels."""
    lane_group_series = flow_series.get("laneGroupSeries") or []
    if lane_group_series:
        source = lane_group_series
    else:
        source = flow_series.get("series") or []
    return [
        item
        for item in source
        if str(item.get("turn") or "").lower() != "right"
        and (item.get("criticalVph") or item.get("totalVph"))
    ]


def _chart_series_label(item: dict[str, Any]) -> str:
    dir_name = str(item.get("dirName") or item.get("dir8No") or item.get("dir8Code") or "")
    turn = str(item.get("turn") or "through").lower()
    if turn == "approach":
        return _approach_label(item)
    if item.get("laneGroupId") or item.get("laneGroupKey"):
        turn_word = {"left": "左转", "through": "直行"}.get(
            turn,
            str(item.get("turnName") or turn),
        )
        return f"{dir_name}{turn_word}" if dir_name else turn_word
    return _movement_label(item)


def build_flow_chart_payload(
    flow_series: dict[str, Any],
    *,
    max_series: int = 16,
    config: SegmentationConfig | None = None,
) -> dict[str, Any]:
    """Compact critical-lane flow curves with direction/turn labels for HTML charts."""
    cfg = config or SegmentationConfig()
    chart_series = _resolve_chart_series(flow_series)
    times = flow_series.get("times") or [
        _slot_to_time(i) for i in range(SLOTS_PER_DAY)
    ]
    if len(times) < SLOTS_PER_DAY:
        times = list(times) + [_slot_to_time(i) for i in range(len(times), SLOTS_PER_DAY)]
    times = times[:SLOTS_PER_DAY]

    ranked: list[tuple[float, dict[str, Any]]] = []
    aggregate = np.zeros(SLOTS_PER_DAY, dtype=float)
    for item in chart_series:
        values = item.get("criticalVph") or []
        if len(values) < SLOTS_PER_DAY:
            values = list(values) + [None] * (SLOTS_PER_DAY - len(values))
        numeric = np.array([0.0 if v is None else float(v) for v in values[:SLOTS_PER_DAY]])
        mean_vph = float(numeric.mean())
        if mean_vph <= 0:
            continue
        turn = str(item.get("turn") or "through").lower()
        raw_series, smooth_layers = _series_smooth_layers(values, cfg)
        if smooth_layers:
            aggregate += np.asarray(smooth_layers[-1], dtype=float)
        else:
            aggregate += numeric
        series_entry: dict[str, Any] = {
            "label": _chart_series_label(item),
            "dir8Code": int(item.get("dir8Code") or item.get("dir8No") or 0),
            "dirName": str(item.get("dirName") or ""),
            "turn": turn,
            "turnName": str(
                item.get("displayTurnName") or item.get("turnName") or turn
            ),
            "criticalVph": raw_series,
        }
        for idx, layer in enumerate(smooth_layers, start=1):
            series_entry[smooth_pass_field(idx)] = layer
        ranked.append((mean_vph, series_entry))
    ranked.sort(key=lambda item: item[0], reverse=True)
    cumulative = np.cumsum(aggregate)
    result: dict[str, Any] = {
        "intervalMinutes": int(flow_series.get("intervalMinutes") or SLOT_MINUTES),
        "times": times,
        "aggregateTotalVph": [round(float(v), 1) for v in aggregate.tolist()],
        "cumulativeTotalFlow": [round(float(v), 1) for v in cumulative.tolist()],
        "smoothWindowMinutes": cfg.outlier_smooth_window_minutes,
        "smoothPasses": cfg.outlier_smooth_passes,
        "series": [item[1] for item in ranked[:max_series]],
    }
    from visualization.period_segmentation_report import chart_payload_y_max

    result["yMax"] = chart_payload_y_max(result)
    return result


def _validate_config(cfg: SegmentationConfig) -> None:
    if cfg.min_period_minutes < SLOT_MINUTES or cfg.min_period_minutes % SLOT_MINUTES != 0:
        raise ValueError("min_period_minutes 必须为 5 分钟的正整数倍")
    if cfg.outlier_smooth_window_minutes < SLOT_MINUTES:
        raise ValueError("outlier_smooth_window_minutes 必须不小于 5 分钟")
    if cfg.outlier_smooth_passes < 0:
        raise ValueError("outlier_smooth_passes 不能为负数")
    if cfg.outlier_deviation_ratio <= 0:
        raise ValueError("outlier_deviation_ratio 必须大于 0")
    if cfg.boundary_window_minutes < SLOT_MINUTES:
        raise ValueError("boundary_window_minutes 必须不小于 5 分钟")
    if cfg.short_boundary_window_minutes < SLOT_MINUTES:
        raise ValueError("short_boundary_window_minutes 必须不小于 5 分钟")
    if cfg.min_periods < 1:
        raise ValueError("min_periods 必须大于 0")
    if cfg.max_periods < cfg.min_periods:
        raise ValueError("max_periods 必须不小于 min_periods")


def _build_slot_profile(flow_series: dict[str, Any], cfg: SegmentationConfig) -> dict[str, Any]:
    interval = int(flow_series.get("intervalMinutes") or SLOT_MINUTES)
    if interval != SLOT_MINUTES:
        raise ValueError("配时时段划分需要 5 分钟粒度流量，请使用 intervalMinutes=5 的数据")

    approach_series = _resolve_movement_series(flow_series)
    vectors: list[list[float | None]] = []
    movement_labels: list[str] = []
    for item in approach_series:
        values = item.get("criticalVph") or item.get("totalVph") or []
        if len(values) < SLOTS_PER_DAY:
            values = list(values) + [None] * (SLOTS_PER_DAY - len(values))
        values = values[:SLOTS_PER_DAY]
        if not any(value is not None for value in values):
            continue
        vectors.append([_as_float(value) for value in values])
        movement_labels.append(_movement_series_label(item))

    if not vectors:
        raise ValueError("流量时序中没有可用于划分的进口关键车道序列")

    raw = np.array(vectors, dtype=float).T
    observed = ~np.isnan(raw).all(axis=1)
    filled = _fill_missing(raw)
    denoised = _moving_average_flow_matrix(
        filled,
        cfg.outlier_smooth_slots,
        cfg.outlier_smooth_passes,
    )
    total_vph = denoised.sum(axis=1)
    denominator = np.maximum(total_vph[:, None], 1.0)
    structure = denoised / denominator
    log_total = np.log1p(total_vph)
    feature = np.concatenate([log_total[:, None], structure], axis=1)
    feature = _zscore_rows(feature)
    feature[:, 0] *= cfg.total_flow_weight
    if feature.shape[1] > 1:
        feature[:, 1:] *= cfg.structure_weight
    boundary_scores = _boundary_change_scores(total_vph)
    raw_total_vph = filled.sum(axis=1)
    denoised_total_vph = denoised.sum(axis=1)
    raw_boundary_scores = _boundary_change_scores(raw_total_vph)
    movement_mean_vph = denoised.mean(axis=0)
    dominant_idx = int(np.argmax(movement_mean_vph))
    sorted_flow = np.sort(denoised, axis=1)
    dominant_share = denoised[:, dominant_idx] / np.maximum(total_vph, 1.0)
    dominant_gap = sorted_flow[:, -1] - sorted_flow[:, -2] if denoised.shape[1] > 1 else denoised[:, 0]
    return {
        "rawFlow": filled,
        "denoisedFlow": denoised,
        "flow": denoised,
        "feature": feature,
        "structure": structure,
        "totalVph": total_vph,
        "rawTotalVph": raw_total_vph,
        "denoisedTotalVph": denoised_total_vph,
        "movementMeanVph": movement_mean_vph,
        "dominantMovementIdx": dominant_idx,
        "dominantShare": dominant_share,
        "dominantGap": dominant_gap,
        "observed": observed,
        "movementLabels": movement_labels,
        "seriesKind": _movement_series_kind(flow_series),
        "globalMeanVph": float(total_vph.mean()),
        "globalStdVph": float(max(total_vph.std(), 1.0)),
        "boundaryScores": boundary_scores,
        "rawBoundaryScores": raw_boundary_scores,
    }


def _as_float(value: Any) -> float:
    if value is None:
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _fill_missing(raw: np.ndarray) -> np.ndarray:
    filled = raw.copy()
    x = np.arange(filled.shape[0])
    for col in range(filled.shape[1]):
        values = filled[:, col]
        mask = ~np.isnan(values)
        if not mask.any():
            filled[:, col] = 0.0
        elif mask.sum() == 1:
            filled[:, col] = values[mask][0]
        else:
            filled[:, col] = np.interp(x, x[mask], values[mask])
    return np.nan_to_num(filled, nan=0.0)


def _smooth_flow_matrix(values: np.ndarray, window_slots: int) -> np.ndarray:
    """Centered moving average; edge padding avoids artificial start/end dips."""
    if window_slots <= 1:
        return values.copy()
    kernel = np.ones(window_slots, dtype=float) / window_slots
    pad_left = window_slots // 2
    pad_right = window_slots - 1 - pad_left
    padded = np.pad(values, ((pad_left, pad_right), (0, 0)), mode="edge")
    smoothed = np.empty_like(values, dtype=float)
    for col in range(values.shape[1]):
        smoothed[:, col] = np.convolve(padded[:, col], kernel, mode="valid")
    return smoothed


def _moving_average_flow_matrix(
    values: np.ndarray,
    window_slots: int,
    passes: int,
) -> np.ndarray:
    """Apply centered moving average ``passes`` times."""
    if passes <= 0 or window_slots <= 1:
        return values.copy()
    result = values.copy()
    for _ in range(passes):
        result = _smooth_flow_matrix(result, window_slots)
    return result


def smooth_pass_field(pass_index: int) -> str:
    return f"smoothPass{pass_index}Vph"


def final_smooth_pass_field(cfg: SegmentationConfig) -> str:
    return smooth_pass_field(max(1, cfg.outlier_smooth_passes))


def _series_smooth_layers(
    values: list[float | None],
    cfg: SegmentationConfig,
) -> tuple[list[float | None], list[list[float]]]:
    padded = list(values) + [None] * (SLOTS_PER_DAY - len(values))
    padded = padded[:SLOTS_PER_DAY]
    column = np.array([[_as_float(value)] for value in padded])
    filled = _fill_missing(column)
    current = filled
    smooth_layers: list[list[float]] = []
    for _ in range(cfg.outlier_smooth_passes):
        current = _smooth_flow_matrix(current, cfg.outlier_smooth_slots)
        smooth_layers.append([round(float(value), 1) for value in current[:, 0]])
    raw_series = [
        None if value is None else round(float(value), 1)
        for value in padded
    ]
    return raw_series, smooth_layers


def _boundary_change_scores(total_vph: np.ndarray) -> np.ndarray:
    """Relative flow jump at each 5-minute boundary (index = start slot of right segment)."""
    scores = np.zeros(SLOTS_PER_DAY, dtype=float)
    for slot in range(1, SLOTS_PER_DAY):
        prev = float(total_vph[slot - 1])
        curr = float(total_vph[slot])
        scores[slot] = abs(curr - prev) / max(min(prev, curr), 20.0)
    return np.clip(scores, 0.0, 6.0)


def _zscore_rows(values: np.ndarray) -> np.ndarray:
    mean = values.mean(axis=0)
    std = values.std(axis=0)
    std = np.where(std < 1e-6, 1.0, std)
    return (values - mean) / std


def _movement_label(item: dict[str, Any]) -> str:
    parts = [
        str(item.get("dirName") or item.get("dir8No") or item.get("dir8Code") or ""),
        str(item.get("displayTurnName") or item.get("turnName") or item.get("turn") or ""),
    ]
    label = "".join(part for part in parts if part)
    return label or str(item.get("laneGroupId") or item.get("laneGroupKey") or "movement")


def _approach_label(item: dict[str, Any]) -> str:
    dir_name = str(item.get("dirName") or item.get("dir8No") or item.get("dir8Code") or "")
    suffix = str(item.get("displayTurnName") or item.get("turnName") or "关键车道")
    label = f"{dir_name}{suffix}" if dir_name else suffix
    return label or "进口关键车道"


def _build_approach_series_from_movements(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fallback: per-approach max critical-lane flow from turn or lane-group series."""
    grouped: dict[int, list[dict[str, Any]]] = {}
    dir_names: dict[int, str] = {}
    for item in items:
        if str(item.get("turn") or "").lower() == "right":
            continue
        dir8_no = int(item.get("dir8Code") or item.get("dir8No") or 0)
        grouped.setdefault(dir8_no, []).append(item)
        if item.get("dirName"):
            dir_names[dir8_no] = str(item["dirName"])

    approach_items: list[dict[str, Any]] = []
    for dir8_no in sorted(grouped):
        members = grouped[dir8_no]
        critical_series: list[float | None] = []
        for slot in range(SLOTS_PER_DAY):
            slot_values: list[float] = []
            observed_any = False
            for member in members:
                series = member.get("criticalVph") or []
                if slot >= len(series):
                    continue
                observed_any = True
                value = series[slot]
                if value is not None:
                    slot_values.append(float(value))
            if not observed_any:
                critical_series.append(None)
            elif slot_values:
                critical_series.append(max(slot_values))
            else:
                critical_series.append(0.0)
        approach_items.append(
            {
                "dir8Code": dir8_no,
                "dir8No": dir8_no,
                "dirName": dir_names.get(dir8_no, str(dir8_no)),
                "turn": "approach",
                "turnName": "关键车道",
                "displayTurnName": "进口关键车道",
                "criticalVph": critical_series,
            }
        )
    return approach_items


def _movement_series_label(item: dict[str, Any]) -> str:
    if str(item.get("turn") or "").lower() == "approach":
        return _approach_label(item)
    dir_name = str(item.get("dirName") or item.get("dir8No") or item.get("dir8Code") or "")
    turn = str(item.get("turn") or "through").lower()
    turn_word = str(item.get("displayTurnName") or item.get("turnName") or turn)
    if turn in {"left", "through", "right"}:
        turn_word = {"left": "左转", "through": "直行", "right": "右转"}.get(turn, turn_word)
    label = f"{dir_name}{turn_word}" if dir_name else turn_word
    if item.get("laneGroupId") or item.get("laneGroupKey"):
        return label or str(item.get("laneGroupId") or item.get("laneGroupKey"))
    return label or _movement_label(item)


def _movement_series_kind(flow_series: dict[str, Any]) -> str:
    if flow_series.get("laneGroupSeries"):
        return "laneGroupSeries"
    if flow_series.get("series"):
        return "turnSeries"
    if flow_series.get("approachSeries"):
        return "approachSeries"
    return "approachSeries"


def _eligible_movement_item(item: dict[str, Any]) -> bool:
    if str(item.get("turn") or "").lower() == "right":
        return False
    values = item.get("criticalVph") or item.get("totalVph") or []
    return bool(values)


def _resolve_movement_series(flow_series: dict[str, Any]) -> list[dict[str, Any]]:
    """Prefer lane-group / turn series so within-approach mix shifts remain visible."""

    lane_group_series = flow_series.get("laneGroupSeries") or []
    if lane_group_series:
        items = [item for item in lane_group_series if _eligible_movement_item(item)]
        if items:
            return items
    turn_series = flow_series.get("series") or []
    if turn_series:
        items = [item for item in turn_series if _eligible_movement_item(item)]
        if items:
            return items
    return _resolve_approach_series(flow_series)


def _resolve_approach_series(flow_series: dict[str, Any]) -> list[dict[str, Any]]:
    approach_series = flow_series.get("approachSeries") or []
    if approach_series:
        return approach_series
    lane_group_series = flow_series.get("laneGroupSeries") or []
    if lane_group_series:
        return _build_approach_series_from_movements(lane_group_series)
    turn_series = flow_series.get("series") or []
    if turn_series:
        return _build_approach_series_from_movements(turn_series)
    return []


def _precompute_segment_metrics(
    profile: dict[str, Any],
    cfg: SegmentationConfig,
) -> dict[tuple[int, int], dict[str, Any]]:
    metrics: dict[tuple[int, int], dict[str, Any]] = {}
    for start in range(SLOTS_PER_DAY):
        min_end = start + cfg.min_slots
        if min_end > SLOTS_PER_DAY:
            break
        for end in range(min_end, SLOTS_PER_DAY + 1):
            metrics[(start, end)] = _evaluate_segment(profile, start, end, cfg)
    return metrics


def _evaluate_segment(
    profile: dict[str, Any],
    start: int,
    end: int,
    cfg: SegmentationConfig,
) -> dict[str, Any]:
    features = profile["feature"][start:end]
    structure = profile["structure"][start:end]
    total = profile["totalVph"][start:end]
    observed = profile["observed"][start:end]
    centroid = features.mean(axis=0)
    cohesion = float(np.linalg.norm(features - centroid, axis=1).mean()) if len(features) else 0.0
    total_mean = float(total.mean()) if len(total) else 0.0
    intra_flow_std = float(total.std()) if len(total) else 0.0
    global_std = float(profile.get("globalStdVph") or 1.0)
    intra_flow_std_norm = intra_flow_std / global_std
    structure_mean = structure.mean(axis=0)
    structure_center = structure.mean(axis=0)
    structure_l1 = float(np.abs(structure - structure_center).sum(axis=1).mean()) if len(structure) else 0.0
    adjacent_change = _max_adjacent_change(total)
    intra_cost = (
        0.75 * min(intra_flow_std_norm, 2.5)
        + 0.10 * min(cohesion, 3.0)
        + 0.10 * min(structure_l1, 2.0)
        + 0.05 * min(adjacent_change, 3.0)
    )
    fisher_loss = _fisher_segment_loss(features)
    intra_similarity = 1.0 / (1.0 + intra_flow_std_norm)
    objective = cfg.intra_weight * intra_cost

    return {
        "startSlot": start,
        "endSlot": end,
        "startTime": _slot_to_time(start),
        "endTime": _slot_to_time(end),
        "durationMinutes": (end - start) * SLOT_MINUTES,
        "observedSlotCount": int(observed.sum()),
        "centroid": centroid,
        "structureMean": structure_mean,
        "intraFlowStd": round(intra_flow_std, 2),
        "intraFlowStdNorm": round(intra_flow_std / max(total_mean, 1.0), 4),
        "intraFlowStdGlobalNorm": round(intra_flow_std_norm, 4),
        "intraCost": round(intra_cost, 4),
        "intraSimilarity": round(intra_similarity, 4),
        "cohesion": round(cohesion, 4),
        "meanTotalVph": round(total_mean, 2),
        "peakTotalVph": round(float(total.max()) if len(total) else 0.0, 2),
        "cv": round(intra_flow_std / max(total_mean, 1.0), 4),
        "structureL1": round(structure_l1, 4),
        "maxAdjacentChange": round(adjacent_change, 4),
        "dominantMovements": _dominant_movements(profile, start, end),
        "fisherLoss": float(fisher_loss),
        "objective": float(objective),
    }


def _fisher_segment_loss(features: np.ndarray) -> float:
    if len(features) <= 1:
        return 0.0
    center = features.mean(axis=0)
    return float(np.square(features - center).sum())


def _inter_dissimilarity(
    left: dict[str, Any],
    right: dict[str, Any],
    cfg: SegmentationConfig,
) -> float:
    mean_left = float(left.get("meanTotalVph") or 0.0)
    mean_right = float(right.get("meanTotalVph") or 0.0)
    abs_gap = abs(mean_left - mean_right)
    if max(mean_left, mean_right) < cfg.quiet_flow_vph:
        return min(abs_gap / max(cfg.quiet_flow_absolute_gap_vph, 1.0), 6.0)
    flow_gap = abs(mean_left - mean_right) / max(min(mean_left, mean_right), cfg.low_flow_vph * 0.5)
    flow_gap = min(flow_gap, 6.0)
    if mean_left < cfg.low_flow_vph and mean_right < cfg.low_flow_vph:
        return flow_gap
    feature_gap = _centroid_distance(left, right)
    structure_gap = float(
        np.linalg.norm(left.get("structureMean", 0.0) - right.get("structureMean", 0.0))
    )
    return 0.70 * flow_gap + 0.18 * feature_gap + 0.12 * min(structure_gap, 2.0)


def _centroid_distance(left: dict[str, Any], right: dict[str, Any]) -> float:
    return float(np.linalg.norm(left["centroid"] - right["centroid"]))


def _max_adjacent_change(values: np.ndarray) -> float:
    if len(values) < 2:
        return 0.0
    prev = values[:-1]
    curr = values[1:]
    return float(np.max(np.abs(curr - prev) / np.maximum(prev, 1.0)))


def _dominant_movements(profile: dict[str, Any], start: int, end: int, limit: int = 3) -> list[dict[str, Any]]:
    flow = profile["flow"][start:end]
    means = flow.mean(axis=0)
    order = np.argsort(means)[::-1][:limit]
    return [
        {"movement": profile["movementLabels"][idx], "meanVph": round(float(means[idx]), 2)}
        for idx in order
        if means[idx] > 0
    ]


def _normalized_cumulative_coords(total_vph: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Map slot index and cumulative flow to [0, 1] for scale-invariant deviation."""
    cum = np.cumsum(total_vph)
    n = len(cum)
    x = np.arange(n, dtype=float) / max(n - 1, 1)
    y = cum / max(float(cum[-1]), 1.0)
    return x, y


def _normalized_flow_coords(total_vph: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Map slot index and instantaneous flow to [0, 1] for long-period level splits."""
    n = len(total_vph)
    x = np.arange(n, dtype=float) / max(n - 1, 1)
    y = total_vph / max(float(total_vph.max()), 1.0)
    return x, y


def _perpendicular_distance(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    x: float,
    y: float,
) -> float:
    dx = x1 - x0
    dy = y1 - y0
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-18:
        return math.hypot(x - x0, y - y0)
    return abs(dy * (x - x0) - dx * (y - y0)) / math.sqrt(length_sq)


def _douglas_peucker_breakpoints(
    total_vph: np.ndarray,
    min_slots: int,
    deviation_threshold: float,
) -> list[int]:
    """Recursively split cumulative-flow chords at the largest normalized deviation."""

    n = len(total_vph)
    if n <= 1:
        return [0, n]
    x, y = _normalized_cumulative_coords(total_vph)
    breakpoints: set[int] = {0, n}

    def recurse(start: int, end: int) -> None:
        """Split slot range [start, end) using cumulative-flow chord deviation."""
        if end - start < 2 * min_slots:
            return
        left_idx = start
        right_idx = end - 1
        x0, y0 = float(x[left_idx]), float(y[left_idx])
        x1, y1 = float(x[right_idx]), float(y[right_idx])
        seg_len = math.hypot(x1 - x0, y1 - y0)
        if seg_len < 1e-12:
            return
        best_split: int | None = None
        best_dev = 0.0
        for split in range(start + min_slots, end - min_slots + 1):
            probe = split - 1
            if probe <= left_idx or probe >= right_idx:
                continue
            dev = _perpendicular_distance(
                x0,
                y0,
                x1,
                y1,
                float(x[probe]),
                float(y[probe]),
            )
            norm_dev = dev / seg_len
            if norm_dev > best_dev:
                best_dev = norm_dev
                best_split = split
        if best_split is not None and best_dev > deviation_threshold:
            breakpoints.add(best_split)
            recurse(start, best_split)
            recurse(best_split, end)

    recurse(0, n)
    return sorted(breakpoints)


def _structure_mean_l1_gap(left: dict[str, Any], right: dict[str, Any]) -> float:
    return float(
        np.abs(
            np.asarray(left.get("structureMean", 0.0), dtype=float)
            - np.asarray(right.get("structureMean", 0.0), dtype=float)
        ).sum()
    )


def _window_monotonic_trend(
    segment: np.ndarray,
    cfg: SegmentationConfig,
) -> tuple[bool, float]:
    """Return whether a window is mostly one-directional and its mean step change."""

    diffs = np.diff(segment)
    if len(diffs) == 0:
        return False, 0.0
    min_step = cfg.ramp_min_trend_vph
    up = int((diffs >= min_step).sum())
    down = int((diffs <= -min_step).sum())
    strong = up + down
    if strong == 0:
        return False, 0.0
    if up >= down and up / len(diffs) >= cfg.ramp_window_monotonic_fraction:
        return True, float(diffs[diffs >= min_step].mean())
    if down > up and down / len(diffs) >= cfg.ramp_window_monotonic_fraction:
        return True, float(diffs[diffs <= -min_step].mean())
    return False, 0.0


def _ramp_monotonic_context(
    total: np.ndarray,
    left_start: int,
    slot: int,
    right_end: int,
    cfg: SegmentationConfig,
) -> dict[str, Any]:
    """Detect whether left/right windows sit on the same monotonic ramp (both rising or falling)."""

    left_segment = total[left_start:slot]
    right_segment = total[slot:right_end]
    if len(left_segment) < 2 or len(right_segment) < 2:
        return {"isRamp": False, "direction": None, "leftTrendVph": 0.0, "rightTrendVph": 0.0}

    left_mono, left_trend = _window_monotonic_trend(left_segment, cfg)
    right_mono, right_trend = _window_monotonic_trend(right_segment, cfg)
    same_direction = left_trend * right_trend > 0.0
    direction: str | None = None
    if left_mono and right_mono and same_direction:
        direction = "up" if left_trend > 0.0 else "down"
    left_total = float(left_segment.mean())
    right_total = float(right_segment.mean())
    consistent_level = (
        direction == "up" and right_total >= left_total
    ) or (
        direction == "down" and right_total <= left_total
    )
    is_ramp = direction is not None and consistent_level
    return {
        "isRamp": is_ramp,
        "direction": direction,
        "leftTrendVph": round(left_trend, 2),
        "rightTrendVph": round(right_trend, 2),
    }


def _boundary_window_evidence(
    profile: dict[str, Any],
    slot: int,
    window_slots: int,
    cfg: SegmentationConfig,
    *,
    apply_ramp_penalty: bool = False,
) -> dict[str, Any]:
    """Compare mean flow/structure in ``window_slots`` immediately left vs right of ``slot``."""
    flow = profile["flow"]
    structure = profile["structure"]
    total = profile["totalVph"]
    dominant_idx = int(profile["dominantMovementIdx"])
    left_start = max(0, slot - window_slots)
    right_end = min(len(total), slot + window_slots)
    if slot - left_start < cfg.min_slots or right_end - slot < cfg.min_slots:
        return {"pass": False, "score": 0.0}

    left_total = float(total[left_start:slot].mean())
    right_total = float(total[slot:right_end].mean())
    total_abs_gap = abs(left_total - right_total)
    total_rel_gap = total_abs_gap / max(min(left_total, right_total), cfg.low_flow_vph)

    left_flow = flow[left_start:slot].mean(axis=0)
    right_flow = flow[slot:right_end].mean(axis=0)
    movement_abs_gap = float(np.max(np.abs(left_flow - right_flow))) if len(left_flow) else 0.0
    movement_rel_gap = float(
        np.max(np.abs(left_flow - right_flow) / np.maximum(np.minimum(left_flow, right_flow), cfg.low_flow_vph))
    ) if len(left_flow) else 0.0

    left_structure = structure[left_start:slot].mean(axis=0)
    right_structure = structure[slot:right_end].mean(axis=0)
    structure_gap = float(np.abs(left_structure - right_structure).sum())

    left_dom = float(left_flow[dominant_idx]) if len(left_flow) else 0.0
    right_dom = float(right_flow[dominant_idx]) if len(right_flow) else 0.0
    dominant_abs_gap = abs(left_dom - right_dom)
    dominant_rel_gap = dominant_abs_gap / max(min(left_dom, right_dom), cfg.low_flow_vph)

    dominant_share = profile.get("dominantShare")
    share_gap = 0.0
    if dominant_share is not None and len(dominant_share) >= right_end:
        left_share = float(dominant_share[left_start:slot].mean())
        right_share = float(dominant_share[slot:right_end].mean())
        share_gap = abs(left_share - right_share)

    local_peak = max(left_total, right_total, left_dom, right_dom)
    quiet = local_peak < cfg.quiet_flow_vph
    quiet_noise = (
        quiet
        and total_abs_gap < cfg.quiet_flow_absolute_gap_vph
        and movement_abs_gap < cfg.quiet_flow_absolute_gap_vph * 0.75
        and structure_gap < cfg.structure_change_threshold * 1.5
    )
    ramp = _ramp_monotonic_context(total, left_start, slot, right_end, cfg)
    total_rel_score = total_rel_gap / max(cfg.level_change_threshold, 1e-9)
    movement_rel_score = movement_rel_gap / max(cfg.cumulative_rate_merge_threshold, 1e-9)
    if apply_ramp_penalty and ramp.get("isRamp"):
        total_rel_score *= cfg.ramp_monotonic_score_factor
        movement_rel_score *= cfg.ramp_monotonic_score_factor
    score = max(
        total_rel_score,
        structure_gap / max(cfg.structure_change_threshold, 1e-9),
        movement_rel_score,
        dominant_rel_gap / max(cfg.dominant_rel_gap, 1e-9),
        share_gap / max(cfg.dominant_share_change_threshold, 1e-9),
    )
    level_pass = (
        total_abs_gap >= cfg.quiet_flow_absolute_gap_vph
        and total_rel_gap >= cfg.level_change_threshold
    )
    movement_level_pass = (
        movement_abs_gap >= cfg.quiet_flow_absolute_gap_vph
        and movement_rel_gap >= cfg.cumulative_rate_merge_threshold
    )
    if apply_ramp_penalty and ramp.get("isRamp"):
        level_pass = False
        movement_level_pass = False
    structure_threshold = cfg.structure_change_threshold
    if apply_ramp_penalty and ramp.get("isRamp"):
        structure_threshold *= cfg.ramp_structure_threshold_multiplier
    turn_mix_structure_min = cfg.structure_change_threshold * 0.50
    if apply_ramp_penalty and ramp.get("isRamp"):
        turn_mix_structure_min = cfg.structure_change_threshold * cfg.ramp_turn_mix_structure_multiplier
    passed = not quiet_noise and (
        level_pass
        or (
            structure_gap >= structure_threshold
            and local_peak >= cfg.quiet_flow_vph
        )
        or movement_level_pass
        or (
            movement_rel_gap >= cfg.turn_mix_rel_gap
            and movement_abs_gap >= cfg.turn_mix_abs_gap_vph
            and structure_gap >= turn_mix_structure_min
            and local_peak >= cfg.quiet_flow_vph * 0.50
        )
    )
    return {
        "pass": passed,
        "score": float(score),
        "quiet": quiet,
        "rampMonotonic": bool(ramp.get("isRamp")),
        "rampDirection": ramp.get("direction"),
        "leftTrendVph": ramp.get("leftTrendVph"),
        "rightTrendVph": ramp.get("rightTrendVph"),
        "levelPass": level_pass,
        "leftTotalVph": left_total,
        "rightTotalVph": right_total,
        "totalAbsGap": total_abs_gap,
        "totalRelGap": total_rel_gap,
        "movementAbsGap": movement_abs_gap,
        "movementRelGap": movement_rel_gap,
        "structureGap": structure_gap,
        "dominantAbsGap": dominant_abs_gap,
        "dominantRelGap": dominant_rel_gap,
        "shareGap": share_gap,
        "localPeak": local_peak,
    }


def _boundary_evidence(profile: dict[str, Any], slot: int, cfg: SegmentationConfig) -> dict[str, Any]:
    long_evidence = _boundary_window_evidence(
        profile,
        slot,
        cfg.boundary_window_slots,
        cfg,
        apply_ramp_penalty=True,
    )
    short_evidence = _boundary_window_evidence(
        profile,
        slot,
        cfg.short_boundary_window_slots,
        cfg,
        apply_ramp_penalty=False,
    )
    local_peak = float(short_evidence.get("localPeak") or 0.0)
    abs_threshold = max(
        cfg.dominant_abs_gap_vph,
        local_peak * cfg.dominant_abs_gap_ratio,
    )
    compound_pass = (
        not short_evidence.get("quiet", False)
        and float(short_evidence.get("dominantAbsGap") or 0.0) >= abs_threshold
        and float(short_evidence.get("dominantRelGap") or 0.0) >= cfg.dominant_rel_gap
        and float(short_evidence.get("structureGap") or 0.0)
        >= cfg.structure_change_threshold * cfg.compound_structure_gap_ratio
        and local_peak >= cfg.quiet_flow_vph
    )
    short_share_pass = (
        not short_evidence.get("quiet", False)
        and float(short_evidence.get("shareGap") or 0.0) >= cfg.dominant_share_change_threshold
        and float(short_evidence.get("dominantAbsGap") or 0.0) >= abs_threshold * 0.75
        and local_peak >= cfg.quiet_flow_vph
    )
    short_turn_mix_pass = (
        not short_evidence.get("quiet", False)
        and float(short_evidence.get("movementRelGap") or 0.0) >= cfg.turn_mix_rel_gap
        and float(short_evidence.get("movementAbsGap") or 0.0) >= cfg.turn_mix_abs_gap_vph
        and float(short_evidence.get("structureGap") or 0.0)
        >= (
            cfg.structure_change_threshold
            * (
                cfg.ramp_turn_mix_structure_multiplier
                if long_evidence.get("rampMonotonic")
                else 0.45
            )
        )
        and local_peak >= cfg.quiet_flow_vph * 0.50
    )
    passed = (
        bool(long_evidence.get("pass"))
        or compound_pass
        or short_share_pass
        or short_turn_mix_pass
    )
    score = max(
        float(long_evidence.get("score") or 0.0),
        float(short_evidence.get("score") or 0.0),
        (
            max(
                float(short_evidence.get("dominantRelGap") or 0.0) / max(cfg.dominant_rel_gap, 1e-9),
                float(short_evidence.get("structureGap") or 0.0)
                / max(cfg.structure_change_threshold * cfg.compound_structure_gap_ratio, 1e-9),
            )
            if compound_pass
            else 0.0
        ),
        (
            float(short_evidence.get("shareGap") or 0.0) / max(cfg.dominant_share_change_threshold, 1e-9)
            if short_share_pass
            else 0.0
        ),
        (
            float(short_evidence.get("movementRelGap") or 0.0) / max(cfg.turn_mix_rel_gap, 1e-9)
            if short_turn_mix_pass
            else 0.0
        ),
    )
    return {
        "pass": passed,
        "score": float(score),
        "quiet": bool(long_evidence.get("quiet")) and bool(short_evidence.get("quiet")),
        "longWindow": long_evidence,
        "shortWindow": short_evidence,
        "compoundPass": compound_pass,
        "shortSharePass": short_share_pass,
        "shortTurnMixPass": short_turn_mix_pass,
        "leftTotalVph": long_evidence.get("leftTotalVph"),
        "rightTotalVph": long_evidence.get("rightTotalVph"),
        "totalAbsGap": long_evidence.get("totalAbsGap"),
        "totalRelGap": long_evidence.get("totalRelGap"),
        "movementAbsGap": long_evidence.get("movementAbsGap"),
        "movementRelGap": long_evidence.get("movementRelGap"),
        "structureGap": long_evidence.get("structureGap"),
        "dominantAbsGap": short_evidence.get("dominantAbsGap"),
        "dominantRelGap": short_evidence.get("dominantRelGap"),
        "shareGap": short_evidence.get("shareGap"),
        "rampMonotonic": bool(long_evidence.get("rampMonotonic")),
        "rampDirection": long_evidence.get("rampDirection"),
    }


def _boundary_should_preserve(profile: dict[str, Any], slot: int, cfg: SegmentationConfig) -> bool:
    evidence = _boundary_evidence(profile, slot, cfg)
    if evidence.get("compoundPass") or evidence.get("shortSharePass") or evidence.get("shortTurnMixPass"):
        return bool(evidence.get("pass"))
    long_window = evidence.get("longWindow") or {}
    if evidence.get("rampMonotonic"):
        if long_window.get("structureGap", 0.0) >= cfg.structure_change_threshold:
            return bool(evidence.get("pass"))
        if (
            long_window.get("movementRelGap", 0.0) >= cfg.turn_mix_rel_gap
            and long_window.get("movementAbsGap", 0.0) >= cfg.turn_mix_abs_gap_vph
        ):
            return bool(evidence.get("pass"))
        return False
    return bool(evidence.get("pass")) and bool(long_window.get("levelPass"))


def _ranked_boundary_candidates(profile: dict[str, Any], cfg: SegmentationConfig) -> list[tuple[float, int]]:
    candidates: list[tuple[float, int]] = []
    for slot in range(cfg.min_slots, SLOTS_PER_DAY - cfg.min_slots + 1):
        evidence = _boundary_evidence(profile, slot, cfg)
        if evidence.get("pass"):
            candidates.append((_boundary_semantic_score(profile, slot, cfg), slot))
    candidates.sort(reverse=True)

    selected: list[tuple[float, int]] = []
    radius = max(cfg.min_slots, cfg.boundary_window_slots // 2)
    limit = max(cfg.max_periods * 2, cfg.min_periods)
    for score, slot in candidates:
        if any(abs(slot - chosen_slot) < radius for _, chosen_slot in selected):
            continue
        selected.append((score, slot))
        if len(selected) >= limit:
            break
    return selected


def _candidate_dominant_share_breakpoints(
    profile: dict[str, Any],
    cfg: SegmentationConfig,
) -> set[int]:
    """Breakpoints from dominant-share / dominant-gap curves and short-window share shifts."""

    breakpoints: set[int] = set()
    dominant_share = profile.get("dominantShare")
    if dominant_share is None:
        return breakpoints

    share_arr = np.asarray(dominant_share, dtype=float)
    breakpoints.update(
        _douglas_peucker_breakpoints(
            share_arr,
            cfg.min_slots,
            cfg.dominant_share_deviation_threshold,
        )
    )

    dominant_gap = profile.get("dominantGap")
    if dominant_gap is not None:
        breakpoints.update(
            _douglas_peucker_breakpoints(
                np.asarray(dominant_gap, dtype=float),
                cfg.min_slots,
                cfg.dominant_share_deviation_threshold,
            )
        )

    window = cfg.short_boundary_window_slots
    for slot in range(window, SLOTS_PER_DAY - window + 1):
        left_share = float(share_arr[slot - window:slot].mean())
        right_share = float(share_arr[slot:slot + window].mean())
        if abs(left_share - right_share) < cfg.dominant_share_change_threshold:
            continue
        evidence = _boundary_evidence(profile, slot, cfg)
        if evidence.get("pass"):
            breakpoints.add(slot)
            continue
        if float(evidence.get("dominantAbsGap") or 0.0) >= cfg.dominant_abs_gap_vph * 0.75:
            breakpoints.add(slot)

    return breakpoints


def _candidate_cumulative_breakpoints(profile: dict[str, Any], cfg: SegmentationConfig) -> list[int]:
    total_vph = profile["totalVph"]
    breakpoints: set[int] = set(
        _douglas_peucker_breakpoints(total_vph, cfg.min_slots, cfg.cumulative_deviation_threshold)
    )

    flow = profile["flow"]
    means = profile.get("movementMeanVph")
    if means is None:
        means = flow.mean(axis=0)
    dominant_order = np.argsort(means)[::-1][:4]
    for col in dominant_order:
        if float(means[col]) < cfg.low_flow_vph:
            continue
        movement_breakpoints = _douglas_peucker_breakpoints(
            flow[:, int(col)],
            cfg.min_slots,
            cfg.movement_deviation_threshold,
        )
        breakpoints.update(movement_breakpoints)

    for _, slot in _ranked_boundary_candidates(profile, cfg):
        breakpoints.add(slot)

    dominant_share_breakpoints = _candidate_dominant_share_breakpoints(profile, cfg)
    breakpoints.update(dominant_share_breakpoints)

    candidates: list[tuple[float, int]] = []
    for slot in sorted(bp for bp in breakpoints if 0 < bp < SLOTS_PER_DAY):
        if _is_ramp_only_boundary(profile, slot, cfg):
            continue
        evidence = _boundary_evidence(profile, slot, cfg)
        if evidence.get("pass"):
            candidates.append((float(evidence["score"]), slot))
        elif slot in dominant_share_breakpoints:
            share_arr = np.asarray(profile["dominantShare"], dtype=float)
            window = cfg.short_boundary_window_slots
            left_share = float(share_arr[max(0, slot - window):slot].mean())
            right_share = float(share_arr[slot:min(len(share_arr), slot + window)].mean())
            share_score = abs(left_share - right_share) / max(cfg.dominant_share_change_threshold, 1e-9)
            candidates.append((share_score, slot))
    candidates.sort(reverse=True)

    selected = [0, SLOTS_PER_DAY]
    for _, slot in candidates:
        if any(abs(slot - existing) < cfg.min_slots for existing in selected):
            continue
        selected.append(slot)
    return sorted(selected)


def _flow_rate_gap(
    left: dict[str, Any],
    right: dict[str, Any],
    cfg: SegmentationConfig,
) -> float:
    mean_left = float(left.get("meanTotalVph") or 0.0)
    mean_right = float(right.get("meanTotalVph") or 0.0)
    return abs(mean_left - mean_right) / max(min(mean_left, mean_right), cfg.low_flow_vph * 0.5)


def _flow_absolute_gap(left: dict[str, Any], right: dict[str, Any]) -> float:
    mean_left = float(left.get("meanTotalVph") or 0.0)
    mean_right = float(right.get("meanTotalVph") or 0.0)
    return abs(mean_left - mean_right)


def _best_chord_split(
    x: np.ndarray,
    y: np.ndarray,
    start: int,
    end: int,
    cfg: SegmentationConfig,
) -> tuple[int | None, float]:
    sub_x = x[start:end]
    sub_y = y[start:end]
    if len(sub_x) < 2 * cfg.min_slots:
        return None, 0.0
    left_idx = 0
    right_idx = len(sub_x) - 1
    x0, y0 = float(sub_x[left_idx]), float(sub_y[left_idx])
    x1, y1 = float(sub_x[right_idx]), float(sub_y[right_idx])
    seg_len = math.hypot(x1 - x0, y1 - y0)
    if seg_len < 1e-12:
        return None, 0.0
    best_split: int | None = None
    best_dev = 0.0
    for split in range(cfg.min_slots, len(sub_x) - cfg.min_slots + 1):
        probe = split - 1
        if probe <= left_idx or probe >= right_idx:
            continue
        dev = _perpendicular_distance(
            x0,
            y0,
            x1,
            y1,
            float(sub_x[probe]),
            float(sub_y[probe]),
        ) / seg_len
        if dev > best_dev:
            best_dev = dev
            best_split = start + split
    return best_split, best_dev


def _best_cumulative_split(
    total_vph: np.ndarray,
    start: int,
    end: int,
    cfg: SegmentationConfig,
) -> tuple[int | None, float]:
    sub = total_vph[start:end]
    if len(sub) < 2 * cfg.min_slots:
        return None, 0.0
    x, y = _normalized_cumulative_coords(sub)
    split, dev = _best_chord_split(x, y, 0, len(sub), cfg)
    if split is None:
        return None, 0.0
    return start + split, dev


def _best_flow_level_split(
    total_vph: np.ndarray,
    start: int,
    end: int,
    cfg: SegmentationConfig,
) -> tuple[int | None, float]:
    sub = total_vph[start:end]
    if len(sub) < 2 * cfg.min_slots:
        return None, 0.0
    x, y = _normalized_flow_coords(sub)
    split, dev = _best_chord_split(x, y, 0, len(sub), cfg)
    if split is None:
        return None, 0.0
    return start + split, dev


def _is_ramp_only_boundary(
    profile: dict[str, Any],
    slot: int,
    cfg: SegmentationConfig,
) -> bool:
    evidence = _boundary_evidence(profile, slot, cfg)
    if not evidence.get("rampMonotonic"):
        return False
    if evidence.get("compoundPass") or evidence.get("shortSharePass") or evidence.get("shortTurnMixPass"):
        return False
    long_window = evidence.get("longWindow") or {}
    structure_threshold = cfg.structure_change_threshold * cfg.ramp_structure_threshold_multiplier
    if float(long_window.get("structureGap") or 0.0) >= structure_threshold:
        return False
    if (
        float(long_window.get("movementRelGap") or 0.0) >= cfg.turn_mix_rel_gap
        and float(long_window.get("movementAbsGap") or 0.0) >= cfg.turn_mix_abs_gap_vph
    ):
        return False
    return True


def _flow_growth_deceleration_strength(
    total: np.ndarray,
    slot: int,
    cfg: SegmentationConfig,
) -> float:
    """Score boundaries where growth before ``slot`` clearly slows afterward."""

    half = cfg.inflection_half_window_slots
    left = total[max(0, slot - half):slot]
    right = total[slot:min(len(total), slot + half)]
    if len(left) < 2 or len(right) < 2:
        return 0.0
    left_slope = (float(left[-1]) - float(left[0])) / max(len(left) - 1, 1)
    right_slope = (float(right[-1]) - float(right[0])) / max(len(right) - 1, 1)
    if left_slope < cfg.ramp_min_trend_vph:
        return 0.0
    deceleration = left_slope - right_slope
    if deceleration < cfg.ramp_min_trend_vph * 0.35:
        return 0.0
    return deceleration / max(abs(left_slope), cfg.ramp_min_trend_vph)


def _flow_plateau_entry_strength(
    total: np.ndarray,
    slot: int,
    cfg: SegmentationConfig,
) -> float:
    """Score boundaries where growth before ``slot`` flattens into a plateau after."""

    deceleration = _flow_growth_deceleration_strength(total, slot, cfg)
    if deceleration <= 0.0:
        return 0.0
    half = cfg.inflection_half_window_slots
    right = total[slot:min(len(total), slot + half)]
    if len(right) < 2:
        return 0.0
    right_slope = (float(right[-1]) - float(right[0])) / max(len(right) - 1, 1)
    if abs(right_slope) > cfg.ramp_min_trend_vph:
        return deceleration * 0.65
    return deceleration


def _flow_decline_elbow_strength(
    total: np.ndarray,
    slot: int,
    cfg: SegmentationConfig,
) -> float:
    """Score boundaries where a steep evening drop before ``slot`` eases afterward."""

    half = cfg.inflection_half_window_slots
    left = total[max(0, slot - half):slot]
    right = total[slot:min(len(total), slot + half)]
    if len(left) < 2 or len(right) < 2:
        return 0.0
    left_slope = (float(left[-1]) - float(left[0])) / max(len(left) - 1, 1)
    right_slope = (float(right[-1]) - float(right[0])) / max(len(right) - 1, 1)
    if left_slope > -cfg.ramp_min_trend_vph:
        return 0.0
    slowdown = right_slope - left_slope
    if slowdown < cfg.ramp_min_trend_vph * 0.35:
        return 0.0
    return slowdown / max(abs(left_slope), cfg.ramp_min_trend_vph)


def _flow_inflection_strength(
    total: np.ndarray,
    slot: int,
    cfg: SegmentationConfig,
) -> float:
    """Relative change in short-window growth rate at ``slot`` (slope kink / plateau entry)."""

    half = cfg.inflection_half_window_slots
    left = total[max(0, slot - half):slot]
    right = total[slot:min(len(total), slot + half)]
    if len(left) < 2 or len(right) < 2:
        return 0.0
    left_slope = (float(left[-1]) - float(left[0])) / max(len(left) - 1, 1)
    right_slope = (float(right[-1]) - float(right[0])) / max(len(right) - 1, 1)
    return abs(right_slope - left_slope) / max(abs(left_slope), abs(right_slope), cfg.ramp_min_trend_vph)


def _is_night_to_day_transition(profile: dict[str, Any], slot: int, cfg: SegmentationConfig) -> bool:
    long_window = _boundary_window_evidence(
        profile,
        slot,
        cfg.boundary_window_slots,
        cfg,
        apply_ramp_penalty=True,
    )
    return float(long_window.get("totalRelGap") or 0.0) >= 1.0 and float(
        long_window.get("leftTotalVph") or 0.0
    ) < cfg.quiet_flow_vph


def _boundary_semantic_score(
    profile: dict[str, Any],
    slot: int,
    cfg: SegmentationConfig,
) -> float:
    """Prefer inflection / structure boundaries over ramp level steps."""

    evidence = _boundary_evidence(profile, slot, cfg)
    if not evidence.get("pass") and not _is_night_to_day_transition(profile, slot, cfg):
        inflection_only = _flow_inflection_strength(profile["totalVph"], slot, cfg)
        if inflection_only < cfg.inflection_score_threshold:
            return 0.0
    score = float(evidence.get("score") or 0.0)
    inflection = _flow_inflection_strength(profile["totalVph"], slot, cfg)
    plateau = _flow_plateau_entry_strength(profile["totalVph"], slot, cfg)
    deceleration = _flow_growth_deceleration_strength(profile["totalVph"], slot, cfg)
    score += inflection * 2.5
    score += max(plateau, deceleration) * 2.0
    if _is_night_to_day_transition(profile, slot, cfg):
        score += 3.0
    if evidence.get("shortTurnMixPass") or evidence.get("compoundPass"):
        score += 1.0
    if evidence.get("rampMonotonic") and not _is_night_to_day_transition(profile, slot, cfg):
        score *= cfg.ramp_monotonic_score_factor
    return score


def _boundary_climb_feature_score(
    profile: dict[str, Any],
    slot: int,
    cfg: SegmentationConfig,
) -> float:
    total = profile["totalVph"]
    inflection = _flow_inflection_strength(total, slot, cfg)
    deceleration = _flow_growth_deceleration_strength(total, slot, cfg)
    plateau = _flow_plateau_entry_strength(total, slot, cfg)
    semantic = _boundary_semantic_score(profile, slot, cfg)
    return max(semantic, inflection * 2.5, deceleration * 2.0, plateau * 2.0)


def _plateau_entry_feature_score(
    profile: dict[str, Any],
    slot: int,
    cfg: SegmentationConfig,
) -> float:
    total = profile["totalVph"]
    return max(
        _flow_inflection_strength(total, slot, cfg) * 2.5,
        _flow_growth_deceleration_strength(total, slot, cfg) * 2.0,
        _flow_plateau_entry_strength(total, slot, cfg) * 2.0,
    )


def _decline_elbow_feature_score(
    profile: dict[str, Any],
    slot: int,
    cfg: SegmentationConfig,
) -> float:
    total = profile["totalVph"]
    return max(
        _flow_decline_elbow_strength(total, slot, cfg) * 2.5,
        _flow_inflection_strength(total, slot, cfg) * 2.0,
    )


def _pick_best_boundary_in_span(
    profile: dict[str, Any],
    start_slot: int,
    end_slot: int,
    cfg: SegmentationConfig,
    *,
    score_fn: Any | None = None,
    min_score: float | None = None,
) -> int | None:
    """Pick the strongest semantic boundary inside ``[start_slot, end_slot]``."""

    if start_slot > end_slot:
        return None
    scorer = score_fn or _boundary_climb_feature_score
    threshold = cfg.inflection_score_threshold if min_score is None else min_score
    best_slot: int | None = None
    best_score = threshold
    for slot in range(start_slot, end_slot + 1):
        score = scorer(profile, slot, cfg)
        if score > best_score:
            best_score = score
            best_slot = slot
    return best_slot


def _pick_boundary_in_window(
    profile: dict[str, Any],
    start_slot: int,
    end_slot: int,
    cfg: SegmentationConfig,
    *,
    prefer_slot: int | None = None,
    prefer_weight: float = 0.18,
    prefer_first_floor: float = 0.45,
    score_fn: Any | None = None,
) -> int | None:
    del prefer_slot, prefer_weight, prefer_first_floor
    return _pick_best_boundary_in_span(profile, start_slot, end_slot, cfg, score_fn=score_fn)


def _periods_from_boundaries(boundaries: list[int]) -> list[tuple[int, int]]:
    ordered = sorted({0, SLOTS_PER_DAY, *boundaries})
    return [(ordered[idx], ordered[idx + 1]) for idx in range(len(ordered) - 1)]


def _enforce_min_period_duration(
    periods: list[tuple[int, int]],
    cfg: SegmentationConfig,
) -> list[tuple[int, int]]:
    merged = list(periods)
    changed = True
    while changed and len(merged) > 1:
        changed = False
        for idx, (start, end) in enumerate(merged):
            if end - start >= cfg.min_slots:
                continue
            if idx == 0:
                neighbor = 1
            elif idx == len(merged) - 1:
                neighbor = idx - 1
            else:
                left_len = merged[idx - 1][1] - merged[idx - 1][0]
                right_len = merged[idx + 1][1] - merged[idx + 1][0]
                neighbor = idx - 1 if left_len <= right_len else idx + 1
            if neighbor < idx:
                merged[neighbor] = (merged[neighbor][0], end)
                del merged[idx]
            else:
                merged[idx] = (start, merged[neighbor][1])
                del merged[neighbor]
            changed = True
            break
    return merged


def _flow_swing(
    profile: dict[str, Any],
    start: int,
    end: int,
) -> float:
    segment = profile["totalVph"][start:end]
    if len(segment) < 4:
        return 0.0
    return float(segment.max() - segment.min())


def _rising_flow_period(
    profile: dict[str, Any],
    start: int,
    end: int,
    cfg: SegmentationConfig,
) -> bool:
    segment = profile["totalVph"][start:end]
    window = min(cfg.boundary_window_slots, max(1, len(segment) // 3))
    if len(segment) < window * 2:
        return False
    left_mean = float(segment[:window].mean())
    right_mean = float(segment[-window:].mean())
    return right_mean > left_mean + cfg.ramp_min_trend_vph * window * 0.35


def _falling_flow_period(
    profile: dict[str, Any],
    start: int,
    end: int,
    cfg: SegmentationConfig,
) -> bool:
    segment = profile["totalVph"][start:end]
    window = min(cfg.boundary_window_slots, max(1, len(segment) // 3))
    if len(segment) < window * 2:
        return False
    left_mean = float(segment[:window].mean())
    right_mean = float(segment[-window:].mean())
    return right_mean < left_mean - cfg.ramp_min_trend_vph * window * 0.35


def _period_interior_boundaries(
    periods: list[tuple[int, int]],
    start: int,
    end: int,
) -> list[int]:
    return [boundary for boundary in (period_end for _, period_end in periods[:-1]) if start < boundary < end]


def _ramp_direction_boundary(
    profile: dict[str, Any],
    boundary: int,
    cfg: SegmentationConfig,
) -> str | None:
    evidence = _boundary_evidence(profile, boundary, cfg)
    if not evidence.get("rampMonotonic"):
        return None
    return str(evidence.get("rampDirection") or "")


def _has_oversized_period(
    periods: list[tuple[int, int]],
    cfg: SegmentationConfig,
    *,
    max_minutes: int,
    profile: dict[str, Any] | None = None,
    min_swing_vph: float = 0.0,
) -> bool:
    for start, end in periods:
        if (end - start) * SLOT_MINUTES <= max_minutes:
            continue
        if profile is not None and min_swing_vph > 0.0:
            if _flow_swing(profile, start, end) < min_swing_vph:
                continue
        return True
    return False


def _collapse_ramp_micro_boundaries(
    periods: list[tuple[int, int]],
    profile: dict[str, Any],
    cfg: SegmentationConfig,
    *,
    direction: str,
    keep_boundary: Any,
) -> list[tuple[int, int]]:
    """Drop ramp micro-splits inside monotonic flow spans; keep semantic inflection points."""

    if len(periods) <= 2:
        return periods
    boundaries = [end for _, end in periods[:-1]]
    candidates: set[int] = set()
    for start, end in periods:
        trend_ok = (
            _rising_flow_period(profile, start, end, cfg)
            if direction == "up"
            else _falling_flow_period(profile, start, end, cfg)
        )
        if not trend_ok:
            continue
        for boundary in _period_interior_boundaries(periods, start, end):
            if _is_ramp_only_boundary(profile, boundary, cfg):
                candidates.add(boundary)
                continue
            if _ramp_direction_boundary(profile, boundary, cfg) == direction:
                candidates.add(boundary)
    if not candidates:
        return periods

    keep = {boundary for boundary in candidates if keep_boundary(profile, boundary, cfg)}
    preserved = [boundary for boundary in boundaries if boundary not in candidates]
    preserved.extend(sorted(keep))
    result = _periods_from_boundaries(preserved)
    min_swing = cfg.quiet_flow_absolute_gap_vph if direction == "up" else 0.0
    if _has_oversized_period(
        result,
        cfg,
        max_minutes=180 if direction == "up" else 150,
        profile=profile,
        min_swing_vph=min_swing,
    ):
        return periods
    return result


def _keep_climb_boundary(
    profile: dict[str, Any],
    boundary: int,
    cfg: SegmentationConfig,
) -> bool:
    total = profile["totalVph"]
    if _is_night_to_day_transition(profile, boundary, cfg):
        return True
    inflection = _flow_inflection_strength(total, boundary, cfg)
    plateau = _flow_plateau_entry_strength(total, boundary, cfg)
    evidence = _boundary_evidence(profile, boundary, cfg)
    return (
        inflection >= cfg.inflection_score_threshold or plateau >= cfg.inflection_score_threshold
    ) and not evidence.get("rampMonotonic")


def _keep_decline_boundary(
    profile: dict[str, Any],
    boundary: int,
    cfg: SegmentationConfig,
) -> bool:
    total = profile["totalVph"]
    evidence = _boundary_evidence(profile, boundary, cfg)
    if evidence.get("compoundPass") or evidence.get("shortTurnMixPass") or evidence.get("shortSharePass"):
        return True
    decline_elbow = _flow_decline_elbow_strength(total, boundary, cfg)
    if decline_elbow >= cfg.inflection_score_threshold * 0.35:
        return True
    inflection = _flow_inflection_strength(total, boundary, cfg)
    return inflection >= cfg.inflection_score_threshold and not evidence.get("rampMonotonic")


def _collapse_climb_micro_boundaries(
    periods: list[tuple[int, int]],
    profile: dict[str, Any],
    cfg: SegmentationConfig,
) -> list[tuple[int, int]]:
    return _collapse_ramp_micro_boundaries(
        periods,
        profile,
        cfg,
        direction="up",
        keep_boundary=_keep_climb_boundary,
    )


def _has_strong_boundary_scores(
    boundaries: list[int],
    profile: dict[str, Any],
    cfg: SegmentationConfig,
    score_fn: Any,
) -> bool:
    return any(score_fn(profile, boundary, cfg) >= cfg.inflection_score_threshold for boundary in boundaries)


def _should_apply_ramp_reshape(
    periods: list[tuple[int, int]],
    profile: dict[str, Any],
    cfg: SegmentationConfig,
    *,
    direction: str,
    kink_score_fn: Any,
    plateau_score_fn: Any,
) -> bool:
    boundaries = [end for _, end in periods[:-1]]
    if _has_strong_boundary_scores(boundaries, profile, cfg, kink_score_fn) and _has_strong_boundary_scores(
        boundaries,
        profile,
        cfg,
        plateau_score_fn,
    ):
        return False

    for start, end in periods:
        trend_ok = (
            _rising_flow_period(profile, start, end, cfg)
            if direction == "up"
            else _falling_flow_period(profile, start, end, cfg)
        )
        if not trend_ok:
            continue
        zone_bounds = _period_interior_boundaries(periods, start, end)
        ramp_bounds = [
            boundary
            for boundary in zone_bounds
            if _is_ramp_only_boundary(profile, boundary, cfg)
            or _ramp_direction_boundary(profile, boundary, cfg) == direction
        ]
        if len(ramp_bounds) >= 2 and ramp_bounds[-1] - ramp_bounds[0] <= cfg.climb_boundary_cluster_slots:
            return True
        if direction == "up" and any(_is_ramp_only_boundary(profile, boundary, cfg) for boundary in zone_bounds):
            return True

    if direction == "up":
        return any(
            _rising_flow_period(profile, start, end, cfg)
            and end - start >= cfg.min_slots * 8
            and _flow_swing(profile, start, end) >= cfg.quiet_flow_absolute_gap_vph * 2
            for start, end in periods
        )
    return any(
        _falling_flow_period(profile, start, end, cfg)
        and (end - start) * SLOT_MINUTES >= 120
        and _flow_swing(profile, start, end) >= cfg.quiet_flow_absolute_gap_vph
        for start, end in periods
    )


def _reshape_ramp_cluster_boundaries(
    periods: list[tuple[int, int]],
    profile: dict[str, Any],
    cfg: SegmentationConfig,
    *,
    direction: str,
    pickers: list[tuple[Any, Any | None]],
) -> list[tuple[int, int]]:
    """Replace clustered ramp micro-splits with strongest semantic points in the same flow span."""

    if len(periods) <= 1:
        return periods
    if not _should_apply_ramp_reshape(
        periods,
        profile,
        cfg,
        direction=direction,
        kink_score_fn=(_boundary_climb_feature_score if direction == "up" else _decline_elbow_feature_score),
        plateau_score_fn=(_plateau_entry_feature_score if direction == "up" else _decline_elbow_feature_score),
    ):
        return periods

    boundaries = [end for _, end in periods[:-1]]
    replacements: set[int] = set()
    preserved = list(boundaries)

    for start, end in periods:
        trend_ok = (
            _rising_flow_period(profile, start, end, cfg)
            if direction == "up"
            else _falling_flow_period(profile, start, end, cfg)
        )
        if not trend_ok:
            continue
        zone_bounds = _period_interior_boundaries(periods, start, end)
        ramp_bounds = [
            boundary
            for boundary in zone_bounds
            if _is_ramp_only_boundary(profile, boundary, cfg)
            or _ramp_direction_boundary(profile, boundary, cfg) == direction
        ]
        if not ramp_bounds and direction != "up":
            continue
        if not ramp_bounds and not (
            end - start >= cfg.min_slots * 8
            and _flow_swing(profile, start, end) >= cfg.quiet_flow_absolute_gap_vph * 2
        ):
            continue

        zone_lo = min(ramp_bounds) if ramp_bounds else start + cfg.min_slots
        zone_hi = max(ramp_bounds) if ramp_bounds else end - cfg.min_slots
        search_lo = max(start + cfg.min_slots, zone_lo - cfg.boundary_window_slots)
        search_hi = min(end - cfg.min_slots, zone_hi + cfg.boundary_window_slots)
        if search_lo > search_hi:
            continue

        period_picks: list[int] = []
        for score_fn, slot_filter in pickers:
            pick_lo = search_lo
            pick_hi = search_hi
            if slot_filter is not None:
                pick_lo, pick_hi = slot_filter(start, end, zone_lo, zone_hi, period_picks, cfg)
                pick_lo = max(pick_lo, start + cfg.min_slots)
                pick_hi = min(pick_hi, end - cfg.min_slots)
            if pick_lo > pick_hi:
                continue
            if direction == "up" and score_fn is _night_transition_score:
                if any(_is_night_to_day_transition(profile, boundary, cfg) for boundary in boundaries):
                    continue
                pick_lo = max(pick_lo, start + cfg.min_slots)
                pick_hi = min(pick_hi, zone_lo)
            slot = _pick_best_boundary_in_span(profile, pick_lo, pick_hi, cfg, score_fn=score_fn)
            if slot is None:
                continue
            if period_picks and slot <= period_picks[-1] + cfg.min_slots - 1:
                continue
            period_picks.append(slot)

        if not period_picks:
            continue
        preserved = [boundary for boundary in preserved if boundary < zone_lo or boundary > zone_hi]
        replacements.update(period_picks)

    if not replacements:
        return periods
    preserved.extend(replacements)
    return _periods_from_boundaries(preserved)


def _night_transition_score(profile: dict[str, Any], slot: int, cfg: SegmentationConfig) -> float:
    if not _is_night_to_day_transition(profile, slot, cfg):
        return 0.0
    return _boundary_semantic_score(profile, slot, cfg) + 3.0


def _reshape_morning_climb_boundaries(
    periods: list[tuple[int, int]],
    profile: dict[str, Any],
    cfg: SegmentationConfig,
) -> list[tuple[int, int]]:
    """Replace ramp micro-splits in rising spans with night transition / kink / plateau points."""

    def _after_prior(
        start: int,
        end: int,
        zone_lo: int,
        zone_hi: int,
        prior: list[int],
        reshape_cfg: SegmentationConfig,
    ) -> tuple[int, int]:
        del start, end
        if not prior:
            return zone_lo, zone_hi
        return prior[-1] + reshape_cfg.min_slots, zone_hi

    return _reshape_ramp_cluster_boundaries(
        periods,
        profile,
        cfg,
        direction="up",
        pickers=[
            (_night_transition_score, None),
            (_boundary_climb_feature_score, None),
            (_plateau_entry_feature_score, _after_prior),
        ],
    )


def _collapse_decline_micro_boundaries(
    periods: list[tuple[int, int]],
    profile: dict[str, Any],
    cfg: SegmentationConfig,
) -> list[tuple[int, int]]:
    return _collapse_ramp_micro_boundaries(
        periods,
        profile,
        cfg,
        direction="down",
        keep_boundary=_keep_decline_boundary,
    )


def _period_needs_decline_elbow(
    profile: dict[str, Any],
    start: int,
    end: int,
    cfg: SegmentationConfig,
) -> bool:
    if (end - start) * SLOT_MINUTES < 120:
        return False
    segment = profile["totalVph"][start:end]
    if len(segment) < cfg.boundary_window_slots * 2:
        return False
    if float(segment.max() - segment.min()) < cfg.quiet_flow_absolute_gap_vph:
        return False
    peak_offset = int(np.argmax(segment))
    after_peak = segment[peak_offset:]
    if len(after_peak) < cfg.boundary_window_slots:
        return False
    slope = (float(after_peak[-1]) - float(after_peak[0])) / max(len(after_peak) - 1, 1)
    return slope < -cfg.ramp_min_trend_vph


def _decline_onset_slot(profile: dict[str, Any], start: int, end: int) -> int:
    segment = profile["totalVph"][start:end]
    return start + int(np.argmax(segment))


def _evening_structure_boundary_score(
    profile: dict[str, Any],
    slot: int,
    cfg: SegmentationConfig,
) -> float:
    evidence = _boundary_evidence(profile, slot, cfg)
    long_window = evidence.get("longWindow") or {}
    short_window = evidence.get("shortWindow") or {}
    score = float(long_window.get("structureGap") or 0.0) * 2.0
    score += float(short_window.get("movementRelGap") or 0.0) * 1.8
    score += float(short_window.get("movementAbsGap") or 0.0) / max(
        cfg.turn_mix_abs_gap_vph,
        1.0,
    )
    if evidence.get("shortTurnMixPass"):
        score += 1.25
    if evidence.get("compoundPass"):
        score += 1.0
    return score


def _reshape_high_flow_structure_boundaries(
    periods: list[tuple[int, int]],
    profile: dict[str, Any],
    cfg: SegmentationConfig,
) -> list[tuple[int, int]]:
    """Align interior splits in high-flow spans with strongest turn-mix / structure evidence."""

    if len(periods) <= 1:
        return periods
    boundaries = [end for _, end in periods[:-1]]
    preserved = list(boundaries)
    changed = False

    for start, end in periods:
        segment = profile["totalVph"][start:end]
        if float(segment.mean()) < cfg.quiet_flow_vph:
            continue
        interior = _period_interior_boundaries(periods, start, end)
        if not interior:
            continue
        strong = [
            boundary
            for boundary in interior
            if _evening_structure_boundary_score(profile, boundary, cfg) >= cfg.inflection_score_threshold
        ]
        if len(strong) >= 2:
            continue

        search_lo = start + cfg.min_slots
        search_hi = end - cfg.min_slots
        replacements: list[int] = []
        first = _pick_best_boundary_in_span(
            profile,
            search_lo,
            search_hi,
            cfg,
            score_fn=_evening_structure_boundary_score,
        )
        if first is not None:
            replacements.append(first)
            second = _pick_best_boundary_in_span(
                profile,
                first + cfg.min_slots,
                search_hi,
                cfg,
                score_fn=_evening_structure_boundary_score,
            )
            if second is not None:
                replacements.append(second)
        if not replacements:
            continue
        preserved = [boundary for boundary in preserved if boundary <= start or boundary >= end]
        preserved.extend(replacements)
        changed = True

    if not changed:
        return periods
    return _periods_from_boundaries(preserved)


def _reshape_decline_elbow_boundaries(
    periods: list[tuple[int, int]],
    profile: dict[str, Any],
    cfg: SegmentationConfig,
) -> list[tuple[int, int]]:
    """Inject decline-elbow boundaries after the within-period flow peak when missing."""

    if len(periods) <= 1:
        return periods
    boundaries = [end for _, end in periods[:-1]]
    preserved = list(boundaries)
    changed = False

    for start, end in periods:
        if not _period_needs_decline_elbow(profile, start, end, cfg):
            continue
        decline_start = _decline_onset_slot(profile, start, end)
        interior = [boundary for boundary in preserved if decline_start < boundary < end]
        if any(
            _decline_elbow_feature_score(profile, boundary, cfg) >= cfg.inflection_score_threshold * 0.35
            for boundary in interior
        ):
            continue
        elbow = _pick_best_boundary_in_span(
            profile,
            decline_start + cfg.min_slots,
            end - cfg.min_slots,
            cfg,
            score_fn=_decline_elbow_feature_score,
        )
        if elbow is None:
            continue
        preserved = [boundary for boundary in preserved if boundary <= decline_start or boundary >= end]
        preserved.append(elbow)
        changed = True

    if not changed:
        return periods
    return _periods_from_boundaries(preserved)


def _strong_movement_boundary_score(
    profile: dict[str, Any],
    slot: int,
    cfg: SegmentationConfig,
) -> float:
    """Score operationally important boundaries driven by one major movement."""

    evidence = _boundary_evidence(profile, slot, cfg)
    if not evidence.get("pass"):
        return 0.0
    movement_abs_gap = float(evidence.get("movementAbsGap") or 0.0)
    dominant_abs_gap = float(evidence.get("dominantAbsGap") or 0.0)
    structure_gap = float(evidence.get("structureGap") or 0.0)
    total_abs_gap = float(evidence.get("totalAbsGap") or 0.0)
    if max(movement_abs_gap, dominant_abs_gap) < cfg.dominant_abs_gap_vph:
        return 0.0
    if (
        structure_gap < cfg.structure_change_threshold
        and total_abs_gap < cfg.quiet_flow_absolute_gap_vph * 0.50
    ):
        return 0.0

    return (
        _boundary_semantic_score(profile, slot, cfg)
        + movement_abs_gap / max(cfg.turn_mix_abs_gap_vph, 1.0)
        + dominant_abs_gap / max(cfg.dominant_abs_gap_vph, 1.0)
        + structure_gap / max(cfg.structure_change_threshold, 1e-9)
        + total_abs_gap / max(cfg.quiet_flow_absolute_gap_vph, 1.0) * 0.50
    )


def _best_strong_movement_boundary_in_period(
    profile: dict[str, Any],
    start: int,
    end: int,
    cfg: SegmentationConfig,
    existing_boundaries: list[int],
) -> tuple[float, int] | None:
    if end - start < cfg.min_slots * 4:
        return None

    scored: list[tuple[float, int]] = []
    for slot in range(start + cfg.min_slots, end - cfg.min_slots + 1):
        if any(abs(slot - boundary) <= cfg.boundary_window_slots for boundary in existing_boundaries):
            continue
        score = _strong_movement_boundary_score(profile, slot, cfg)
        if score >= cfg.inflection_score_threshold:
            scored.append((score, slot))
    if not scored:
        return None

    best_score = max(score for score, _ in scored)
    onset_floor = best_score * 0.96
    onset_candidates = [item for item in scored if item[0] >= onset_floor]
    return min(onset_candidates, key=lambda item: item[1])


def _weak_boundary_replacement_score(
    periods: list[tuple[int, int]],
    boundary_idx: int,
    profile: dict[str, Any],
    cfg: SegmentationConfig,
) -> float:
    boundary = periods[boundary_idx][1]
    if _boundary_should_preserve(profile, boundary, cfg):
        return inf

    merged_start = periods[boundary_idx][0]
    merged_end = periods[boundary_idx + 1][1]
    merged_minutes = (merged_end - merged_start) * SLOT_MINUTES
    if (
        merged_minutes > cfg.max_period_minutes
        and _flow_swing(profile, merged_start, merged_end) >= cfg.quiet_flow_absolute_gap_vph
    ):
        return inf

    evidence = _boundary_evidence(profile, boundary, cfg)
    score = _boundary_semantic_score(profile, boundary, cfg)
    if evidence.get("pass"):
        score += 50.0
    return score


def _promote_strong_movement_boundaries(
    periods: list[tuple[int, int]],
    profile: dict[str, Any],
    cfg: SegmentationConfig,
) -> list[tuple[int, int]]:
    """Make room for high-priority single-movement jumps when the result is already full."""

    result = list(periods)
    changed = True
    while changed:
        changed = False
        boundaries = [end for _, end in result[:-1]]
        candidates: list[tuple[float, int]] = []
        for start, end in result:
            candidate = _best_strong_movement_boundary_in_period(
                profile,
                start,
                end,
                cfg,
                boundaries,
            )
            if candidate is not None:
                candidates.append(candidate)
        if not candidates:
            break

        candidate_score, candidate_slot = max(candidates)
        if len(result) < cfg.max_periods:
            boundaries.append(candidate_slot)
            result = _periods_from_boundaries(boundaries)
            changed = True
            continue

        removable: list[tuple[float, int]] = []
        for idx in range(len(result) - 1):
            replacement_score = _weak_boundary_replacement_score(result, idx, profile, cfg)
            if math.isfinite(replacement_score):
                removable.append((replacement_score, result[idx][1]))
        if not removable:
            break

        weakest_score, weakest_boundary = min(removable)
        if candidate_score <= weakest_score + 1.0:
            break
        boundaries = [
            boundary
            for boundary in boundaries
            if boundary != weakest_boundary
        ]
        boundaries.append(candidate_slot)
        result = _periods_from_boundaries(boundaries)
        changed = True

    return result


def _collapse_spike_bracket_to_single(
    periods: list[tuple[int, int]],
    profile: dict[str, Any],
    cfg: SegmentationConfig,
) -> list[tuple[int, int]]:
    """Replace a tight spike bracket (e.g. 14:15 / 14:30) with one center boundary (14:25)."""

    result = list(periods)
    max_pair_span = cfg.min_slots * 4
    total = profile["totalVph"]
    changed = True
    while changed and len(result) >= 3:
        changed = False
        boundaries = [end for _, end in result[:-1]]
        for idx in range(len(result) - 2):
            left_start, left_end = result[idx]
            mid_start, mid_end = result[idx + 1]
            right_start, right_end = result[idx + 2]
            if left_end != mid_start or mid_end != right_start:
                continue
            inner_slots = mid_end - mid_start
            pair_span = mid_end - left_end
            if inner_slots > cfg.min_slots or pair_span > max_pair_span:
                continue
            inner_span = total[left_end:mid_end]
            outer_left = total[max(0, left_end - cfg.min_slots):left_end]
            outer_right = total[mid_end:min(len(total), mid_end + cfg.min_slots)]
            if len(inner_span) < 1 or len(outer_left) < 1 or len(outer_right) < 1:
                continue
            peak = float(inner_span.max())
            base = float(np.concatenate([outer_left, outer_right]).mean())
            minimum_bracket = inner_slots <= cfg.min_slots and pair_span <= max_pair_span
            if not minimum_bracket and peak < base * 1.04:
                continue
            prefer_single = (left_end + mid_end + 1) // 2
            search_lo = max(left_start + cfg.min_slots, left_end - 1)
            search_hi = min(right_end - cfg.min_slots, mid_end + 1)
            if search_lo > search_hi:
                continue
            single_slot = _pick_boundary_in_window(
                profile,
                search_lo,
                search_hi,
                cfg,
                prefer_slot=prefer_single,
            )
            if single_slot is None:
                continue
            preserved = [
                boundary
                for boundary in boundaries
                if boundary not in {left_end, mid_end}
            ]
            preserved.append(single_slot)
            result = _periods_from_boundaries(preserved)
            changed = True
            break
    return result


def _widen_spike_bracket_boundaries(
    periods: list[tuple[int, int]],
    profile: dict[str, Any],
    cfg: SegmentationConfig,
) -> list[tuple[int, int]]:
    """Relocate tight boundary pairs bracketing a spike to outer inflection points."""

    if len(periods) < 3:
        return periods
    max_inner_slots = max(cfg.min_slots, round(cfg.spike_bracket_max_minutes / SLOT_MINUTES))
    radius = cfg.spike_boundary_relocate_slots
    boundaries = [end for _, end in periods[:-1]]
    updated = list(boundaries)
    total = profile["totalVph"]

    idx = 0
    while idx < len(periods) - 2:
        left_start, left_end = periods[idx]
        mid_start, mid_end = periods[idx + 1]
        right_start, right_end = periods[idx + 2]
        if left_end != mid_start or mid_end != right_start:
            idx += 1
            continue
        inner_slots = mid_end - mid_start
        pair_span = mid_end - left_end
        if inner_slots > max_inner_slots or pair_span > radius * 2 + cfg.min_slots:
            idx += 1
            continue
        inner_metric_span = total[left_end:mid_end]
        outer_metric_span = total[max(0, left_end - radius):min(len(total), mid_end + radius)]
        if len(inner_metric_span) < 1 or len(outer_metric_span) < 2:
            idx += 1
            continue
        inner_peak = float(inner_metric_span.max())
        outer_mean = float(outer_metric_span.mean())
        if inner_peak < outer_mean * 1.08 and inner_peak > outer_mean * 0.92:
            idx += 1
            continue
        left_pos = updated.index(left_end)
        right_pos = updated.index(mid_end)
        search_left = range(
            max(left_start + cfg.min_slots, left_end - radius),
            left_end + 1,
        )
        search_right = range(
            mid_end,
            min(right_end - cfg.min_slots, mid_end + radius + 1),
        )
        if not search_left or not search_right:
            idx += 1
            continue
        best_left = max(search_left, key=lambda slot: _boundary_semantic_score(profile, slot, cfg))
        best_right = max(search_right, key=lambda slot: _boundary_semantic_score(profile, slot, cfg))
        if best_left >= best_right or best_right - best_left < cfg.min_slots:
            idx += 1
            continue
        updated[left_pos] = best_left
        updated[right_pos] = best_right
        idx += 2

    return _periods_from_boundaries(updated)


def _inject_missing_inflection_boundaries(
    periods: list[tuple[int, int]],
    profile: dict[str, Any],
    cfg: SegmentationConfig,
) -> list[tuple[int, int]]:
    """Ensure strong inflection points inside long daytime periods are not skipped entirely."""

    result = list(periods)
    while len(result) < cfg.max_periods:
        best_period_idx: int | None = None
        best_slot: int | None = None
        best_score = cfg.inflection_score_threshold
        total = profile["totalVph"]
        for idx, (start, end) in enumerate(result):
            if end - start < cfg.min_slots * 6:
                continue
            if float(total[start:end].mean()) < cfg.quiet_flow_vph * 0.75:
                continue
            for slot in range(start + cfg.min_slots, end - cfg.min_slots + 1):
                inflection = _flow_inflection_strength(total, slot, cfg)
                plateau = _flow_plateau_entry_strength(total, slot, cfg)
                if (
                    inflection < cfg.inflection_score_threshold
                    and plateau < cfg.inflection_score_threshold
                ):
                    continue
                semantic = _boundary_semantic_score(profile, slot, cfg)
                feature = max(inflection, plateau)
                pick_score = max(semantic, feature * 2.5)
                if pick_score <= best_score:
                    continue
                existing = {boundary for _, boundary in result[:-1]}
                if any(abs(slot - boundary) < cfg.min_slots for boundary in existing):
                    continue
                best_score = pick_score
                best_slot = slot
                best_period_idx = idx
        if best_period_idx is None or best_slot is None:
            break
        start, end = result[best_period_idx]
        result[best_period_idx : best_period_idx + 1] = [(start, best_slot), (best_slot, end)]
    return result


def _refine_semantic_boundaries(
    periods: list[tuple[int, int]],
    profile: dict[str, Any],
    segment_metrics: dict[tuple[int, int], dict[str, Any]],
    cfg: SegmentationConfig,
) -> list[tuple[int, int]]:
    if _is_near_uniform_profile(profile, cfg):
        return periods
    periods = _collapse_climb_micro_boundaries(periods, profile, cfg)
    periods = _reshape_morning_climb_boundaries(periods, profile, cfg)
    periods = _widen_spike_bracket_boundaries(periods, profile, cfg)
    periods = _collapse_spike_bracket_to_single(periods, profile, cfg)
    periods = _inject_missing_inflection_boundaries(periods, profile, cfg)
    periods = _collapse_decline_micro_boundaries(periods, profile, cfg)
    periods = _reshape_high_flow_structure_boundaries(periods, profile, cfg)
    periods = _reshape_decline_elbow_boundaries(periods, profile, cfg)
    periods = _promote_strong_movement_boundaries(periods, profile, cfg)
    return _enforce_min_period_duration(periods, cfg)


def _refine_long_period_splits(
    periods: list[tuple[int, int]],
    profile: dict[str, Any],
    segment_metrics: dict[tuple[int, int], dict[str, Any]],
    cfg: SegmentationConfig,
) -> list[tuple[int, int]]:
    """Re-split merged daytime blocks whose cumulative slope looks flat but flow level bends."""

    total_vph = profile["totalVph"]
    result = list(periods)
    while len(result) < cfg.max_periods:
        best_idx: int | None = None
        best_split: int | None = None
        best_score = -1.0
        for idx, (start, end) in enumerate(result):
            duration = (end - start) * SLOT_MINUTES
            if duration <= cfg.max_period_minutes:
                continue
            period_metric = segment_metrics[(start, end)]
            mean_flow = float(period_metric.get("meanTotalVph") or 0.0)
            if mean_flow < cfg.quiet_flow_vph:
                continue
            split, dev = _best_flow_level_split(total_vph, start, end, cfg)
            if split is None or dev <= cfg.flow_level_deviation_threshold:
                continue
            score = dev * math.sqrt(end - start)
            if score > best_score:
                best_idx = idx
                best_split = split
                best_score = score
        if best_idx is None or best_split is None:
            break
        start, end = result[best_idx]
        result[best_idx : best_idx + 1] = [(start, best_split), (best_split, end)]
    return result


def _refine_cumulative_slope_splits(
    periods: list[tuple[int, int]],
    profile: dict[str, Any],
    cfg: SegmentationConfig,
) -> list[tuple[int, int]]:
    """Split long periods while chord deviation on cumulative flow still exceeds threshold."""

    total_vph = profile["totalVph"]
    result = list(periods)
    while len(result) < cfg.max_periods:
        best_idx: int | None = None
        best_split: int | None = None
        best_dev = -1.0
        for idx, (start, end) in enumerate(result):
            split, dev = _best_cumulative_split(total_vph, start, end, cfg)
            if split is None or dev <= cfg.cumulative_deviation_threshold:
                continue
            if _is_ramp_only_boundary(profile, split, cfg):
                continue
            if best_split is None or dev > best_dev:
                best_idx = idx
                best_split = split
                best_dev = dev
        if best_idx is None or best_split is None:
            break
        start, end = result[best_idx]
        result[best_idx : best_idx + 1] = [(start, best_split), (best_split, end)]
    return result


def _refine_internal_compound_splits(
    periods: list[tuple[int, int]],
    profile: dict[str, Any],
    cfg: SegmentationConfig,
) -> list[tuple[int, int]]:
    """Split long periods at the strongest short-window turn-mix / structure boundary."""

    result = list(periods)
    while len(result) < cfg.max_periods:
        best_idx: int | None = None
        best_split: int | None = None
        best_score = -1.0
        for idx, (start, end) in enumerate(result):
            if end - start < cfg.internal_split_min_slots:
                continue
            for slot in range(start + cfg.min_slots, end - cfg.min_slots + 1):
                evidence = _boundary_evidence(profile, slot, cfg)
                if not evidence.get("pass"):
                    continue
                if not (
                    evidence.get("compoundPass")
                    or evidence.get("shortSharePass")
                    or evidence.get("shortTurnMixPass")
                ):
                    continue
                score = float(evidence.get("score") or 0.0)
                if score > best_score:
                    best_idx = idx
                    best_split = slot
                    best_score = score
        if best_idx is None or best_split is None or best_score < cfg.internal_compound_score_threshold:
            break
        start, end = result[best_idx]
        result[best_idx : best_idx + 1] = [(start, best_split), (best_split, end)]
    return result


def _breakpoints_to_periods(breakpoints: list[int]) -> list[tuple[int, int]]:
    return [(breakpoints[idx], breakpoints[idx + 1]) for idx in range(len(breakpoints) - 1)]


def _segment_mean_flow(total_vph: np.ndarray, start: int, end: int) -> float:
    segment = total_vph[start:end]
    return float(segment.mean()) if len(segment) else 0.0


def _merge_most_similar_adjacent_periods(
    periods: list[tuple[int, int]],
    total_vph: np.ndarray,
    cfg: SegmentationConfig,
) -> tuple[list[tuple[int, int]], dict[str, Any] | None]:
    best_idx: int | None = None
    best_gap = inf
    for idx in range(len(periods) - 1):
        start_left, end_left = periods[idx]
        start_right, end_right = periods[idx + 1]
        if end_left != start_right:
            continue
        flow_left = _segment_mean_flow(total_vph, start_left, end_left)
        flow_right = _segment_mean_flow(total_vph, start_right, end_right)
        gap = abs(flow_left - flow_right) / max(min(flow_left, flow_right), cfg.low_flow_vph * 0.5)
        if gap < best_gap:
            best_gap = gap
            best_idx = idx
    if best_idx is None:
        return periods, None
    start_left, _ = periods[best_idx]
    _, end_right = periods[best_idx + 1]
    merged = periods[:best_idx] + [(start_left, end_right)] + periods[best_idx + 2:]
    return merged, {
        "mergedIndex": best_idx,
        "flowGap": round(float(best_gap), 4),
    }


def _is_near_uniform_profile(profile: dict[str, Any], cfg: SegmentationConfig) -> bool:
    total = profile["totalVph"]
    mean = float(total.mean()) if len(total) else 0.0
    if mean < 1.0:
        return True
    return float(total.std()) / mean <= cfg.uniform_flow_cv_threshold


def _solve_cumulative_piecewise(
    profile: dict[str, Any],
    segment_metrics: dict[tuple[int, int], dict[str, Any]],
    cfg: SegmentationConfig,
) -> tuple[list[tuple[int, int]], float, dict[str, Any]]:
    """Detect timing periods from cumulative-flow slope changes via Douglas–Peucker."""

    threshold = cfg.cumulative_deviation_threshold
    total_vph = profile["totalVph"]
    breakpoints = _candidate_cumulative_breakpoints(profile, cfg)
    periods = _breakpoints_to_periods(breakpoints)
    merge_steps: list[dict[str, Any]] = []
    split_steps: list[dict[str, Any]] = []

    while len(periods) > cfg.max_periods:
        periods, step = _merge_most_similar_adjacent_periods(periods, total_vph, cfg)
        if step is None:
            break
        merge_steps.append(step)

    if len(periods) < cfg.min_periods:
        if _is_near_uniform_profile(profile, cfg):
            periods = _balanced_periods(cfg.min_periods, cfg.min_slots)
            split_steps.append({"method": "balanced_uniform_fallback", "selectedK": len(periods)})
        else:
            lowered = threshold
            for _ in range(8):
                lowered *= 0.65
                breakpoints = _douglas_peucker_breakpoints(total_vph, cfg.min_slots, lowered)
                breakpoints = [
                    slot
                    for slot in breakpoints
                    if slot in {0, SLOTS_PER_DAY}
                    or _boundary_evidence(profile, slot, cfg).get("pass")
                ]
                candidate = _breakpoints_to_periods(breakpoints)
                split_steps.append(
                    {
                        "deviationThreshold": round(lowered, 6),
                        "periodCount": len(candidate),
                    }
                )
                if len(candidate) >= cfg.min_periods:
                    periods = candidate
                    threshold = lowered
                    break
            if len(periods) < cfg.min_periods:
                periods = _balanced_periods(cfg.min_periods, cfg.min_slots)
                split_steps.append({"method": "balanced_fallback", "selectedK": len(periods)})

    while len(periods) > cfg.max_periods:
        periods, step = _merge_most_similar_adjacent_periods(periods, total_vph, cfg)
        if step is None:
            periods = _balanced_periods(cfg.max_periods, cfg.min_slots)
            merge_steps.append({"method": "balanced_cap_fallback", "selectedK": len(periods)})
            break
        merge_steps.append(step)

    objective = sum(
        float(segment_metrics[period]["fisherLoss"])
        for period in periods
        if period in segment_metrics
    )
    diagnostics = {
        "method": "multi_signal_cumulative_douglas_peucker",
        "selectedK": len(periods),
        "deviationThreshold": round(threshold, 6),
        "initialBreakpointCount": len(breakpoints) - 1,
        "breakpoints": breakpoints,
        "mergeSteps": merge_steps,
        "splitSteps": split_steps,
    }
    return periods, objective, diagnostics


def _balanced_periods(period_count: int, min_slots: int) -> list[tuple[int, int]]:
    """Evenly divide flat profiles to avoid arbitrary minimum-length fragments."""

    raw_bounds = [
        round(i * SLOTS_PER_DAY / period_count)
        for i in range(period_count + 1)
    ]
    bounds = [0]
    for idx in range(1, period_count):
        lower = bounds[-1] + min_slots
        upper = SLOTS_PER_DAY - (period_count - idx) * min_slots
        bounds.append(min(max(raw_bounds[idx], lower), upper))
    bounds.append(SLOTS_PER_DAY)
    return [(bounds[idx], bounds[idx + 1]) for idx in range(period_count)]


def _snap_period_boundaries(
    periods: list[tuple[int, int]],
    profile: dict[str, Any],
    cfg: SegmentationConfig,
) -> list[tuple[int, int]]:
    """Snap piecewise-linear boundaries back to nearby raw-flow change points."""

    if len(periods) <= 1:
        return periods
    boundaries = [end for _, end in periods[:-1]]
    raw_scores = profile.get("rawBoundaryScores")
    if raw_scores is None:
        return periods
    radius = max(1, cfg.outlier_smooth_slots // 2)
    snapped: list[int] = []
    for idx, boundary in enumerate(boundaries):
        left_start = periods[idx][0] if idx == 0 else snapped[idx - 1]
        right_end = periods[idx + 1][1]
        low = max(left_start + cfg.min_slots, boundary - radius)
        high = min(right_end - cfg.min_slots, boundary + radius)
        if low > high:
            snapped.append(boundary)
            continue
        candidates = range(low, high + 1)
        best = max(
            candidates,
            key=lambda slot: (float(raw_scores[slot]), -abs(slot - boundary), -slot),
        )
        snapped.append(int(best))
    rebuilt: list[tuple[int, int]] = []
    start = 0
    for boundary in snapped:
        rebuilt.append((start, boundary))
        start = boundary
    rebuilt.append((start, SLOTS_PER_DAY))
    return rebuilt


def _merge_similar_periods(
    periods: list[tuple[int, int]],
    segment_metrics: dict[tuple[int, int], dict[str, Any]],
    cfg: SegmentationConfig,
    *,
    profile: dict[str, Any] | None = None,
) -> list[tuple[int, int]]:
    """Merge adjacent low-dissimilarity periods, especially low-flow overnight blocks."""
    merged = list(periods)
    while len(merged) > cfg.min_periods:
        best_idx: int | None = None
        best_score = inf
        for idx in range(len(merged) - 1):
            start_left, end_left = merged[idx]
            start_right, end_right = merged[idx + 1]
            if end_left != start_right:
                continue
            if profile is not None and _boundary_should_preserve(profile, end_left, cfg):
                continue
            left = segment_metrics[(start_left, end_left)]
            right = segment_metrics[(start_right, end_right)]
            absolute_gap = _flow_absolute_gap(left, right)
            local_peak = max(float(left.get("meanTotalVph") or 0.0), float(right.get("meanTotalVph") or 0.0))
            quiet_pair = (
                local_peak < cfg.quiet_flow_vph
                and absolute_gap < cfg.quiet_flow_absolute_gap_vph
            )
            if (
                not quiet_pair
                and _flow_rate_gap(left, right, cfg) >= cfg.cumulative_rate_merge_threshold
                and absolute_gap >= cfg.quiet_flow_absolute_gap_vph
            ):
                continue
            structure_gap = _structure_mean_l1_gap(left, right)
            if (
                not quiet_pair
                and structure_gap >= cfg.structure_change_threshold * cfg.merge_structure_gap_ratio
            ):
                continue
            dissimilarity = _inter_dissimilarity(left, right, cfg)
            if not quiet_pair and dissimilarity >= cfg.merge_dissimilarity_threshold:
                continue
            merged_minutes = (end_right - start_left) * SLOT_MINUTES
            if (
                not quiet_pair
                and merged_minutes > cfg.max_period_minutes
                and dissimilarity >= cfg.long_period_merge_dissimilarity_threshold
            ):
                continue
            if quiet_pair:
                dissimilarity = absolute_gap / max(cfg.quiet_flow_absolute_gap_vph, 1.0)
            merged_metric = segment_metrics[(start_left, end_right)]
            merged_intra = float(merged_metric.get("intraFlowStdGlobalNorm") or 0.0)
            child_intra = max(
                float(left.get("intraFlowStdGlobalNorm") or 0.0),
                float(right.get("intraFlowStdGlobalNorm") or 0.0),
            )
            if (
                merged_intra >= cfg.heterogeneous_split_threshold
                and merged_intra > child_intra + cfg.merge_intra_degradation_tolerance
            ):
                continue
            if dissimilarity < best_score:
                best_score = dissimilarity
                best_idx = idx
        if best_idx is None:
            break
        start_left, _ = merged[best_idx]
        _, end_right = merged[best_idx + 1]
        merged[best_idx : best_idx + 2] = [(start_left, end_right)]
    return merged


def _absorb_short_fragments(
    periods: list[tuple[int, int]],
    segment_metrics: dict[tuple[int, int], dict[str, Any]],
    cfg: SegmentationConfig,
    *,
    profile: dict[str, Any] | None = None,
) -> list[tuple[int, int]]:
    """Merge minimum-duration fragments, especially low-flow overnight slivers."""
    merged = list(periods)
    changed = True
    while changed and len(merged) > cfg.min_periods:
        changed = False
        for idx in range(len(merged)):
            start, end = merged[idx]
            if end - start > cfg.short_fragment_slots:
                boundary_tail = end == SLOTS_PER_DAY and (end - start) <= cfg.min_slots * 4
                if not boundary_tail:
                    continue
            metric = segment_metrics[(start, end)]
            mean_vph = float(metric.get("meanTotalVph") or 0.0)
            low_flow_fragment = mean_vph < cfg.quiet_flow_vph
            boundary_fragment = start == 0 or end == SLOTS_PER_DAY
            operational_fragment = end - start <= cfg.short_fragment_slots
            force_merge = low_flow_fragment or boundary_fragment or operational_fragment
            best_neighbor: int | None = None
            best_score = inf
            for neighbor_idx in (idx - 1, idx + 1):
                if neighbor_idx < 0 or neighbor_idx >= len(merged):
                    continue
                n_start, n_end = merged[neighbor_idx]
                if neighbor_idx < idx:
                    left = segment_metrics[(n_start, n_end)]
                    right = metric
                    merge_start, merge_end = n_start, end
                    boundary_slot = n_end
                else:
                    left = metric
                    right = segment_metrics[(n_start, n_end)]
                    merge_start, merge_end = start, n_end
                    boundary_slot = start
                if profile is not None and _boundary_should_preserve(profile, boundary_slot, cfg):
                    continue
                absolute_gap = _flow_absolute_gap(left, right)
                local_peak = max(float(left.get("meanTotalVph") or 0.0), float(right.get("meanTotalVph") or 0.0))
                quiet_pair = (
                    local_peak < cfg.quiet_flow_vph
                    and absolute_gap < cfg.quiet_flow_absolute_gap_vph
                )
                dissim = _inter_dissimilarity(left, right, cfg)
                structure_gap = _structure_mean_l1_gap(left, right)
                if (
                    not (force_merge or quiet_pair)
                    and structure_gap >= cfg.structure_change_threshold * cfg.merge_structure_gap_ratio
                ):
                    continue
                if not (force_merge or quiet_pair) and dissim >= cfg.merge_dissimilarity_threshold:
                    continue
                merged_metric = segment_metrics[(merge_start, merge_end)]
                merged_intra = float(merged_metric.get("intraFlowStdGlobalNorm") or 0.0)
                child_intra = max(
                    float(left.get("intraFlowStdGlobalNorm") or 0.0),
                    float(right.get("intraFlowStdGlobalNorm") or 0.0),
                )
                score = dissim + max(0.0, merged_intra - child_intra)
                if score < best_score:
                    best_score = score
                    best_neighbor = neighbor_idx
            if best_neighbor is None:
                continue
            if best_neighbor < idx:
                merge_start = merged[best_neighbor][0]
                merge_end = merged[idx][1]
                del merged[idx]
                merged[best_neighbor] = (merge_start, merge_end)
            else:
                merge_start = merged[idx][0]
                merge_end = merged[best_neighbor][1]
                del merged[best_neighbor]
                merged[idx] = (merge_start, merge_end)
            changed = True
            break
    return merged


def _public_period(metric: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in metric.items()
        if key not in {"centroid", "structureMean"}
    }


def _adjacent_pair_metrics(
    periods: list[dict[str, Any]],
    cfg: SegmentationConfig,
) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for left, right in zip(periods, periods[1:], strict=False):
        distance = _inter_dissimilarity(left, right, cfg)
        pairs.append(
            {
                "boundaryTime": right["startTime"],
                "interDissimilarity": round(distance, 4),
                "leftPeriod": f"{left['startTime']}-{left['endTime']}",
                "rightPeriod": f"{right['startTime']}-{right['endTime']}",
            }
        )
    return pairs


def _baseline_4_periods(
    segment_metrics: dict[tuple[int, int], dict[str, Any]],
    cfg: SegmentationConfig,
) -> dict[str, Any]:
    slots = [0, 72, 108, 204, SLOTS_PER_DAY]
    periods = [segment_metrics[(slots[i], slots[i + 1])] for i in range(4)]
    pairs = _adjacent_pair_metrics(periods, cfg)
    return {
        "name": "固定四时段",
        "periods": [
            {
                "startTime": item["startTime"],
                "endTime": item["endTime"],
                "intraFlowStd": item["intraFlowStd"],
                "intraSimilarity": item["intraSimilarity"],
                "intraCost": item["intraCost"],
            }
            for item in periods
        ],
        "avgIntraFlowStd": round(float(np.mean([item["intraFlowStd"] for item in periods])), 2),
        "avgIntraSimilarity": round(float(np.mean([item["intraSimilarity"] for item in periods])), 4),
        "avgInterDissimilarity": round(
            float(np.mean([item["interDissimilarity"] for item in pairs])) if pairs else 0.0,
            4,
        ),
    }


def _constraint_checks(
    periods: list[dict[str, Any]],
    pair_metrics: list[dict[str, Any]],
    cfg: SegmentationConfig,
) -> dict[str, Any]:
    durations = [int(period["durationMinutes"]) for period in periods]
    return {
        "periodCountWithinRange": cfg.min_periods <= len(periods) <= cfg.max_periods,
        "minDurationSatisfied": min(durations or [0]) >= cfg.min_period_minutes,
        "continuousCoverage": _continuous_coverage(periods),
        "avgIntraFlowStd": round(
            float(np.mean([period["intraFlowStd"] for period in periods])) if periods else 0.0,
            2,
        ),
        "avgIntraSimilarity": round(
            float(np.mean([period["intraSimilarity"] for period in periods])) if periods else 0.0,
            4,
        ),
        "avgInterDissimilarity": round(
            float(np.mean([item["interDissimilarity"] for item in pair_metrics])) if pair_metrics else 0.0,
            4,
        ),
    }


def _continuous_coverage(periods: list[dict[str, Any]]) -> bool:
    if not periods:
        return False
    if periods[0]["startSlot"] != 0 or periods[-1]["endSlot"] != SLOTS_PER_DAY:
        return False
    return all(left["endSlot"] == right["startSlot"] for left, right in zip(periods, periods[1:], strict=False))


def _summary(result: dict[str, Any]) -> dict[str, Any]:
    constraints = result["constraints"]
    return {
        "passed": all(
            bool(value)
            for key, value in constraints.items()
            if key not in {"avgIntraSimilarity", "avgInterDissimilarity", "avgIntraFlowStd"}
        ),
        "periodCount": result["periodCount"],
        "avgIntraFlowStd": constraints.get("avgIntraFlowStd"),
        "avgIntraSimilarity": constraints.get("avgIntraSimilarity"),
        "avgInterDissimilarity": constraints.get("avgInterDissimilarity"),
        "completeRate": result["dataQuality"]["completeRate"],
    }


def _slot_to_time(slot: int) -> str:
    minutes = slot * SLOT_MINUTES
    if minutes >= 24 * 60:
        return "24:00"
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _config_to_dict(cfg: SegmentationConfig) -> dict[str, Any]:
    return {
        "minPeriodMinutes": cfg.min_period_minutes,
        "minPeriods": cfg.min_periods,
        "maxPeriods": cfg.max_periods,
        "outlierSmoothWindowMinutes": cfg.outlier_smooth_window_minutes,
        "outlierSmoothPasses": cfg.outlier_smooth_passes,
        "outlierDeviationRatio": cfg.outlier_deviation_ratio,
        "cumulativeDeviationThreshold": cfg.cumulative_deviation_threshold,
        "movementDeviationThreshold": cfg.movement_deviation_threshold,
        "cumulativeRateMergeThreshold": cfg.cumulative_rate_merge_threshold,
        "levelChangeThreshold": cfg.level_change_threshold,
        "structureChangeThreshold": cfg.structure_change_threshold,
        "quietFlowVph": cfg.quiet_flow_vph,
        "quietFlowAbsoluteGapVph": cfg.quiet_flow_absolute_gap_vph,
        "boundaryWindowMinutes": cfg.boundary_window_minutes,
        "uniformFlowCvThreshold": cfg.uniform_flow_cv_threshold,
        "totalFlowWeight": cfg.total_flow_weight,
        "structureWeight": cfg.structure_weight,
        "elbowWeight": cfg.elbow_weight,
        "mutationWeight": cfg.mutation_weight,
        "minRelativeLossDrop": cfg.min_relative_loss_drop,
        "intraWeight": cfg.intra_weight,
        "interWeight": cfg.inter_weight,
        "boundaryPenalty": cfg.boundary_penalty,
        "complexityPenalty": cfg.complexity_penalty,
        "changePointWeight": cfg.change_point_weight,
        "lowFlowVph": cfg.low_flow_vph,
        "heterogeneousSplitThreshold": cfg.heterogeneous_split_threshold,
        "splitGainThreshold": cfg.split_gain_threshold,
        "mergeIntraDegradationTolerance": cfg.merge_intra_degradation_tolerance,
        "shortFragmentMinutes": cfg.short_fragment_minutes,
        "maxPeriodMinutes": cfg.max_period_minutes,
        "flowLevelDeviationThreshold": cfg.flow_level_deviation_threshold,
        "longPeriodMergeDissimilarityThreshold": cfg.long_period_merge_dissimilarity_threshold,
        "shortBoundaryWindowMinutes": cfg.short_boundary_window_minutes,
        "dominantAbsGapVph": cfg.dominant_abs_gap_vph,
        "dominantRelGap": cfg.dominant_rel_gap,
        "dominantShareChangeThreshold": cfg.dominant_share_change_threshold,
        "dominantShareDeviationThreshold": cfg.dominant_share_deviation_threshold,
        "mergeStructureGapRatio": cfg.merge_structure_gap_ratio,
        "compoundStructureGapRatio": cfg.compound_structure_gap_ratio,
        "dominantAbsGapRatio": cfg.dominant_abs_gap_ratio,
        "turnMixRelGap": cfg.turn_mix_rel_gap,
        "turnMixAbsGapVph": cfg.turn_mix_abs_gap_vph,
        "internalSplitMinMinutes": cfg.internal_split_min_minutes,
        "internalCompoundScoreThreshold": cfg.internal_compound_score_threshold,
        "rampMonotonicScoreFactor": cfg.ramp_monotonic_score_factor,
        "rampMinTrendVph": cfg.ramp_min_trend_vph,
        "rampWindowMonotonicFraction": cfg.ramp_window_monotonic_fraction,
        "rampStructureThresholdMultiplier": cfg.ramp_structure_threshold_multiplier,
        "rampTurnMixStructureMultiplier": cfg.ramp_turn_mix_structure_multiplier,
        "inflectionHalfWindowSlots": cfg.inflection_half_window_slots,
        "inflectionScoreThreshold": cfg.inflection_score_threshold,
        "climbBoundaryClusterSlots": cfg.climb_boundary_cluster_slots,
        "spikeBracketMaxMinutes": cfg.spike_bracket_max_minutes,
        "spikeBoundaryRelocateSlots": cfg.spike_boundary_relocate_slots,
    }
