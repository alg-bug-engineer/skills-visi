"""方案生成生产级证据契约测试。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load(rel: str):
    path = PROJECT_ROOT / rel
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _signal_with_evidence() -> dict:
    return {
        "inter_id": "demo_inter",
        "current_cycle_s": 130,
        "phase_stage_timing_list": [
            {
                "phase_stage_id": "1",
                "phase_stage_name": "西直、东直",
                "greenTime": 60,
                "yellowTime": 3,
                "allRedTime": 2,
                "minGreenTime": 36,
                "maxGreenTime": 78,
                "phaseDirInfoDTOList": [
                    {
                        "movementKey": "d6_t2",
                        "label": "西直",
                        "dir8No": 6,
                        "turnDirNo": 2,
                        "turnFlowTotal": 1200,
                        "laneCount": 2,
                        "saturation": 0.75,
                        "flow_available": True,
                        "source": "pg_turn_flow",
                    },
                    {
                        "movementKey": "d2_t2",
                        "label": "东直",
                        "dir8No": 2,
                        "turnDirNo": 2,
                        "turnFlowTotal": 1300,
                        "laneCount": 2,
                        "saturation": 0.8746,
                        "flow_available": True,
                        "source": "pg_turn_flow",
                    },
                ],
            }
        ],
    }


def _optimizer_request() -> dict:
    return {
        "phasePlanOfTimeList": [
            {
                "phaseStageInfoList": [
                    {
                        "phaseStageId": "1",
                        "phaseStageName": "西直、东直",
                        "currentTiming": {
                            "greenSec": 60,
                            "yellowSec": 3,
                            "allRedSec": 2,
                            "stageTotalSec": 65,
                        },
                        "greenBounds": {"minGreenS": 36, "maxGreenS": 78},
                        "phaseDirInfoDTOList": _signal_with_evidence()["phase_stage_timing_list"][0][
                            "phaseDirInfoDTOList"
                        ],
                    }
                ],
            }
        ]
    }


def test_build_timing_evidence_contains_current_optimized_movements_and_meta():
    mod = _load("skills/plan-generation/scripts/run_single_point_optimizer.py")
    build = getattr(mod, "_build_timing_evidence", None)
    assert callable(build), "_build_timing_evidence should build production plan evidence"

    timing = build(
        signal=_signal_with_evidence(),
        request=_optimizer_request(),
        cycle_s=98,
        timing_list=[
            {
                "phase_stage_id": "1",
                "phase_stage_name": "西直、东直",
                "green_time_s": 36,
                "yellow_time_s": 3,
                "all_red_time_s": 2,
                "min_green_time_s": 36,
                "max_green_time_s": 78,
                "split_ratio": 0.3673,
                "phase_saturation": 0.8746,
            }
        ],
        meta={
            "solver": "scipy_slsqp_document_model",
            "target_saturation": 0.75,
            "max_phase_saturation": 0.8746,
            "total_turn_flow_vph": 4078.0,
            "direction_intensity_list": [
                {
                    "movementKey": "d6_t2",
                    "label": "西-直行",
                    "dir8No": 6,
                    "turnDirNo": 2,
                    "intensity": 0.75,
                }
            ],
            "notes": ["使用文档 SQP 模型"],
        },
    )

    assert timing["available"] is True
    assert timing["current_cycle_s"] == 130
    assert timing["cycle_s"] == 98
    assert timing["cycle_delta_s"] == -32
    stage = timing["phase_stage_timing_list"][0]
    assert stage["current_timing"]["green_time_s"] == 60
    assert stage["optimized_timing"]["green_time_s"] == 36
    assert stage["optimized_timing"]["stage_total_s"] == 41
    assert stage["green_delta_s"] == -24
    assert stage["stage_delta_s"] == -24
    assert stage["movements"][0]["movement_key"] == "d6_t2"
    assert stage["movements"][0]["source"] == "pg_turn_flow"
    assert timing["meta"]["direction_intensity_list"]
    assert timing["meta"]["data_quality"]["current_timing_source"] == "pg_signal_plan"


def test_build_timing_evidence_marks_missing_fields_unavailable():
    mod = _load("skills/plan-generation/scripts/run_single_point_optimizer.py")
    build = getattr(mod, "_build_timing_evidence", None)
    assert callable(build), "_build_timing_evidence should build production plan evidence"

    timing = build(
        signal={"inter_id": "demo_inter"},
        request={"phasePlanOfTimeList": [{"phaseStageInfoList": [{"phaseStageId": "1"}]}]},
        cycle_s=98,
        timing_list=[{"phase_stage_id": "1", "green_time_s": 36, "yellow_time_s": 3, "all_red_time_s": 2}],
        meta={},
    )

    assert timing["available"] is False
    assert "timing.current_cycle_s" in timing["missing_fields"]
    assert "phase_stage_timing_list[1].current_timing" in timing["missing_fields"]
    assert "phase_stage_timing_list[1].movements" in timing["missing_fields"]
    assert "timing.meta.direction_intensity_list" in timing["missing_fields"]
