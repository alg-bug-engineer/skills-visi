"""Tests for sustained window detection."""

from intersection_agent.utils.sustained_windows import find_sustained_windows


def test_find_sustained_windows_above():
    series = {i: 0.35 for i in range(204, 208)}
    windows = find_sustained_windows(series, 0.30, min_steps=3, above=True)
    assert len(windows) == 1
    assert windows[0]["duration_min"] == 20


def test_find_sustained_windows_below():
    series = {i: 0.45 for i in range(210, 214)}
    windows = find_sustained_windows(series, 0.60, min_steps=3, above=False)
    assert len(windows) == 1
