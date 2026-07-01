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


@pytest.mark.asyncio
async def test_empty_green_natural_phrase():
    svc = NluService()
    res = await svc.extract(
        "会展路与奥体中路路口晚高峰17点到19点西进口绿灯经常没车也放行，东进口却排队很长"
    )
    assert "empty_green" in res["data"].problem_types
    assert "congestion" in res["data"].problem_types
