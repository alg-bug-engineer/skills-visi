import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    path = PROJECT_ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cause_scores_dimensions():
    score_mod = _load("score", "skills/cause-analysis/scripts/score_cause_dimensions.py")
    diagnosis = {
        "metrics": {
            "saturation": 0.92,
            "queue_ratio": 0.88,
            "green_utilization": 0.45,
        },
        "downstream_trace": {"governance": {"downstream_blocked": True}},
        "downstream_diagnosis": {"release_answer": "下游接不住"},
        "arterial_analysis": {"need_upstream_metering": True},
        "bottleneck_analysis": {"bottleneck_type": "downstream_capacity"},
        "downstream_metrics": {"queue_ratio": 0.9},
    }
    result = score_mod.score_cause_dimensions(diagnosis, task={})
    assert set(result["scores"].keys()) == set(score_mod.DIMENSIONS)
    assert result["primary_dimension"] in score_mod.DIMENSIONS
    assert result["scores"]["demand"] > 0
    assert result["scores"]["coordination"] > 0
    ranking = score_mod.build_cause_ranking_from_scores(result, diagnosis)
    assert ranking[0]["role"] == "主因"


def test_strategy_instruction_contract():
    profile_mod = _load("profile", "skills/strategy-generation/scripts/build_strategy_profile.py")
    cause = {
        "cause_scores": {
            "scores": {"event": 0.5, "coordination": 0.4},
            "primary_dimension": "event",
        },
        "arterial_coordination_needed": True,
    }
    diagnosis = {
        "downstream_trace": {"governance": {"downstream_blocked": True}},
        "arterial_analysis": {"need_upstream_metering": True},
        "bottleneck_analysis": {"bottleneck_type": "downstream_capacity"},
    }
    profile = profile_mod.build_strategy_profile(cause, diagnosis, {"principles": ["防溢流优先"]})
    instruction = profile["strategy_instruction"]
    assert instruction["target_saturation"] > 0
    assert instruction["rollback_condition"]
    assert profile["strategy_package"] in profile_mod.PACKAGE_DEFINITIONS
    assert sum(profile["package_scores"].values()) > 0
