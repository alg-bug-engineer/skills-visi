"""Small normalization helpers shared by request preprocessors."""

from __future__ import annotations

from typing import Any


def merge_optional_mapping(
    request: dict[str, Any],
    key: str,
    extra: dict[str, Any] | None,
) -> None:
    """Merge optional mapping values into a request section in place."""
    if not extra:
        return
    request[key] = {**request.get(key, {}), **extra}


def resolve_intersection_id(payload: dict[str, Any]) -> str:
    """Resolve a stable intersection identifier from common external field names."""
    value = payload.get("intersection_id") or payload.get("interId") or payload.get("id")
    return str(value) if value is not None else ""


def normalize_corridor_intersection_ids(request: dict[str, Any]) -> None:
    """Populate ``intersection_ids`` from rich intersection payloads when omitted."""
    if request.get("intersection_ids") is not None:
        return
    intersections = request.get("intersections")
    if not isinstance(intersections, list):
        return
    request["intersection_ids"] = [
        inter_id
        for item in intersections
        if isinstance(item, dict)
        for inter_id in [resolve_intersection_id(item)]
        if inter_id
    ]
