"""Deterministic congestion scoring for corridor scan ranking."""

from __future__ import annotations


def congestion_score(
    saturation_max: float | None,
    delay_index: float | None = None,
    unbalance_index: float | None = None,
) -> float:
    """Weighted score in [0, 1] for ranking intersections on a corridor."""
    sat = saturation_max if saturation_max is not None else 0.0
    sat_norm = min(max(sat, 0.0), 1.5) / 1.5
    if delay_index is not None:
        delay_norm = min(max(delay_index, 0.0), 3.0) / 3.0
        return 0.6 * sat_norm + 0.4 * delay_norm
    imb = unbalance_index if unbalance_index is not None else 0.0
    imb_norm = min(max(imb, 0.0), 1.0)
    return 0.75 * sat_norm + 0.25 * imb_norm


def level_label(saturation_max: float | None, *, has_data: bool) -> str:
    if not has_data or saturation_max is None:
        return "暂无数据"
    sat = float(saturation_max)
    if sat >= 0.90:
        return "严重"
    if sat >= 0.75:
        return "较重"
    if sat >= 0.60:
        return "中等"
    return "基本畅通"


def severity_level(saturation_max: float | None, *, has_data: bool) -> str:
    if not has_data or saturation_max is None:
        return "unknown"
    sat = float(saturation_max)
    if sat >= 0.90:
        return "high"
    if sat >= 0.75:
        return "medium"
    if sat >= 0.60:
        return "low"
    return "low"


def format_annotation(saturation_max: float | None, *, has_data: bool) -> str:
    label = level_label(saturation_max, has_data=has_data)
    if not has_data or saturation_max is None:
        return label
    return f"饱和{float(saturation_max):.2f}·{label}"
