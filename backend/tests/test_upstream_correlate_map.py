"""UpstreamCorrelateMapService：溯源表全量路口 link 地图。"""
from __future__ import annotations

import pytest

from intersection_agent.services.upstream_correlate_map_service import UpstreamCorrelateMapService
from intersection_agent.utils.data_window import build_data_window
from intersection_agent.models.domain import TimePeriod


@pytest.mark.asyncio
async def test_mock_correlate_map_distinct_upstream():
    from intersection_agent.config import Settings

    svc = UpstreamCorrelateMapService(settings=Settings(mock_db=True, mock_llm=True))
    window = build_data_window(TimePeriod(label="晚高峰", start="17:00", end="19:00"))
    payload = await svc.build(
        "inter_demo",
        dir8=6,
        turn_no=2,
        approach="西进口",
        window=window,
        period_label="晚高峰",
        cognition={"intersection": {"name": "演示路口", "lon": 117.11, "lat": 36.65}},
    )
    assert payload is not None
    assert payload["stats"]["distinct_upstream"] == 3
    assert len(payload["intersections"]) == 4
    target = payload["intersections"][0]
    assert target["role"] == "target"
    assert len(target["links"]) >= 1
    upstream = [n for n in payload["intersections"] if n["role"] == "upstream"]
    assert len(upstream) == 3
    main = [n for n in upstream if n["in_main_corridor"]]
    assert len(main) == 2
    assert len(payload["main_corridor_chain"]) == 2
