"""上游路口 feed_segments 路径与解析。"""
import math

import pytest

from intersection_agent.services.upstream_topology_service import (
    UpstreamTopologyService,
    feed_segment_id,
    orient_path_outer_to_center,
    truncate_path_from_outer,
)


def test_orient_path_outer_to_center():
    center = (117.0, 36.0)
    path = [[117.0, 36.0], [117.001, 36.0]]
    out = orient_path_outer_to_center(path, center[0], center[1])
    assert out[0][0] == pytest.approx(117.001, abs=1e-6)


def test_truncate_path_from_outer():
    path = [[0.0, 0.0], [0.001, 0.0], [0.002, 0.0]]
    out = truncate_path_from_outer(path, max_len_m=50.0)
    assert len(out) >= 2
    assert out[0] == path[0]


def test_feed_segment_id_format():
    assert feed_segment_id("U1", 6, 2) == "feed:U1:6:2"


@pytest.mark.asyncio
async def test_resolve_feed_segments_mock_db():
    topo = UpstreamTopologyService()
    topo._settings.mock_db = True
    turn_split = [
        {"cor_dir8": 6, "cor_turn": 2, "feed_direction": "西直行", "share_pct": 93.3},
        {"cor_dir8": 4, "cor_turn": 3, "feed_direction": "南右转", "share_pct": 6.7},
    ]
    segs = await topo.resolve_feed_segments("mock_inter", turn_split, node_id="hop1")
    assert len(segs) == 2
    assert segs[0]["share_pct"] == 93.3
    assert all(len(s["path"]) >= 3 for s in segs)
    assert segs[0]["id"] == feed_segment_id("hop1", 6, 2)
    assert segs[0].get("from_inter_id")


@pytest.mark.asyncio
async def test_resolve_feed_segments_full_link_real_db():
    from intersection_agent.config import get_settings

    if get_settings().mock_db:
        pytest.skip("requires real DB")
    topo = UpstreamTopologyService()
    up = "011wwe289qc00001"
    from intersection_agent.services.flow_trace_service import (
        FlowTraceService,
        turn_split_for_upstream,
        period_type_from_label,
        day_labels_for_filter,
    )

    ft = FlowTraceService()
    rows = await ft._fetch_upstream(
        "011wwe28ctu00001", period_type_from_label("晚高峰"), day_labels_for_filter((1, 2, 3, 4, 5))
    )
    split = turn_split_for_upstream(rows, 6, up)
    segs = await topo.resolve_feed_segments(up, split, node_id=up)
    west = next(s for s in segs if s["cor_dir8"] == 6)
    assert len(west["path"]) >= 5
    assert (west.get("len_m") or 0) > 200
    assert west.get("from_inter_name")
