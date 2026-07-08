"""前端回放 fixture 采集脚本必须只写入真实生产证据。"""

from __future__ import annotations

import json

from scripts import capture_frontend_mock as capture


def _public_response_with_plan(timing: dict) -> dict:
    return {
        "completed": True,
        "plan": {
            "candidates": [
                {
                    "plan_id": "downstream_protection",
                    "timing": timing,
                }
            ]
        },
    }


def test_validate_public_evidence_accepts_complete_plan_timing():
    validate = getattr(capture, "_validate_public_evidence", None)
    assert callable(validate), "capture script should validate production plan evidence before writing"

    errors = validate(
        _public_response_with_plan(
            {
                "current_cycle_s": 130,
                "phase_stage_timing_list": [
                    {
                        "current_timing": {"green_time_s": 60},
                        "movements": [{"movement_key": "d6_t2"}],
                    }
                ],
                "meta": {
                    "direction_intensity_list": [{"movementKey": "d6_t2", "intensity": 0.75}],
                },
            }
        )
    )

    assert errors == []


def test_write_rejects_incomplete_plan_evidence(tmp_path):
    out = tmp_path / "run_1_fixture.json"
    incomplete = _public_response_with_plan(
        {
            "cycle_s": 98,
            "phase_stage_timing_list": [{"optimized_timing": {"green_time_s": 36}}],
            "meta": {},
        }
    )

    rc = capture._write_if_valid(incomplete, out)

    assert rc == 3
    assert not out.exists()


def test_write_accepts_complete_plan_evidence(tmp_path):
    out = tmp_path / "run_1_fixture.json"
    complete = _public_response_with_plan(
        {
            "current_cycle_s": 130,
            "phase_stage_timing_list": [
                {
                    "current_timing": {"green_time_s": 60},
                    "movements": [{"movement_key": "d6_t2"}],
                }
            ],
            "meta": {
                "direction_intensity_list": [{"movementKey": "d6_t2", "intensity": 0.75}],
            },
        }
    )

    rc = capture._write_if_valid(complete, out)

    assert rc == 0
    assert json.loads(out.read_text(encoding="utf-8"))["plan"]["candidates"][0]["timing"]["current_cycle_s"] == 130
