"""单条干线 MVP：固定子区、固定相位顺序，联合优化周期 / 协调相位绿时 / 偏移.

默认目标：双向绿波（通过对向行程时间链）下最大化「最小协调绿时」并惩罚周期模上的对齐误差。
延误：可选饱和度下的 Webster 近似（无流量数据时用默认饱和度）。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import Any, Sequence

import numpy as np
from scipy.optimize import minimize

# ---------- 数据契约 ----------


@dataclass(frozen=True)
class ArterialLink:
    """沿 forward 方向，从 intersection_ids[i] 到 intersection_ids[i+1]."""

    distance_m: float
    forward_speed_kmh: float
    reverse_speed_kmh: float | None = None

    def forward_travel_s(self) -> float:
        return _travel_time_s(self.distance_m, self.forward_speed_kmh)

    def reverse_travel_s(self) -> float:
        v = self.reverse_speed_kmh if self.reverse_speed_kmh is not None else self.forward_speed_kmh
        return _travel_time_s(self.distance_m, v)


def _travel_time_s(distance_m: float, speed_kmh: float) -> float:
    if speed_kmh <= 0.1:
        speed_kmh = 0.1
    if distance_m < 0:
        distance_m = 0.0
    return float(distance_m) / (float(speed_kmh) / 3.6)


def _modular_pen(delta: float, c: float) -> float:
    """min_k (delta - k*c)^2，k 取小整数邻域，供无梯度断点处仍可用数值优化."""
    if c <= 1e-6:
        return 1e12
    best = inf
    for k in (-2, -1, 0, 1, 2):
        v = delta - k * c
        best = min(best, v * v)
    return float(best)


def _webster_approach_delay_s(cycle_s: float, green_s: float, x: float) -> float:
    """单进口道 Webster 平均延误（秒/车）；x 为饱和度，需 < 1."""
    if cycle_s <= 0 or green_s <= 0:
        return 0.0
    lam = min(0.99, max(0.01, green_s / cycle_s))
    x = min(0.95, max(0.05, x))
    denom = 1.0 - lam * x
    if denom <= 1e-6:
        return cycle_s
    return 0.5 * cycle_s * (1.0 - lam) ** 2 / denom


def solve_arterial_two_way_max_bandwidth(
    intersection_ids: Sequence[str],
    links: Sequence[ArterialLink],
    *,
    min_cycle_s: float = 60.0,
    max_cycle_s: float = 120.0,
    min_green_s: float = 12.0,
    max_green_s: float = 45.0,
    lost_time_s: float = 0.0,
    saturation_x: Sequence[float] | None = None,
    progression_weight: float = 0.08,
    random_seed: int = 0,
) -> dict[str, Any]:
    """求解干线双向绿波 MVP，返回结构化结果（供 corridor 组装 plan）.

    progression_weight 越大越强调相位差与行程时间的周期对齐，越小越接近「只拉大最小绿时」.
    """
    ids = [str(x) for x in intersection_ids]
    n = len(ids)
    link_list = list(links)
    if n == 0:
        return {"ok": False, "error": "intersection_ids 为空", "nodes": [], "kpis": {}}
    if n == 1:
        c0 = float(np.clip(0.5 * (min_cycle_s + max_cycle_s), min_cycle_s, max_cycle_s))
        g0 = float(np.clip(0.35 * c0, min_green_s, min(max_green_s, c0 - lost_time_s)))
        x0 = float(saturation_x[0]) if saturation_x and len(saturation_x) > 0 else 0.5
        d0 = _webster_approach_delay_s(c0, g0, x0)
        return {
            "ok": True,
            "cycle_s": c0,
            "strategy": "bidirectional_max_bandwidth",
            "bandwidth_s": g0,
            "total_delay_s": d0,
            "nodes": [
                {
                    "intersection_id": ids[0],
                    "offset_s": 0.0,
                    "cycle_s": c0,
                    "coordinated_green_s": g0,
                    "green_ratio": g0 / c0 if c0 else 0.0,
                    "webster_delay_s": d0,
                }
            ],
            "kpis": {
                "bandwidth_s": g0,
                "total_webster_delay_s": d0,
                "progression_penalty": 0.0,
            },
            "meta": {"solver": "scipy_minimize_SLSQP", "notes": ["单路口无协调链接，仅返回可行配时。"]},
        }
    if len(link_list) != n - 1:
        return {
            "ok": False,
            "error": f"links 数量应为 {n - 1}，实际为 {len(link_list)}",
            "nodes": [],
            "kpis": {},
        }

    tau_f = np.array([lk.forward_travel_s() for lk in link_list], dtype=float)
    tau_b = np.array([lk.reverse_travel_s() for lk in link_list], dtype=float)
    x_per = (
        np.array([float(saturation_x[i]) for i in range(n)], dtype=float)
        if saturation_x is not None and len(saturation_x) >= n
        else np.full(n, 0.5, dtype=float)
    )

    c_lo, c_hi = float(min_cycle_s), float(max_cycle_s)
    g_lo, g_hi = float(min_green_s), float(max_green_s)
    lt = max(0.0, float(lost_time_s))
    w = float(progression_weight)
    rng = np.random.default_rng(random_seed)

    def unpack(y: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
        c = float(y[0])
        g = np.clip(y[1 : 1 + n], g_lo, g_hi)
        f = np.zeros(n, dtype=float)
        f[0] = 0.0
        f[1:] = np.clip(y[1 + n :], 0.0, 1.0 - 1e-9)
        return c, g, f

    def penalty(c: float, f: np.ndarray) -> float:
        if c <= lt + 1e-6:
            return 1e12
        p = 0.0
        theta = f * c
        for i in range(n - 1):
            d_f = theta[i + 1] - theta[i] - tau_f[i]
            p += _modular_pen(d_f, c)
            d_b = theta[i] - theta[i + 1] - tau_b[i]
            p += _modular_pen(d_b, c)
        return p

    def objective(y: np.ndarray) -> float:
        c, g, f = unpack(y)
        if c < c_lo or c > c_hi:
            return 1e9
        if np.any(g > c - lt - 1e-6) or np.any(g < g_lo):
            return 1e9
        b = float(np.min(g))
        pen = penalty(c, f)
        return -(b - w * pen)

    def cons_cycle_green(y: np.ndarray) -> np.ndarray:
        c, g, _f = unpack(y)
        return np.array([c - c_lo, c_hi - c, *(c - lt - g)], dtype=float)

    x0_core = []
    for _ in range(5):
        c = float(rng.uniform(c_lo, c_hi))
        g = np.clip(rng.uniform(g_lo, min(g_hi, c - lt - 1.0), size=n), g_lo, g_hi)
        f_inner = np.sort(rng.uniform(0.0, 1.0, size=n - 1))
        x0_core.append(np.concatenate([[c], g, f_inner]))
    # 平直初值
    c_mid = float(np.clip(0.5 * (c_lo + c_hi), c_lo, c_hi))
    g_mid = np.full(n, np.clip(0.33 * c_mid, g_lo, min(g_hi, c_mid - lt - 1.0)))
    f_mid = np.linspace(0.0, 0.4, n - 1)
    x0_core.append(np.concatenate([[c_mid], g_mid, f_mid]))

    bounds = [(c_lo, c_hi)] + [(g_lo, g_hi)] * n + [(0.0, 1.0 - 1e-9)] * (n - 1)
    constraints = {"type": "ineq", "fun": cons_cycle_green}

    best: dict[str, Any] | None = None
    best_obj = inf
    for x0 in x0_core:
        res = minimize(
            objective,
            x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 400, "ftol": 1e-6},
        )
        if res.success and res.fun < best_obj:
            best_obj = float(res.fun)
            best = {"x": res.x, "message": res.message}
        elif res.fun < best_obj:
            best_obj = float(res.fun)
            best = {"x": res.x, "message": res.message}

    if best is None:
        return {"ok": False, "error": "优化未产生候选解", "nodes": [], "kpis": {}}

    c_opt, g_opt, f_opt = unpack(np.asarray(best["x"], dtype=float))
    pen_opt = penalty(c_opt, f_opt)
    theta_opt = f_opt * c_opt
    delays = [_webster_approach_delay_s(c_opt, float(g_opt[i]), float(x_per[i])) for i in range(n)]

    nodes = []
    for i in range(n):
        nodes.append(
            {
                "intersection_id": ids[i],
                "offset_s": float(theta_opt[i]),
                "cycle_s": float(c_opt),
                "coordinated_green_s": float(g_opt[i]),
                "green_ratio": float(g_opt[i] / c_opt) if c_opt else 0.0,
                "webster_delay_s": float(delays[i]),
            }
        )

    bw = float(np.min(g_opt))
    return {
        "ok": True,
        "cycle_s": float(c_opt),
        "strategy": "bidirectional_max_bandwidth",
        "bandwidth_s": bw,
        "total_delay_s": float(sum(delays)),
        "nodes": nodes,
        "kpis": {
            "bandwidth_s": bw,
            "total_webster_delay_s": float(sum(delays)),
            "progression_penalty": float(pen_opt),
        },
        "meta": {
            "solver": "scipy_minimize_SLSQP",
            "multi_start": len(x0_core),
            "solver_message": str(best.get("message", "")),
        },
    }
