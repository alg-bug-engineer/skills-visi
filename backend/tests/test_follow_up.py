"""Follow-up generation tests."""

import pytest

from intersection_agent.services.nlu_service import NluService


@pytest.mark.asyncio
async def test_greeting_gets_natural_follow_up():
    service = NluService()
    result = await service.extract("你好")
    assert result["status"] == "incomplete"
    assert result["follow_up_field"] == "intersection"
    assert "路口" in result["follow_up"]
    assert result["follow_up"] != "您描述的是哪个路口？（如：奥体西路与经十路交叉口）"


@pytest.mark.asyncio
async def test_incomplete_uses_llm_follow_up():
    service = NluService()
    result = await service.extract("缺少时段：奥体西路与经十路交叉口经常拥堵")
    assert result["status"] == "incomplete"
    assert result["follow_up_field"] == "time_period"
    assert len(result["follow_up"]) > 5
