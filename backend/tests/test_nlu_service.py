"""NLU service tests."""

import pytest

from intersection_agent.services.nlu_service import NluService


@pytest.mark.asyncio
async def test_nlu_complete():
    service = NluService()
    result = await service.extract("奥体西路与经十路交叉口，下午四点南北向经常拥堵")
    assert result["status"] == "complete"
    assert result["data"].intersection is not None
    assert result["data"].problem_type == "congestion"
    assert result["data"].directions == ["南北向"]


@pytest.mark.asyncio
async def test_nlu_incomplete_missing_directions():
    service = NluService()
    result = await service.extract("奥体西路与经十路交叉口，下午四点经常拥堵")
    assert result["status"] == "incomplete"
    assert "directions" in result["missing"]
    assert result["follow_up_field"] == "directions"


@pytest.mark.asyncio
async def test_nlu_incomplete():
    service = NluService()
    result = await service.extract("缺少时段：奥体西路与经十路交叉口经常拥堵")
    assert result["status"] == "incomplete"
    assert "time_period" in result["missing"]
    assert result["follow_up_field"] == "time_period"


@pytest.mark.asyncio
async def test_nlu_extracts_user_constraint_slot():
    service = NluService()
    result = await service.extract(
        "奥体西路与经十路交叉口，下午四点南北向经常拥堵，优先保障南北向直行，绿灯可以延长"
    )
    assert result["status"] == "complete"
    assert result["data"].user_suggestion
    assert "南北向" in result["data"].user_suggestion


@pytest.mark.asyncio
async def test_nlu_extracts_vertical_overflow_constraint():
    service = NluService()
    result = await service.extract(
        "奥体西路与经十路交叉口，下午四点南北向经常拥堵，要考虑垂直方向不能溢出"
    )
    assert result["status"] == "complete"
    assert result["data"].user_suggestion == "要考虑垂直方向不能溢出"
