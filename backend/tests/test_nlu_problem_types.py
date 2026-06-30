import pytest

from intersection_agent.services.nlu_service import NluService


@pytest.mark.asyncio
async def test_spillback_keyword_classified():
    svc = NluService()  # settings.mock_llm 生效
    res = await svc.extract("经十路口下午老是排队溢出到上游")
    assert "spillback" in res["data"].problem_types


@pytest.mark.asyncio
async def test_multi_type_congestion_and_spillback():
    svc = NluService()
    res = await svc.extract("这个路口又堵又溢出")
    assert {"congestion", "spillback"} <= set(res["data"].problem_types)


@pytest.mark.asyncio
async def test_default_congestion_when_no_keyword():
    svc = NluService()
    res = await svc.extract("奥体西路与经十路交叉口晚高峰南北向情况")
    assert res["data"].problem_types == ["congestion"]
