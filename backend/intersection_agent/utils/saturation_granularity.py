"""Canonical saturation summary — one granularity for display, diagnosis, and rules."""

from __future__ import annotations

from typing import Any, Literal

SaturationGranularity = Literal["turn", "lane", "intersection", "none"]


def _positive_floats(rows: list[dict[str, Any]], field: str) -> list[float]:
    out: list[float] = []
    for row in rows:
        raw = row.get(field)
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            out.append(value)
    return out


def canonical_saturation_summary(
    *,
    by_turn: list[dict[str, Any]] | None = None,
    by_lane: list[dict[str, Any]] | None = None,
    inter_saturation_max: float | None = None,
    inter_saturation_avg: float | None = None,
) -> dict[str, Any]:
    """Derive headline saturation from the finest available DB granularity.

    Priority (display / diagnosis / rules must share this):
    1. turn — AVG(turn_saturation) per movement in granularity.by_turn
    2. lane — lane_saturation in granularity.by_lane
    3. intersection — dws_inter_evaluation saturation_max / saturation_avg
  """
    turn_sats = _positive_floats(by_turn or [], "turn_saturation")
    if turn_sats:
        peak = max(turn_sats)
        trough = min(turn_sats)
        return {
            "granularity": "turn",
            "saturation_rate": round(peak, 4),
            "turn_saturation_max": round(peak, 4),
            "turn_saturation_min": round(trough, 4),
            "turn_saturation_spread": round(peak - trough, 4),
        }

    lane_sats = _positive_floats(by_lane or [], "lane_saturation")
    if lane_sats:
        peak = max(lane_sats)
        trough = min(lane_sats)
        return {
            "granularity": "lane",
            "saturation_rate": round(peak, 4),
            "turn_saturation_max": round(peak, 4),
            "turn_saturation_min": round(trough, 4),
            "turn_saturation_spread": round(peak - trough, 4),
        }

    inter_peak = inter_saturation_max if inter_saturation_max and inter_saturation_max > 0 else None
    if inter_peak is None and inter_saturation_avg and inter_saturation_avg > 0:
        inter_peak = inter_saturation_avg
    if inter_peak is not None:
        return {
            "granularity": "intersection",
            "saturation_rate": round(float(inter_peak), 4),
            "turn_saturation_max": round(float(inter_peak), 4),
            "turn_saturation_min": None,
            "turn_saturation_spread": None,
        }

    return {
        "granularity": "none",
        "saturation_rate": None,
        "turn_saturation_max": None,
        "turn_saturation_min": None,
        "turn_saturation_spread": None,
    }


def max_turn_saturation_from_rows(by_turn: list[dict[str, Any]] | None) -> float | None:
    """Max AVG turn_saturation from granularity.by_turn (same as left runtime panel)."""
    sats = _positive_floats(by_turn or [], "turn_saturation")
    return round(max(sats), 4) if sats else None


def apply_canonical_saturation_to_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Rewrite traffic_flow saturation fields from granularity — single source of truth."""
    gran = data.get("granularity") or {}
    ev = data.get("evaluation") or {}
    summary = canonical_saturation_summary(
        by_turn=gran.get("by_turn"),
        by_lane=gran.get("by_lane"),
        inter_saturation_max=_float_or_none(ev.get("saturation_max")),
        inter_saturation_avg=_float_or_none(ev.get("saturation_avg")),
    )
    if summary.get("saturation_rate") is not None:
        tf = dict(data.get("traffic_flow") or {})
        tf["saturation_rate"] = summary["saturation_rate"]
        tf["turn_saturation_max"] = summary["turn_saturation_max"]
        tf["turn_saturation_spread"] = summary.get("turn_saturation_spread")
        tf["saturation_granularity"] = summary["granularity"]
        data["traffic_flow"] = tf
    return summary


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
