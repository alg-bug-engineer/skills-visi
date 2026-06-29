"""Task 1.1 — 枚举全部信号路口（MOCK_DB=1，注入假 fetch 验证解析/过滤）。"""

import pytest

from region_scan.config import get_scan_settings
from region_scan.enumerate_intersections import enumerate_signalized_intersections


@pytest.mark.asyncio
async def test_enumerate_returns_signalized_with_coords():
    rows = [
        {"inter_id": "A1", "inter_name": "经十路与历山路", "geom_center": "POINT(117.05 36.65)"},
        {"inter_id": "A2", "inter_name": "无坐标路口", "geom_center": None},
        {"inter_id": "A3", "inter_name": "坏坐标路口", "geom_center": "GARBAGE"},
        {"inter_id": "A4", "inter_name": None, "geom_center": "POINT(117.11 36.60)"},
    ]

    captured = {}

    async def fake_fetch(sql, *params):
        captured["sql"] = sql
        captured["params"] = params
        return rows

    result = await enumerate_signalized_intersections(
        pool=None, settings=get_scan_settings(), fetch=fake_fetch
    )

    # 只保留可解析坐标的路口；A2/A3 被丢弃
    assert [r["inter_id"] for r in result] == ["A1", "A4"]
    assert result[0] == {
        "inter_id": "A1",
        "inter_name": "经十路与历山路",
        "lon": 117.05,
        "lat": 36.65,
    }
    # inter_name 缺省时回退为 inter_id
    assert result[1]["inter_name"] == "A4"

    # SQL 按版本 + 信号 + 有坐标过滤
    sql = captured["sql"]
    assert "is_signalized = 1" in sql
    assert "geom_center IS NOT NULL" in sql
    assert "version_id = $1" in sql
    assert captured["params"][0] == get_scan_settings().pg_version_id
