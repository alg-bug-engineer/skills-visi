"""NLU field normalization tests."""

from intersection_agent.services.nlu_service import NluService


def test_normalize_llm_aliases():
    service = NluService()
    raw = {
        "location": "奥体西路与经十路交叉口",
        "time_period": "晚高峰",
        "issue": "拥堵",
    }
    normalized = service._normalize_raw(raw)
    nlu = service._parse_raw(normalized)
    assert nlu.intersection == "奥体西路与经十路交叉口"
    assert nlu.problem_type == "congestion"
    assert nlu.time_period is not None
    assert nlu.time_period.label == "晚高峰"
