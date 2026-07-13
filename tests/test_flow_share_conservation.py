"""需求 34：流量占比守恒，越界不得进入叙事。"""

from app.data.pg_adapters import _coverage_index
from app.trace.flow_trace import build_flow_trace


def test_coverage_index_does_not_sum_across_turns():
    rows = [
        {"f_dir8_no": 0, "turn_dir_no": 1, "trace_type": "DOWNSTREAM", "cor_inter_id": "U1", "flow_share_ratio": 80},
        {"f_dir8_no": 0, "turn_dir_no": 2, "trace_type": "DOWNSTREAM", "cor_inter_id": "U1", "flow_share_ratio": 70},
    ]
    # 目标北左：只取 turn=1
    cov = _coverage_index(rows, dir8_code=0, turn_dir_no=1)
    assert cov[("DOWNSTREAM", "U1")] == 80


def test_coverage_index_drops_out_of_range_shares():
    rows = [
        {"f_dir8_no": 0, "turn_dir_no": 2, "trace_type": "DOWNSTREAM", "cor_inter_id": "U1", "flow_share_ratio": 286.39},
    ]
    cov = _coverage_index(rows, dir8_code=0, turn_dir_no=2)
    assert cov == {}


def test_flow_trace_marks_unavailable_when_all_shares_out_of_range():
    topology = {
        "upstream_nodes": [
            {
                "upstream_inter_id": "U1",
                "upstream_inter_name": "上游",
                "upstream_movements": [
                    {"turn": "直行", "share_pct": 286.39, "vehicles_of_100": 286, "raw_coverage": 286.39}
                ],
            }
        ]
    }
    out = build_flow_trace(topology=topology, dir8_code=0, turn_dir_no=2)
    assert out["available"] is False
    assert out["reason"] == "flow_share_out_of_range"
