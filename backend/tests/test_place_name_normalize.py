"""Place name normalization tests."""

from intersection_agent.utils.place_name_normalize import (
    extract_intersection_phrases,
    normalize_place_names,
)


def test_luo_character_correction():
    assert normalize_place_names("奥体中路与新泩大街路口") == "奥体中路与新泺大街路口"


def test_extract_from_raw_context():
    text = "奥体中路与新泺大街路口，每周三晚高峰东向拥堵"
    phrases = extract_intersection_phrases(text)
    assert "奥体中路与新泺大街路口" in phrases
    assert "新泺大街与奥体中路路口" in phrases
