"""DataFetcher DWS fallback logic tests."""

from datetime import date

import pytest

from intersection_agent.config import Settings
from intersection_agent.models.domain import NluResult, TimePeriod
from intersection_agent.services.data_fetcher import DataFetcher, _dws_dow_for_query
from intersection_agent.utils.data_window import build_data_window


def test_dws_uses_primary_dow_when_dwd_empty():
    window = build_data_window(
        TimePeriod(start="16:00", end="18:00", label="晚高峰"),
        reference_date=date(2026, 6, 24),  # 周三
    )
    assert window.primary_dow == 3
    assert _dws_dow_for_query(window, dwd_has_data=False) == (3,)


def test_dws_uses_full_filter_when_dwd_hit():
    window = build_data_window(
        TimePeriod(start="16:00", end="18:00", label="晚高峰"),
        reference_date=date(2026, 6, 24),
    )
    assert _dws_dow_for_query(window, dwd_has_data=True) == (1, 2, 3, 4, 5)


def test_date_values_for_asyncpg():
    window = build_data_window(
        TimePeriod(start="16:00", end="18:00", label="晚高峰"),
        reference_date=date(2026, 6, 24),
    )
    assert window.date_from_value == date(2026, 6, 18)
    assert window.date_to_value == date(2026, 6, 24)


class _TracePool:
    async def connect(self):
        return None

    async def fetchrow(self, query, *args):
        if "dwd_tfc_inter_dir_perf_5min" in query:
            return {"delay_index": 2.0, "sample_count": 6}
        if "dws_inter_evaluation_5min_mm" in query:
            return {
                "saturation_max": 0.91,
                "saturation_avg": 0.82,
                "imbalance_index": 0.31,
            }
        if "dws_turn_green_utilization_5min_mm" in query:
            return {"green_utilization": 0.42, "empty_green_rate": 0.08}
        if "dws_turn_saturation_5min_mm" in query:
            return {"turn_saturation": 0.93}
        if "dwd_ctl_inter_plan_cfg" in query:
            return {"cycle_length": 120, "green_ratio": 0.3}
        return None

    async def fetch(self, query, *args):
        if "dwd_tfc_rltn_wide_inter_ft_link" in query:
            return [{"turn_move": "直行", "lane_info": "直行车道"}]
        return []


class _ByTurnPool(_TracePool):
    async def fetch(self, query, *args):
        if "GROUP BY ts.dir8_code, ts.turn_dir_no" in query:
            return [
                {"dir8_code": 2, "turn_dir_no": 1, "turn_saturation": 1.73, "green_utilization": 0.9},
            ]
        return await super().fetch(query, *args)


@pytest.mark.asyncio
async def test_by_turn_keeps_dir8_and_turn_codes():
    """TC by_turn_dir_fields：by_turn 行须带 dir8_code/turn_dir_no（溯源对齐用）。"""
    settings = Settings(mock_db=False, pg_flow_schema="flow", pgschema="road", pg_version_id="v1")
    fetcher = DataFetcher(pool=_ByTurnPool(), settings=settings)
    nlu = NluResult(
        intersection="x",
        time_period=TimePeriod(start="16:00", end="18:00", label="晚高峰"),
        problem_type="congestion",
        directions=["东西向"],
    )
    payload = await fetcher.fetch("inter_001", "x", nlu, reference_date=date(2026, 6, 24))
    by_turn = payload["granularity"]["by_turn"]
    assert by_turn
    assert by_turn[0]["dir8_code"] == 2
    assert by_turn[0]["turn_dir_no"] == 1
    assert by_turn[0]["label"]


@pytest.mark.asyncio
async def test_fetch_keeps_sql_and_raw_rows_for_replay(caplog):
    settings = Settings(mock_db=False, pg_flow_schema="flow", pgschema="road", pg_version_id="v1")
    fetcher = DataFetcher(pool=_TracePool(), settings=settings)
    nlu = NluResult(
        intersection="奥体西路与经十路交叉口",
        time_period=TimePeriod(start="16:00", end="18:00", label="晚高峰"),
        problem_type="congestion",
        directions=["南北向"],
    )

    with caplog.at_level("INFO"):
        payload = await fetcher.fetch(
            "inter_001",
            "奥体西路与经十路交叉口",
            nlu,
            reference_date=date(2026, 6, 24),
        )

    trace = payload["meta"]["query_trace"]
    assert trace
    assert any("dwd_tfc_inter_dir_perf_5min" in item["sql"] for item in trace)
    assert all("$1" not in item["sql"] for item in trace)
    assert all("$2" not in item["sql"] for item in trace)
    assert "'inter_001'" in trace[0]["sql"]
    assert "ARRAY[1, 2, 3, 4, 5]" in trace[0]["sql"]
    assert any(item["raw_data"] for item in trace)
    assert "inter_001" in trace[0]["params"]
    assert "data_fetch.sql" in caplog.text
    assert "$1" not in caplog.text
    assert "data_fetch.raw" in caplog.text
