"""Derive east-west / north-south road labels for intersection spatial cognition."""

from __future__ import annotations

import re
from typing import Any

_EW_DIR8 = frozenset({2, 6})
_NS_DIR8 = frozenset({0, 4})
_NAME_SPLIT = re.compile(r"[与和×]")


def _road_head(road_name: str | None) -> str | None:
    if not road_name or not isinstance(road_name, str):
        return None
    text = road_name.strip()
    if not text:
        return None
    head = text.split(":", 1)[0].strip()
    return head or None


def parse_road_pair_from_intersection(intersection_name: str | None) -> tuple[str | None, str | None]:
    if not intersection_name:
        return None, None
    name = str(intersection_name).replace("路口", "").strip()
    parts = _NAME_SPLIT.split(name, maxsplit=1)
    if len(parts) == 2:
        left, right = parts[0].strip(), parts[1].strip()
        return left or None, right or None
    return None, None


def _dir8_code(row: dict[str, Any]) -> int | None:
    raw = row.get("dir8_code")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def build_axis_roads(
    *,
    intersection_name: str | None = None,
    channel_rows: list[dict[str, Any]] | None = None,
    link_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return axis road labels for voice / spatial cognition.

    Priority: channelization entrance links → intersection name pair (unordered).
    """
    ew: str | None = None
    ns: str | None = None
    source = "none"

    rows = list(channel_rows or []) + list(link_rows or [])
    for row in rows:
        role = str(row.get("link_role") or "")
        if role and role != "entrance":
            continue
        dir8 = _dir8_code(row)
        label = _road_head(row.get("road_name")) or str(row.get("dir8_label") or "").replace("进口", "").strip()
        if not label:
            continue
        if dir8 in _EW_DIR8 and not ew:
            ew = label
            source = "channelization"
        elif dir8 in _NS_DIR8 and not ns:
            ns = label
            source = "channelization"

    if not ew and not ns:
        a, b = parse_road_pair_from_intersection(intersection_name)
        if a and b:
            # Name pair only — assign arbitrarily to ew/ns slots for TTS; voice layer uses generic wording.
            ew, ns = a, b
            source = "intersection_name"

    available = bool(ew or ns)
    return {
        "ew_road": ew,
        "ns_road": ns,
        "available": available,
        "source": source if available else "none",
    }
