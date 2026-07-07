"""Fixture 维护脚本：仅用于 `tests/generate_fixtures.py` 刷新 overflow 样例。

生产路径禁止引用；请使用 PG、`task` 注入，或 `tests/fixtures/overflow_topology.json`。
"""

from __future__ import annotations

from typing import Any

from app.trace.topology import resolve_dir8_turn


def build_demo_topology(ticket: dict[str, Any]) -> dict[str, Any]:
    direction = ticket.get("direction", "东向西")
    movement = ticket.get("movement", "直行")
    dir8_code, turn_dir_no = resolve_dir8_turn(direction, movement)

    return {
        "target_inter_id": "demo_wenhua_shunhua",
        "target_inter_name": ticket.get("intersection_name", "文化西路与舜华路交叉口"),
        "target_lng": 117.1208,
        "target_lat": 36.6652,
        "dir8_code": dir8_code,
        "turn_dir_no": turn_dir_no,
        "period_type": "EVENING_PEAK",
        "day_basis": "工作日",
        "upstream_arrival_flow_vph": 1820,
        "upstream_release_intensity_vph": 1760,
        "upstream_arrival_intensity": "high",
        "phase_offset_match": "partial",
        "caveat": "演示数据：未接 PG，拓扑与 correlate 占比为剧本样例",
        "downstream_nodes": [
            {
                "inter_id": "demo_shunhua_gongye",
                "inter_name": "舜华路与工业南路交叉口",
                "role": "downstream",
                "lng": 117.1186,
                "lat": 36.6650,
                "receiving_dir8": 2,
                "receiving_label": "东进口",
                "share_pct": 78.5,
                "path": [[117.1208, 36.6652], [117.1196, 36.6651], [117.1186, 36.6650]],
                "path_source": "demo",
                "queue_length_m": 160.0,
                "storage_length_m": 180.0,
                "volume_vph": 1520.0,
                "capacity_vph": 1600.0,
                "green_utilization": 0.82,
                "stop_count": 2.1,
                "avg_delay_s": 72.0,
                "time_series_trend": "持续高位",
                "by_turn": [
                    {"label": "东进口直行", "turn_saturation": 0.95, "green_utilization": 0.82, "flow_vph": 1520},
                    {"label": "东进口左转", "turn_saturation": 0.58, "green_utilization": 0.55, "flow_vph": 420},
                ],
            }
        ],
        "upstream_nodes": [
            {
                "upstream_inter_id": "demo_wenhua_qilu",
                "upstream_inter_name": "文化东路与舜华路交叉口",
                "upstream_lng": 117.1235,
                "upstream_lat": 36.6654,
                "vehicles_base": 100,
                "path": [[117.1235, 36.6654], [117.1222, 36.6653], [117.1208, 36.6652]],
                "upstream_movements": [
                    {
                        "turn": "直行",
                        "cor_turn": 2,
                        "feed_direction": "东进口直行",
                        "share_pct": 62.0,
                        "vehicles_of_100": 62,
                        "raw_coverage": 74.0,
                    },
                    {
                        "turn": "左转",
                        "cor_turn": 1,
                        "feed_direction": "东进口左转",
                        "share_pct": 24.0,
                        "vehicles_of_100": 24,
                        "raw_coverage": 28.0,
                    },
                    {
                        "turn": "右转",
                        "cor_turn": 3,
                        "feed_direction": "东进口右转",
                        "share_pct": 14.0,
                        "vehicles_of_100": 14,
                        "raw_coverage": 16.0,
                    },
                ],
            }
        ],
    }
