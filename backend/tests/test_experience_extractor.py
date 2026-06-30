import pytest

from intersection_agent.services.experience_extractor import ExperienceExtractor


@pytest.mark.asyncio
async def test_extractor_normalizes_qualitative():
    out = await ExperienceExtractor().to_structured("这地方绿灯应该再多给点")
    assert out["dimension"] in {"control", "signal_timing"}
    assert out["polarity"] == "increase_green"
    assert out["raw"] == "这地方绿灯应该再多给点"


@pytest.mark.asyncio
async def test_extractor_decrease_green():
    out = await ExperienceExtractor().to_structured("这个方向绿灯太长了，缩短一点")
    assert out["polarity"] == "decrease_green"
