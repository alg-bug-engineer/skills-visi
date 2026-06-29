"""Task 2.1 — 单路口完整诊断包装（MOCK_DB=1，复用 backend mock 数据）。"""

import pytest

from intersection_agent.db.postgres import PostgresPool

from region_scan.config import get_scan_settings
from region_scan.diagnose_one import diagnose_one

UNIFIED_KEYS = {
    "inter_id",
    "inter_name",
    "period",
    "scene_type",
    "pressure_level",
    "metrics",
    "top_issues",
    "severity",
    "control_improvement_ceiling",
    "governance_summary",
    "governance_actions",
    "has_data",
    "data_quality_tags",
}


@pytest.mark.asyncio
async def test_diagnose_one_returns_unified_shape():
    settings = get_scan_settings()
    pool = PostgresPool(settings.base)  # mock_db=1 → 短路
    inter = {"inter_id": "X1", "inter_name": "测试拥堵路口", "lon": 117.0, "lat": 36.6}

    diag = await diagnose_one(pool, settings, inter, "早高峰")

    assert UNIFIED_KEYS <= set(diag)
    assert diag["inter_id"] == "X1"
    assert diag["period"] == "早高峰"
    assert diag["has_data"] is True

    # backend mock 拥堵路口：饱和度 0.88 / 失衡 0.35 / 绿灯利用率 0.45
    m = diag["metrics"]
    assert m["saturation_max"] == pytest.approx(0.88, abs=0.01)
    assert m["unbalance_index"] == pytest.approx(0.35, abs=0.01)
    assert m["green_utilization"] == pytest.approx(0.45, abs=0.01)

    # 应检出失衡 / 绿灯空放等信控问题
    assert diag["top_issues"]
    assert diag["severity"] in {"high", "medium", "low"}
    assert diag["control_improvement_ceiling"] in {"high", "medium", "low"}
    assert diag["governance_summary"]
    assert isinstance(diag["governance_actions"], list) and diag["governance_actions"]
    assert isinstance(diag["data_quality_tags"], list)
    assert diag["pressure_level"]


@pytest.mark.asyncio
async def test_diagnose_one_non_oversaturated_not_engineering():
    """非过饱和路口（sat 0.55）不应被判为工程问题（信控改善上限不为 low）。

    注：backend 的 MOCK 证据/持续性夹具固定返回演示拥堵值，无法在 mock 下复现
    「完全无问题」，故无问题口径在 classify 单测（合成 diag）中验证。
    """
    settings = get_scan_settings()
    pool = PostgresPool(settings.base)
    # backend mock：inter_name 含「低饱和」→ 平稳数据（sat 0.55）
    inter = {"inter_id": "X2", "inter_name": "低饱和测试路口", "lon": 117.1, "lat": 36.6}

    diag = await diagnose_one(pool, settings, inter, "晚高峰")

    assert diag["has_data"] is True
    assert diag["metrics"]["saturation_max"] == pytest.approx(0.55, abs=0.01)
    # 未过饱和 → 配时仍有改善空间，不应是「工程可解 / 配时无效」
    assert diag["control_improvement_ceiling"] in {"high", "medium"}
