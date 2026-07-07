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
