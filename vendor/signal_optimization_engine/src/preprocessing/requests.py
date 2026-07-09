"""Normalize external payloads into optimizer request contracts."""

from __future__ import annotations

from typing import Any

from preprocessing.normalization import (
    merge_optional_mapping,
    normalize_corridor_intersection_ids,
)


def prepare_intersection_request(
    payload: dict[str, Any],
    *,
    constraints: dict[str, Any] | None = None,
    strategy_instruction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare one intersection request for the single-point optimizer."""
    request = dict(payload)
    merge_optional_mapping(request, "constraints", constraints)
    merge_optional_mapping(request, "strategy_instruction", strategy_instruction)
    return request


def prepare_corridor_request(
    payload: dict[str, Any],
    *,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare one arterial/corridor coordination request."""
    request = dict(payload)
    normalize_corridor_intersection_ids(request)
    merge_optional_mapping(request, "constraints", constraints)
    return request


def prepare_region_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Prepare a deterministic region-level orchestration request."""
    request = dict(payload)
    request.setdefault("region_id", request.get("id", "UNKNOWN"))
    request.setdefault("corridors", [])
    request.setdefault("intersections", [])
    return request
