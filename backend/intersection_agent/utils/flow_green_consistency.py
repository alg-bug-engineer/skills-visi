"""Flow share vs effective-green share consistency (Spearman rank correlation)."""

from __future__ import annotations

from typing import Any


def flow_green_check(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare flow share with green share within a comparable movement family."""
    pairs = [
        (
            str(item.get("movement_key") or item.get("label") or ""),
            _to_float(item.get("flow_vph") or item.get("turn_flow_total")) or 0.0,
            _to_float(item.get("effective_green_s") or item.get("green_time_plan")) or 0.0,
        )
        for item in items
    ]
    pairs = [(key, flow, green) for key, flow, green in pairs if key and flow > 0 and green > 0]
    if len(pairs) < 2:
        return {
            "spearman_tau": None,
            "flow_shares": [],
            "green_shares": [],
            "verdict": "insufficient",
            "narrative": "转向流量或配时样本不足，暂无法评价流量-绿信比一致性",
        }

    flows = [flow for _, flow, _ in pairs]
    greens = [green for _, _, green in pairs]
    tau = _spearman(flows, greens)
    flow_total = sum(flows)
    green_total = sum(greens)
    flow_shares = [round(value / flow_total, 4) for value in flows] if flow_total else []
    green_shares = [round(value / green_total, 4) for value in greens] if green_total else []
    if tau is not None and tau >= 0.8:
        verdict = "strong"
        narrative = "各转向流量占比与有效绿灯占比高度一致，配时结构基本匹配需求"
    elif tau is not None and tau >= 0.0:
        verdict = "weak"
        narrative = "流量与绿信比存在一定偏差，部分转向配时与需求匹配偏弱"
    else:
        verdict = "mismatch"
        narrative = "高流量转向的有效绿灯占比偏低，存在明显的流量-配时失配"
    return {
        "spearman_tau": tau,
        "flow_shares": flow_shares,
        "green_shares": green_shares,
        "verdict": verdict,
        "narrative": narrative,
        "items": [
            {"label": key, "flow_vph": flow, "effective_green_s": green}
            for key, flow, green in pairs
        ],
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
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
