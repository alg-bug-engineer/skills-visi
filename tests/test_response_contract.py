from app.api.response_builder import build_public_run_response


def test_public_plan_recommendation_exposed():
    payload = build_public_run_response(
        {
            "trace_id": "t1",
            "completed": True,
            "pipeline_complete": True,
            "diagnosis_ticket": {"intersection_name": "文化西路"},
            "artifacts": {
                "strategy_generation": {
                    "strategy": {
                        "recommended": ["上游控流 + 干线协调"],
                        "hard_constraints": ["最小绿灯不可突破"],
                        "trigger_exit_rules": {"rollback_condition": "下游排队上升"},
                    }
                },
                "plan_generation": {
                    "recommended": {"plan_id": "arterial_coordination"},
                    "recommendation": {
                        "recommended_plan_id": "arterial_coordination",
                        "rationale": "下游承接不足叠加上游冲击",
                    },
                },
            },
            "results": [],
        }
    )
    assert payload["plan"]["recommendation"]["rationale"] == "下游承接不足叠加上游冲击"
    assert payload["phases"]["strategy"]["strategy"]["recommended"]
    assert payload["phases"]["strategy"]["strategy"]["hard_constraints"]
    assert payload["pipeline_complete"] is True


def test_public_plan_preserves_timing_evidence_fields():
    payload = build_public_run_response(
        {
            "trace_id": "t2",
            "completed": True,
            "pipeline_complete": True,
            "diagnosis_ticket": {"intersection_name": "文化西路"},
            "artifacts": {
                "plan_generation": {
                    "candidates": [
                        {
                            "plan_id": "downstream_protection",
                            "timing": {
                                "available": True,
                                "current_cycle_s": 130,
                                "cycle_s": 98,
                                "cycle_delta_s": -32,
                                "phase_stage_timing_list": [
                                    {
                                        "phase_stage_id": "1",
                                        "current_timing": {"green_time_s": 60, "stage_total_s": 65},
                                        "optimized_timing": {"green_time_s": 36, "stage_total_s": 41},
                                        "movements": [{"movement_key": "d6_t2", "label": "西直"}],
                                    }
                                ],
                                "meta": {
                                    "direction_intensity_list": [{"movementKey": "d6_t2", "intensity": 0.75}],
                                    "data_quality": {"current_timing_source": "pg_signal_plan"},
                                },
                            },
                        }
                    ],
                    "recommended": {
                        "plan_id": "downstream_protection",
                        "timing": {
                            "current_cycle_s": 130,
                            "phase_stage_timing_list": [
                                {
                                    "current_timing": {"green_time_s": 60},
                                    "movements": [{"movement_key": "d6_t2"}],
                                }
                            ],
                            "meta": {
                                "direction_intensity_list": [{"movementKey": "d6_t2", "intensity": 0.75}],
                                "data_quality": {"movement_source": "pg_turn_flow+pg_turn_saturation"},
                            },
                        },
                    },
                },
            },
            "results": [],
        }
    )

    candidate = payload["plan"]["candidates"][0]
    assert candidate["timing"]["current_cycle_s"] == 130
    assert candidate["timing"]["cycle_delta_s"] == -32
    assert "current_timing" in candidate["timing"]["phase_stage_timing_list"][0]
    assert "optimized_timing" in candidate["timing"]["phase_stage_timing_list"][0]
    assert "movements" in candidate["timing"]["phase_stage_timing_list"][0]
    assert "direction_intensity_list" in candidate["timing"]["meta"]
    assert "data_quality" in candidate["timing"]["meta"]


def test_strategy_fields_from_profile():
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parent.parent
        / "skills"
        / "strategy-generation"
        / "scripts"
        / "build_strategy_profile.py"
    )
    spec = importlib.util.spec_from_file_location("build_strategy_profile", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    profile = module.build_strategy_profile(
        {"cause_scores": {"scores": {"coordination": 0.5}}},
        {"downstream_trace": {"governance": {"downstream_blocked": True}}},
        {
            "recommended": ["自定义推荐"],
            "hard_constraints": ["自定义约束"],
            "trigger_exit_rules": {"human_review": "异常时复核"},
        },
    )
    strategy = profile["strategy"]
    assert strategy["recommended"] == ["自定义推荐"]
    assert strategy["hard_constraints"] == ["自定义约束"]
    assert strategy["trigger_exit_rules"]["human_review"] == "异常时复核"
