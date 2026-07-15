"""试运行红线必须与真实现状配时同口径。"""

from pathlib import Path
import importlib.util


def _load():
    path = Path("skills/strategy-generation/scripts/build_strategy_profile.py")
    spec = importlib.util.spec_from_file_location("build_strategy_profile", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_trial_constraints_do_not_claim_current_224s_cycle_must_be_below_180s():
    mod = _load()
    profile = mod.build_strategy_profile(
        cause={},
        diagnosis={
            "overflow_mechanism": {"primary": "discharge_anomaly"},
            "downstream_state": {"direct_downstream_inter_name": "永绥路与齐音路路口"},
        },
        llm_strategy={
            "hard_constraints": [
                "单相位绿灯不得超过 60s",
                "信号周期不得超过 180s",
            ]
        },
        signal={
            "current_cycle_s": 224,
            "phase_stage_timing_list": [
                {"minGreenTime": 7, "maxGreenTime": 116},
            ],
        },
        constraints={"max_cycle_s": 180},
    )

    hard = profile["strategy"]["hard_constraints"]
    blob = "｜".join(hard)
    assert "信号周期保持现状" in blob
    assert "现状高于配置上限 180s" in blob
    assert "单相位绿灯不得超过 116s" in blob
    assert "单相位绿灯不得超过 60s" not in blob
    assert "信号周期不得超过 180s" not in blob
