from app.trace.act_map_enrichment import (
    build_cause_spatial_map,
    build_diagnosis_compare_map,
    build_plan_preview_map,
    enrich_map_scenes,
)


def test_diagnosis_compare_resolves_downstream_coords():
    ticket = {"inter_id": "T1", "intersection_name": "A与B路口", "lng": 117.1, "lat": 36.6, "direction": "东"}
    diagnosis = {
        "metrics": {"queue_ratio": 0.8, "saturation": 0.9},
        "downstream_diagnosis": {
            "primary_downstream": {
                "inter_id": "D1",
                "inter_name": "下游路口",
                "metrics": {"saturation": 0.7},
            }
        },
        "downstream_trace": {
            "adjacent_intersections": [
                {"inter_id": "D1", "inter_name": "下游路口", "lng": 117.11, "lat": 36.61}
            ]
        },
    }
    result = build_diagnosis_compare_map(ticket, diagnosis)
    assert result["available"] is True
    assert result["target"]["lng"] == 117.1
    assert result["downstream"]["lng"] == 117.11


def test_cause_spatial_includes_annotations():
    ticket = {"lng": 117.1, "lat": 36.6, "direction": "东", "movement": "直行"}
    cause = {
        "cause_analysis": {"primary_cause": "下游承接不足"},
        "case_cards": {"cards": [{"case_id": "A", "title": "案例"}]},
    }
    diagnosis = {
        "downstream_diagnosis": {
            "primary_downstream": {"inter_id": "D1", "inter_name": "下游"},
        },
        "downstream_trace": {
            "adjacent_intersections": [{"inter_id": "D1", "lng": 117.11, "lat": 36.61}]
        },
    }
    result = build_cause_spatial_map(ticket, cause, diagnosis)
    assert result["available"] is True
    kinds = {a["kind"] for a in result["annotations"]}
    assert "approach" in kinds
    assert "downstream" in kinds
    assert "case_ref" in kinds


def test_plan_preview_from_recommended():
    ticket = {"lng": 117.1, "lat": 36.6}
    plan = {
        "recommended": {
            "plan_id": "incremental_release",
            "name": "小步释放",
            "timing": {
                "cycle_delta_s": -5,
                "phase_stage_timing_list": [
                    {"phase_stage_name": "东西直行", "green_delta_s": 3},
                ],
            },
        }
    }
    result = build_plan_preview_map(ticket, plan)
    assert result["available"] is True
    assert result["phase_changes"][0]["green_delta_s"] == 3


def test_enrich_map_scenes_writes_to_diagnosis():
    phases = {
        "diagnosis": {
            "map_scenes": {},
            "metrics": {"queue_ratio": 0.5},
            "downstream_diagnosis": {"primary_downstream": {"inter_name": "下游"}},
        }
    }
    ticket = {"lng": 117.1, "lat": 36.6}
    enrich_map_scenes(ticket=ticket, phases=phases, plan_block=None)
    assert "diagnosis_compare" in phases["diagnosis"]["map_scenes"]
