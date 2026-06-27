"""Intent router tests."""

from intersection_agent.models.domain import Session, SessionState
from intersection_agent.services.intent_router import looks_like_corridor_scan, route_intent


def test_corridor_scan_intent_top_one():
    assert looks_like_corridor_scan("奥体西最拥堵的路口是哪个")
    session = Session()
    assert route_intent("奥体西最拥堵的路口是哪个", session) == "corridor_scan"


def test_corridor_scan_inverted_plural():
    """「路口有哪些」与「哪些路口」均应识别为干线扫描。"""
    q = "奥体西晚高峰经常拥堵的路口有哪些"
    assert looks_like_corridor_scan(q)
    assert route_intent(q, Session()) == "corridor_scan"


def test_corridor_scan_which_intersections():
    assert looks_like_corridor_scan("奥体西路晚高峰哪些路口比较堵")
    assert looks_like_corridor_scan("经十路早高峰拥堵的路口有哪些")


def test_corridor_scan_where_congested():
    assert looks_like_corridor_scan("帮我看看奥体西晚高峰哪里堵")


def test_single_intersection_not_corridor_scan():
    q = "奥体西路与经十路路口晚高峰东进口拥堵"
    assert not looks_like_corridor_scan(q)
    assert route_intent(q, Session()) == "intersection_diagnosis"


def test_corridor_state_forces_scan():
    session = Session()
    session.state = SessionState.CORRIDOR_NLU_INCOMPLETE
    assert route_intent("随便一句", session) == "corridor_scan"
