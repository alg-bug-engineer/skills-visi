"""ExperienceClassifier 三类经验归一测试。"""

import pytest

from intersection_agent.services.experience_classifier import ExperienceClassifier


class _StubLLM:
    def __init__(self, payload):
        self._payload = payload

    async def chat_json(self, *, system: str, user: str, **kwargs: object):
        return self._payload


@pytest.mark.asyncio
async def test_splits_problem_cause_measure():
    llm = _StubLLM(
        {
            "problem": "晚高峰南北向持续拥堵",
            "causes": ["附近学校放学"],
            "measures": ["对向不能溢出", "绿灯加30秒"],
        }
    )
    out = await ExperienceClassifier(llm=llm).classify(
        "奥体西路与经十路下午晚高峰南北向常堵，附近学校放学，建议对向别溢出，绿灯加30秒"
    )
    assert out["problem"] == "晚高峰南北向持续拥堵"
    assert out["causes"] == ["附近学校放学"]
    assert out["measures"] == ["对向不能溢出", "绿灯加30秒"]


@pytest.mark.asyncio
async def test_empty_text_returns_empty():
    out = await ExperienceClassifier(llm=_StubLLM({})).classify("   ")
    assert out == {"problem": None, "causes": [], "measures": []}


@pytest.mark.asyncio
async def test_llm_failure_degrades_gracefully():
    class _BoomLLM:
        async def chat_json(self, *, system: str, user: str, **kwargs: object):
            raise RuntimeError("llm down")

    out = await ExperienceClassifier(llm=_BoomLLM()).classify("某路口堵")
    assert out == {"problem": None, "causes": [], "measures": []}


@pytest.mark.asyncio
async def test_cleans_non_string_and_dedups():
    llm = _StubLLM(
        {"problem": "  ", "causes": ["学校", "学校", 42, ""], "measures": None}
    )
    out = await ExperienceClassifier(llm=llm).classify("文本")
    assert out["problem"] is None
    assert out["causes"] == ["学校"]
    assert out["measures"] == []
