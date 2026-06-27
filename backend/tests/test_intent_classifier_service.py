"""Intent classifier service tests."""

import pytest

from intersection_agent.models.domain import Session
from intersection_agent.services.intent_classifier_service import IntentClassifierService


@pytest.mark.asyncio
async def test_llm_classifies_corridor_scan():
    svc = IntentClassifierService()
    intent = await svc.route_intent("奥体西晚高峰经常拥堵的路口有哪些", Session())
    assert intent == "corridor_scan"


@pytest.mark.asyncio
async def test_llm_classifies_single_intersection():
    svc = IntentClassifierService()
    q = "奥体西路与经十路路口晚高峰东进口拥堵"
    intent = await svc.route_intent(q, Session())
    assert intent == "intersection_diagnosis"


@pytest.mark.asyncio
async def test_llm_fallback_on_invalid_output():
    class BadLlm:
        async def chat_json(self, *, system: str, user: str, **kwargs: object):
            return {"intent": "unknown", "confidence": "high"}

    svc = IntentClassifierService(llm=BadLlm())
    intent = await svc.route_intent("奥体西最拥堵的路口是哪个", Session())
    assert intent == "corridor_scan"


@pytest.mark.asyncio
async def test_session_state_overrides_llm():
    class AlwaysDiagnosisLlm:
        async def chat_json(self, *, system: str, user: str, **kwargs: object):
            return {
                "intent": "intersection_diagnosis",
                "confidence": "high",
            }

    session = Session()
    session.state = session.state.CORRIDOR_NLU_INCOMPLETE
    svc = IntentClassifierService(llm=AlwaysDiagnosisLlm())
    assert await svc.route_intent("任意内容", session) == "corridor_scan"
