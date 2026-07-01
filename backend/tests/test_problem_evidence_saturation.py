"""Problem evidence saturation must follow granularity.by_turn, not stale traffic_flow."""

from intersection_agent.services.problem_evidence_service import ProblemEvidenceService


def test_aggregate_metrics_prefers_by_turn_over_stale_traffic():
    """[RT-DIA-16] problem evidence saturation aligns with granularity.by_turn."""
    svc = ProblemEvidenceService()
    metrics = svc._aggregate_metrics(
        daily_rows=[],
        direction_rows=[],
        saturation_row={"saturation_max": 1.15, "saturation_avg": 0.84},
        data_payload={
            "traffic_flow": {
                "saturation_rate": 1.146,
                "turn_saturation_max": 1.146,
            },
            "evaluation": {"delay_index": 0.84, "saturation_avg": 0.84},
            "granularity": {
                "by_turn": [
                    {"label": "北直行", "turn_saturation": 0.73},
                    {"label": "东左转", "turn_saturation": 0.38},
                ],
            },
        },
    )
    assert metrics["saturation_rate"] == 0.73
