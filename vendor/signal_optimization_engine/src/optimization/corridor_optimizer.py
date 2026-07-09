"""Arterial/corridor coordination optimization entry."""

from __future__ import annotations

from typing import Any

from optimization.solvers.corridor_coordination import (
    generate_corridor_coordination_plan,
)
from preprocessing.requests import prepare_corridor_request


def optimize_corridor(request: dict[str, Any]) -> dict[str, Any]:
    """Generate a deterministic corridor coordination plan."""
    prepared = prepare_corridor_request(request)
    return generate_corridor_coordination_plan(prepared)
