"""Intersection-level signal timing optimization entry."""

from __future__ import annotations

from typing import Any

from optimization.solvers.single_intersection import (
    generate_single_point_plan,
)
from preprocessing.requests import prepare_intersection_request


def optimize_intersection(request: dict[str, Any]) -> dict[str, Any]:
    """Generate a deterministic single-intersection timing plan."""
    prepared = prepare_intersection_request(request)
    return generate_single_point_plan(prepared)
