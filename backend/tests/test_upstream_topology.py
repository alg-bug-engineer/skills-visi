"""拓扑一跳溯源：方位、path 方向、correlate 白名单。"""
import pytest

from intersection_agent.services.upstream_topology_service import (
    UpstreamTopologyService,
    _filter_correlate_rows,
    orient_path_upstream_to_target,
    parse_linestring_wkt,
)


def test_parse_linestring_wkt():
    pts = parse_linestring_wkt("LINESTRING(117.1 36.6, 117.2 36.7, 117.3 36.8)")
    assert len(pts) == 3
    assert pts[0] == [117.1, 36.6]


def test_orient_path_upstream_to_target():
    path = [[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]]
    out = orient_path_upstream_to_target(path, 0.0, 0.0, 2.0, 2.0)
    assert out[0] == [0.0, 0.0]
    assert out[-1] == [2.0, 2.0]


def test_filter_correlate_whitelist():
    rows = [
        {"f_dir8_no": 6, "turn_dir_no": 1, "cor_inter_id": "A", "flow_share_ratio": 90},
        {"f_dir8_no": 6, "turn_dir_no": 1, "cor_inter_id": "B", "flow_share_ratio": 60},
    ]
    out = _filter_correlate_rows(rows, dir8=6, turn=1, allowed_ids={"B"})
    assert len(out) == 1
    assert out[0]["cor_inter_id"] == "B"


@pytest.mark.asyncio
async def test_mock_pick_west_hop_has_path():
    from unittest.mock import MagicMock

    settings = MagicMock()
    settings.mock_db = True
    settings.pgschema = "road6"
    settings.pg_flow_schema = "xianchang"
    settings.pg_version_id = "20260501"
    svc = UpstreamTopologyService(settings=settings)
    hop = await svc.pick_upstream_hop("mock_target", 6, turn=1)
    assert hop is not None
    assert hop["cor_inter_name"] == "经十路与转山西路路口"
    assert len(hop["path"]) >= 3
    assert hop["path_source"] == "link_geom"
