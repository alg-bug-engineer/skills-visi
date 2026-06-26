"""Tests for intersection cognition service."""

from __future__ import annotations

import pytest

from intersection_agent.models.domain import NluResult, TimePeriod
from intersection_agent.services.intersection_cognition_service import IntersectionCognitionService


@pytest.mark.asyncio
async def test_mock_cognition_has_arms_and_directions():
    svc = IntersectionCognitionService()
    nlu = NluResult(
        intersection="奥体西路与经十路交叉口",
        time_period=TimePeriod(start="16:00", end="18:00", label="晚高峰"),
    )
    # force mock via settings - use mock_db from conftest if available
    from intersection_agent.config import get_settings

    settings = get_settings()
    if not settings.mock_db:
        pytest.skip("requires MOCK_DB=1")
    svc._settings = settings  # noqa: SLF001

    payload = await svc.fetch("mock_inter_001", "奥体西路与经十路交叉口", nlu)
    assert payload["intersection"]["arm_count"] >= 4
    assert len(payload["arms"]) >= 4
    assert "东西向" in payload["available_directions"]
    assert payload["direction_groups"]
