"""Task 4.2 — 批量扫描编排（并发 + 失败隔离）。"""

import asyncio

import pytest

from region_scan.config import get_scan_settings
from region_scan.scan_engine import run_region_scan

THRESHOLDS = {"saturation": {"oversaturation": 0.90, "high": 0.80}}


def _fake_inters(n: int):
    return [
        {"inter_id": f"I{i}", "inter_name": f"路口{i}", "lon": 117.0 + i, "lat": 36.0 + i}
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_scan_runs_all_inters_and_periods():
    inters = _fake_inters(4)

    async def fake_enumerate(pool, settings, **kw):
        return inters

    async def fake_diagnose(pool, settings, inter, period):
        # I2 在某时段失败 → 应被隔离，不影响其余
        if inter["inter_id"] == "I2" and period == "早高峰":
            raise RuntimeError("boom")
        sat = 0.95 if inter["inter_id"] == "I0" else 0.75
        return {
            "inter_id": inter["inter_id"],
            "inter_name": inter["inter_name"],
            "lon": inter["lon"],
            "lat": inter["lat"],
            "period": period,
            "metrics": {"saturation_max": sat, "unbalance_index": 0.4, "green_utilization": 0.5},
            "top_issues": ["失衡"],
            "severity": "medium",
            "control_improvement_ceiling": "low" if sat >= 0.9 else "high",
            "governance_summary": "x",
            "governance_actions": [],
            "has_data": True,
            "data_quality_tags": [],
        }

    run = await run_region_scan(
        pool=None,
        settings=get_scan_settings(),
        periods=["早高峰", "白平峰", "晚高峰"],
        enumerate_fn=fake_enumerate,
        diagnose_fn=fake_diagnose,
        thresholds=THRESHOLDS,
    )

    # 4 路口 × 3 时段 = 12 条
    assert len(run.records) == 12
    assert run.intersection_total == 4

    # 失败记录被隔离为「数据不足」
    failed = [r for r in run.records if r["inter_id"] == "I2" and r["period"] == "早高峰"]
    assert len(failed) == 1 and failed[0]["problem_band"] == "数据不足"
    assert failed[0]["has_data"] is False

    # 分层正确：I0 过饱和→工程可解；其余→配时可解
    i0 = [r for r in run.records if r["inter_id"] == "I0"]
    assert all(r["problem_band"] == "工程可解" for r in i0)
    assert all(r["pilot_score"] is None for r in i0)

    timing = [r for r in run.records if r["problem_band"] == "配时可解"]
    assert timing and all(r["pilot_score"] is not None and r["pilot_score"] > 0 for r in timing)


@pytest.mark.asyncio
async def test_concurrency_is_bounded():
    inters = _fake_inters(6)
    state = {"active": 0, "max": 0}

    async def fake_enumerate(pool, settings, **kw):
        return inters

    async def fake_diagnose(pool, settings, inter, period):
        state["active"] += 1
        state["max"] = max(state["max"], state["active"])
        await asyncio.sleep(0.01)
        state["active"] -= 1
        return {
            "inter_id": inter["inter_id"],
            "period": period,
            "metrics": {"saturation_max": 0.7},
            "top_issues": [],
            "severity": "none",
            "control_improvement_ceiling": "medium",
            "has_data": True,
            "data_quality_tags": [],
        }

    await run_region_scan(
        pool=None,
        settings=get_scan_settings(),
        periods=["早高峰"],
        concurrency=2,
        enumerate_fn=fake_enumerate,
        diagnose_fn=fake_diagnose,
        thresholds=THRESHOLDS,
    )
    assert state["max"] <= 2
