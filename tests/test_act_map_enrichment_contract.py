from app.api.response_builder import build_public_run_response, build_public_snapshot
from app.trace.act_map_enrichment import enrich_intent_spatial_scene, enrich_map_scenes


def _payload():
    ticket = {
        "inter_id": "target",
        "intersection_name": "目标路口",
        "lng": 117.1,
        "lat": 36.6,
        "direction": "北向南",
        "movement": "直行",
    }
    phases = {
        "diagnosis": {
            "metrics": {
                "dir8_code": 0,
                "target_movement_key": "d0_t2",
                "queue_length_m": 108,
                "storage_length_m": 111,
                "queue_ratio": 0.97,
            },
            "map_scenes": {
                "channelization_map": {
                    "available": True,
                    "links": [{
                        "link_id": "north-in",
                        "link_role": "entrance",
                        "dir8_code": "0",
                        "path": [[117.1, 36.61], [117.1, 36.6]],
                    }, {
                        "link_id": "east-in", "link_role": "entrance", "dir8_code": "2",
                        "path": [[117.11, 36.6], [117.1, 36.6]],
                    }, {
                        "link_id": "west-in", "link_role": "entrance", "dir8_code": "6",
                        "path": [[117.09, 36.6], [117.1, 36.6]],
                    }],
                },
                "flow_trace_segment_coverage_map": {
                    "available": True,
                    "center": [117.1, 36.6],
                    "trace_direction": "upstream",
                    "source": "postgresql_and_trip_trace",
                    "target": {
                        "id": "target",
                        "name": "目标路口",
                        "lng": 117.1,
                        "lat": 36.6,
                    },
                    "links": [{
                        "id": "north-in",
                        "rank": 1,
                        "coords": [[117.1, 36.6], [117.1, 36.61]],
                        "ratio": 1.0,
                    }],
                },
            },
        },
        "cause": {"cause_analysis": {"primary_cause": "放行效率异常"}},
    }
    plan = {
        "recommended": {
            "plan_id": "trial",
            "action_package": {"layers": {"proposed_timing": [
                {"action": "目标相位绿灯 +5s", "green_delta_s": 5},
                {"action": "非目标相位绿灯 -5s", "green_delta_s": -5},
            ]}},
            "timing": {"phase_stage_timing_list": [
                {"phase_stage_id": "1", "green_delta_s": -5, "movements": [
                    {"movement_key": "d2_t2", "dir8No": 2},
                    {"movement_key": "d6_t2", "dir8No": 6},
                ]},
                {"phase_stage_id": "3", "green_delta_s": 5, "movements": [
                    {"movement_key": "d0_t2", "dir8No": 0},
                ]},
            ]},
        },
        "trial_loop": {"cycle_delta_s": 0, "target_label": "北向南直行"},
    }
    return ticket, phases, plan


def test_enrichment_emits_real_queue_path_and_final_plan_map_scene():
    ticket, phases, plan = _payload()
    enrich_map_scenes(ticket=ticket, phases=phases, plan_block=plan)

    queue = phases["diagnosis"]["map_scenes"]["queue_evidence"]
    assert queue["available"] is True
    assert queue["path"] == [[117.1, 36.61], [117.1, 36.6]]
    assert queue["source"] == "postgresql"
    assert queue["stop_line"]["available"] is False

    scene = plan["map_scene"]
    assert scene["cycle_delta_s"] == 0
    assert scene["phase_changes"][0]["link_id"] == "north-in"
    assert scene["phase_changes"][0]["mapping_status"] == "phase_resolved"
    assert scene["phase_changes"][1]["mapping_status"] == "phase_resolved"
    assert scene["phase_changes"][1]["link_ids"] == ["east-in", "west-in"]


def test_unavailable_scenes_are_still_emitted_with_missing_fields():
    ticket, phases, plan = _payload()
    phases["diagnosis"]["map_scenes"]["channelization_map"]["links"] = []
    enrich_map_scenes(ticket=ticket, phases=phases, plan_block=plan)
    queue = phases["diagnosis"]["map_scenes"]["queue_evidence"]
    assert queue["available"] is False
    assert "path" in queue["missing_fields"]


def test_intent_spatial_scene_is_enriched_from_real_topology_paths():
    ticket, _, _ = _payload()
    intent = {"spatial_scene": {"available": True, "recognition_steps": [
        {"step": "topology", "status": "pending", "label": "上下游拓扑识别完成"},
        {"step": "arterial_path", "status": "pending", "label": "干线路径识别完成"},
    ]}}
    topology = {
        "geometry_source": "dim_link_info.geom",
        "upstream_nodes": [{
            "upstream_inter_id": "up",
            "upstream_inter_name": "上游路口",
            "upstream_lng": 117.1,
            "upstream_lat": 36.61,
            "link_id": "north-in",
            "path": [[117.1, 36.61], [117.1, 36.6]],
        }],
        "downstream_nodes": [{
            "inter_id": "down",
            "inter_name": "下游路口",
            "lng": 117.1,
            "lat": 36.59,
            "link_id": "south-out",
            "path": [[117.1, 36.6], [117.1, 36.59]],
        }],
    }

    enrich_intent_spatial_scene(intent=intent, ticket=ticket, topology=topology)
    scene = intent["spatial_scene"]
    assert scene["target_approach_path"] == [[117.1, 36.61], [117.1, 36.6]]
    assert scene["movement_path"] == [[117.1, 36.61], [117.1, 36.6], [117.1, 36.59]]
    assert scene["highlight_path"] == scene["movement_path"]
    assert scene["missing_fields"] == []
    assert scene["data_lineage"]["link_ids"] == ["north-in", "south-out"]
    assert all(step["status"] == "done" for step in scene["recognition_steps"])


def test_public_json_and_sse_snapshot_share_frontend_map_contract():
    ticket, phases, plan = _payload()
    phases["diagnosis"].update({
        "data_source": "pg",
        "topology": {
            "geometry_source": "dim_link_info.geom",
            "upstream_nodes": [{
                "upstream_inter_id": "up", "upstream_inter_name": "上游路口",
                "upstream_lng": 117.1, "upstream_lat": 36.61,
                "link_id": "north-in", "path": [[117.1, 36.61], [117.1, 36.6]],
            }],
            "downstream_nodes": [{
                "inter_id": "down", "inter_name": "下游路口",
                "lng": 117.1, "lat": 36.59,
                "link_id": "south-out", "path": [[117.1, 36.6], [117.1, 36.59]],
            }],
        },
        "flow_trace": {"entry_traces": [{
            "upstream_inter_id": "up", "upstream_inter_name": "上游路口",
            "upstream_lng": 117.1, "upstream_lat": 36.61,
            "path": [[117.1, 36.61], [117.1, 36.6]],
        }]},
        "downstream_trace": {
            "adjacent_intersections": [{
                "inter_id": "down", "inter_name": "下游路口",
                "lng": 117.1, "lat": 36.59, "capacity": {"blocked": False},
            }],
            "turn_traces": [{
                "downstream_inter_id": "down", "downstream_inter_name": "下游路口",
                "path": [[117.1, 36.6], [117.1, 36.59]],
            }],
        },
    })
    phases["strategy"] = {"control_scope_map": {"available": True}}
    artifacts = {
        "intent_understanding": {
            "diagnosis_ticket": ticket,
            "spatial_scene": {"available": True, "recognition_steps": []},
        },
        "data_analysis_diagnosis": phases["diagnosis"],
        "cause_analysis": phases["cause"],
        "strategy_generation": phases["strategy"],
        "plan_generation": plan,
    }
    raw = {
        "trace_id": "contract",
        "diagnosis_ticket": ticket,
        "artifacts": artifacts,
        "results": [],
    }

    public = build_public_run_response(raw)
    snapshot = build_public_snapshot(trace_id="contract", artifacts=artifacts, results=[])
    for payload in (public, snapshot):
        spatial = payload["phases"]["intent"]["spatial_scene"]
        assert spatial["movement_path"][-1] == [117.1, 36.59]
        trace_visual = payload["phases"]["diagnosis"]["map_scenes"]["flow_trace_segment_coverage_map"]["visualization"]
        assert trace_visual["effect"] == "upstream_spread"
        assert trace_visual["contract_version"] == "trace-spread/v3"
        assert trace_visual["particle_anchor"] == "path"
        assert trace_visual["particle_count"] == 0
        assert trace_visual["particle_texture"] is None
        assert trace_visual["particle_color_mode"] == "uniform"
        assert trace_visual["propagation_renderer"] == "path_prefix"
        assert trace_visual["repeat"] is False
        assert trace_visual["color_semantics"] == "uniform_flow_trace"
        assert trace_visual["road_classification_source"] == (
            "links[].fc|road6.dim_rid_trace_info.fc"
        )
        assert trace_visual["context_geometry_source"] is None
        assert trace_visual["render_geometry_scope"] == "links[].coords"
        assert trace_visual["palette"] == {"trace": "#39dfff"}
        assert trace_visual["camera"] == {
            "pitch": 48, "radius_m": 2000, "max_zoom": 13.8,
        }
        assert payload["phases"]["diagnosis"]["map_scenes"]["queue_evidence"]["available"] is True
        control = payload["phases"]["strategy"]["control_scope_map"]
        assert len(control["coordination_paths"]) == 2
        assert control["risk_boundary"]["geometry"] == {
            "available": False,
            "reason": "PostgreSQL 路网与指标表无策略风险边界 polygon 真源",
            "missing_fields": ["polygon"],
            "source": "none",
        }
        assert payload["plan"]["map_scene"]["available"] is True
