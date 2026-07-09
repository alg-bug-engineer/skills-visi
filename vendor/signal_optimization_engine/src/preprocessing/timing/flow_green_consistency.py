"""Flow-green consistency checks for atom-lane mappings."""

from __future__ import annotations

from typing import Any


def effective_green_by_movement(stages: list[dict[str, Any]]) -> dict[str, float]:
    """Sum historical green seconds for every movementKey appearing in stages."""
    greens: dict[str, float] = {}
    for stage in stages:
        timing = stage.get("currentTiming") or {}
        green = _to_float(timing.get("greenSec") or stage.get("green_sec")) or 0.0
        for item in stage.get("phaseDirInfoDTOList") or stage.get("phase_dir_info_list") or []:
            movement_key = item.get("movementKey")
            if movement_key:
                greens[str(movement_key)] = greens.get(str(movement_key), 0.0) + green
    return greens


def flow_green_check(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare flow share with effective-green share within a comparable family."""
    pairs = [
        (
            str(item.get("movementKey") or ""),
            _to_float(item.get("flowVph") or item.get("turnFlowTotal")) or 0.0,
            _to_float(item.get("effectiveGreenS")) or 0.0,
        )
        for item in items
    ]
    pairs = [(key, flow, green) for key, flow, green in pairs if key and flow > 0 and green > 0]
    if len(pairs) < 2:
        return {"spearmanTau": None, "flowShares": [], "greenShares": [], "verdict": "insufficient"}

    flows = [flow for _, flow, _ in pairs]
    greens = [green for _, _, green in pairs]
    tau = _spearman(flows, greens)
    flow_total = sum(flows)
    green_total = sum(greens)
    flow_shares = [round(value / flow_total, 4) for value in flows] if flow_total else []
    green_shares = [round(value / green_total, 4) for value in greens] if green_total else []
    verdict = "strong" if tau is not None and tau >= 0.8 else "weak" if tau is not None and tau >= 0 else "mismatch"
    return {
        "spearmanTau": tau,
        "flowShares": flow_shares,
        "greenShares": green_shares,
        "verdict": verdict,
    }


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    rx = _ranks(xs)
    ry = _ranks(ys)
    mean_x = sum(rx) / len(rx)
    mean_y = sum(ry) / len(ry)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(rx, ry))
    den_x = sum((x - mean_x) ** 2 for x in rx) ** 0.5
    den_y = sum((y - mean_y) ** 2 for y in ry) ** 0.5
    if den_x == 0 or den_y == 0:
        return None
    return round(num / (den_x * den_y), 4)


def _ranks(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    idx = 0
    while idx < len(indexed):
        end = idx + 1
        while end < len(indexed) and indexed[end][1] == indexed[idx][1]:
            end += 1
        rank = (idx + end + 1) / 2.0
        for original_idx, _ in indexed[idx:end]:
            ranks[original_idx] = rank
        idx = end
    return ranks


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
