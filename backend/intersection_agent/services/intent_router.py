"""Route first-turn user intent: corridor scan vs single-intersection diagnosis."""

from __future__ import annotations

import re

from intersection_agent.models.domain import Session, SessionState
from intersection_agent.utils.place_name_normalize import extract_intersection_phrases

# Explicit corridor-scan signals (ranking, listing, whole-road scope)
_CORRIDOR_SCAN_PATTERNS = (
    r"哪些\s*路口",
    r"哪几个\s*路口",
    r"哪个\s*路口\s*最",
    r"路口\s*有哪些",
    r"路口\s*哪几个",
    r"路口\s*哪些",
    r"有哪些\s*.*路口",
    r"哪些\s*.*路口",
    r"哪些\s*.*节点",
    r"最堵",
    r"最拥堵",
    r"比较堵",
    r"较堵",
    r"经常堵",
    r"经常拥堵",
    r"拥堵排名",
    r"路口排名",
    r"整条",
    r"干线上",
    r"沿线",
    r"路上哪些",
    r"哪里堵",
    r"哪里拥堵",
    r"哪儿堵",
)

# Road / corridor name fragment (without requiring full 「X路与Y路」intersection)
_ROAD_FRAGMENT = re.compile(r"[\u4e00-\u9fff]{1,12}(?:路|街|大道|干线)|奥体西")

# Congestion intent on a road scope
_CONGESTION_ON_ROAD = re.compile(
    r"(堵|拥堵|饱和|排队|通行慢|压力大)",
)

# Plural / exploratory — user wants multiple intersections, not one named junction
_PLURAL_INTERSECTION = re.compile(
    r"(哪些|哪几个|有哪些|都有哪些|几个|哪些个).{0,12}(路口|节点|地方|位置)",
    re.DOTALL,
)
_PLURAL_INTERSECTION_INVERTED = re.compile(
    r"(路口|节点).{0,8}(有哪些|哪几个|哪些|都有哪些)",
    re.DOTALL,
)


def route_intent_by_state(session: Session) -> str | None:
    """Session-state overrides (not LLM)."""
    if session.state == SessionState.AWAITING_CORRIDOR_PICK:
        return "corridor_pick"
    if session.state == SessionState.CORRIDOR_NLU_INCOMPLETE:
        return "corridor_scan"
    return None


def route_intent_by_rules(text: str) -> str:
    """Regex fallback for first-turn corridor vs single-intersection."""
    if looks_like_corridor_scan(text):
        return "corridor_scan"
    return "intersection_diagnosis"


def route_intent(text: str, session: Session) -> str:
    """Sync route: state override + regex rules (used in unit tests / fallback)."""
    state_intent = route_intent_by_state(session)
    if state_intent:
        return state_intent
    return route_intent_by_rules(text)


def looks_like_corridor_scan(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False

    # Named junction like 「经十路与奥体西路路口」→ single-intersection unless explicit scan cues
    if extract_intersection_phrases(normalized):
        return False
    if "与" in normalized and re.search(
        r"[\u4e00-\u9fff]+(?:路|街|大道).{0,2}与.{0,2}[\u4e00-\u9fff]+(?:路|街|大道)",
        normalized,
    ):
        if not _has_explicit_scan_cue(normalized):
            return False

    if _has_explicit_scan_cue(normalized):
        return True

    # 「奥体西晚高峰经常拥堵的路口有哪些」— road + congestion + plural, no named junction
    has_road = bool(_ROAD_FRAGMENT.search(normalized))
    has_congestion = bool(_CONGESTION_ON_ROAD.search(normalized))
    has_plural = bool(
        _PLURAL_INTERSECTION.search(normalized)
        or _PLURAL_INTERSECTION_INVERTED.search(normalized)
    )
    if has_road and has_congestion and has_plural:
        return True

    # 「奥体西晚高峰哪里堵」— road + congestion + where-question
    if has_road and has_congestion and re.search(r"(哪里|哪儿|何处)", normalized):
        return True

    return False


def _has_explicit_scan_cue(text: str) -> bool:
    return any(re.search(p, text) for p in _CORRIDOR_SCAN_PATTERNS)
