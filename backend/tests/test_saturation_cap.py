"""Tests for saturation cap utility."""

from intersection_agent.utils.saturation_cap import cap_saturation


def test_cap_saturation_above_ceiling():
    assert cap_saturation(2.24) == 1.5


def test_cap_saturation_below_ceiling():
    assert cap_saturation(0.86) == 0.86


def test_cap_saturation_none():
    assert cap_saturation(None) is None
