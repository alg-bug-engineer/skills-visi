"""Tests for speakable text helpers."""

from intersection_agent.utils.speakable import speak_decimal, to_speakable, truncate_speakable


def test_speak_decimal_ratio():
    assert speak_decimal(0.85) == "零点八五"


def test_speak_decimal_percent():
    assert speak_decimal(0.85, as_percent=True) == "百分之85"


def test_to_speakable_strips_markers():
    assert to_speakable("> 失衡系数 0.42") == "失衡系数0.42"


def test_truncate_speakable():
    long_text = "测" * 300
    out = truncate_speakable(long_text, limit=50)
    assert len(out) <= 50
    assert out.endswith("…")
