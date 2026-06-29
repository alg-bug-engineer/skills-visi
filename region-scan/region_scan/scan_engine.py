"""区域批量扫描编排：枚举 → 并发逐路口诊断 → 分层评分 → 汇总快照。

- 并发受 ``asyncio.Semaphore(concurrency)`` 限制，避免压垮 PG。
- 单 ``(inter, period)`` 失败被隔离为「数据不足」记录，不中断整体（断点续跑友好）。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Awaitable, Callable

from intersection_agent.utils.thresholds_loader import load_thresholds

from region_scan.classify import classify_problem_band, pilot_score
from region_scan.diagnose_one import diagnose_one
from region_scan.enumerate_intersections import enumerate_signalized_intersections
from region_scan.snapshot import ScanRun

logger = logging.getLogger(__name__)

EnumerateFn = Callable[..., Awaitable[list[dict[str, Any]]]]
DiagnoseFn = Callable[..., Awaitable[dict[str, Any]]]

ProgressFn = Callable[[int, int], None]


def _failure_record(inter: dict[str, Any], period: str, reason: str) -> dict[str, Any]:
    return {
        "inter_id": str(inter.get("inter_id")),
        "inter_name": inter.get("inter_name"),
        "lon": inter.get("lon"),
        "lat": inter.get("lat"),
        "period": period,
        "metrics": {"saturation_max": None, "unbalance_index": None, "green_utilization": None},
        "top_issues": [],
        "severity": "none",
        "control_improvement_ceiling": "medium",
        "governance_summary": "",
        "governance_actions": [],
        "has_data": False,
        "data_quality_tags": [reason],
        "problem_band": "数据不足",
        "pilot_score": None,
    }


async def run_region_scan(
    pool: Any,
    settings: Any,
    *,
    periods: list[str] | None = None,
    concurrency: int | None = None,
    region: str = "全域",
    enumerate_fn: EnumerateFn | None = None,
    diagnose_fn: DiagnoseFn | None = None,
    thresholds: dict[str, Any] | None = None,
    progress: ProgressFn | None = None,
) -> ScanRun:
    """跑一次区域扫描，返回（未落盘的）``ScanRun``。"""
    periods = periods or list(getattr(settings, "periods", ["早高峰", "白平峰", "晚高峰"]))
    concurrency = concurrency or int(getattr(settings, "concurrency", 4))
    enumerate_fn = enumerate_fn or enumerate_signalized_intersections
    diagnose_fn = diagnose_fn or diagnose_one
    thresholds = thresholds if thresholds is not None else load_thresholds()

    inters = await enumerate_fn(pool, settings)
    total_jobs = len(inters) * len(periods)
    sem = asyncio.Semaphore(concurrency)
    done = 0
    lock = asyncio.Lock()

    async def one(inter: dict[str, Any], period: str) -> dict[str, Any]:
        nonlocal done
        async with sem:
            try:
                diag = await diagnose_fn(pool, settings, inter, period)
                band = classify_problem_band(diag, thresholds)
                diag = {**diag, "problem_band": band, "pilot_score": pilot_score(diag, band)}
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "scan failed inter=%s period=%s: %s",
                    inter.get("inter_id"),
                    period,
                    exc,
                )
                diag = _failure_record(inter, period, "scan_failed")
        async with lock:
            done += 1
            if progress:
                progress(done, total_jobs)
        return diag

    tasks = [one(inter, period) for inter in inters for period in periods]
    records = await asyncio.gather(*tasks)

    covered_inters = {
        r["inter_id"] for r in records if r.get("has_data") and r.get("problem_band") != "数据不足"
    }

    run = ScanRun(
        run_id=ScanRun.new_run_id(),
        created_at=datetime.now().isoformat(timespec="seconds"),
        region=region,
        version_id=str(getattr(settings, "pg_version_id", "")),
        periods=periods,
        intersection_total=len(inters),
        covered=len(covered_inters),
        records=list(records),
    )
    return run
