"""Timing profile narrative: duration-only for presentation step."""

from intersection_agent.services.timing_profile_service import TimingProfileService


def test_mock_profile_narrative_is_duration_only():
    profile = TimingProfileService._mock_profile({"signal_plan": {"cycle_length": 130}})
    narrative = profile["narrative"]
    assert "130" in narrative
    assert "不匹配" not in narrative
    assert "最小绿" not in narrative
    assert profile["deficit_turns"]
