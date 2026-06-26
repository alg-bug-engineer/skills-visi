"""Intent detector tests."""

from intersection_agent.services.intent_detector import detect_confirmation_intent


def test_confirm_words():
    assert detect_confirmation_intent("是") == "confirm"
    assert detect_confirmation_intent("好的") == "confirm"
    assert detect_confirmation_intent("OK") == "confirm"


def test_deny_words():
    assert detect_confirmation_intent("否") == "deny"
    assert detect_confirmation_intent("不是") == "deny"
    assert detect_confirmation_intent("不需要") == "deny"


def test_ambiguous():
    assert detect_confirmation_intent("再看看") is None
