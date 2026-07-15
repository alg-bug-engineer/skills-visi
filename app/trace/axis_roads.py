"""Derive east-west / north-south road labels for intersection spatial cognition."""

from __future__ import annotations

import re
from collections import Counter
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


def _known_road_from_text(text: str | None, road_pair: tuple[str | None, str | None]) -> str | None:
    """Pick a target-intersection road mentioned by a topology label.

    Direction labels such as ``西进口`` are deliberately excluded: they describe
    an approach bearing, not a road name.
    """
    if not text:
        return None
    value = str(text).strip()
    if not value:
        return None
    matches = [road for road in road_pair if road and road in value]
    # A label that contains both target roads is usually the target intersection
    # itself and cannot prove either axis.
    return matches[0] if len(matches) == 1 else None


def _most_common(values: list[str]) -> str | None:
    if not values:
        return None
    return Counter(values).most_common(1)[0][0]


def build_axis_roads(
    *,
    intersection_name: str | None = None,
    channel_rows: list[dict[str, Any]] | None = None,
    link_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return axis road labels for voice / spatial cognition.

    Priority: channelization road_name / adjacent-intersection topology →
    intersection name pair (unordered).
    """
    road_pair = parse_road_pair_from_intersection(intersection_name)
    ew_votes: list[str] = []
    ns_votes: list[str] = []
    source = "none"

    rows = list(channel_rows or []) + list(link_rows or [])
    for row in rows:
        role = str(row.get("link_role") or "")
        if role and role != "entrance":
            continue
        dir8 = _dir8_code(row)
        road_name = _road_head(row.get("road_name"))
        label = _known_road_from_text(road_name, road_pair)
        if not label:
            label = _known_road_from_text(row.get("adjacent_inter_name"), road_pair)
        # When the intersection name cannot be parsed, a real road_name remains
        # useful. Never fall back to dir8_label ("西进口"/"北进口").
        if not label and not any(road_pair):
            label = road_name
        if not label:
            continue
        if dir8 in _EW_DIR8:
            ew_votes.append(label)
        elif dir8 in _NS_DIR8:
            ns_votes.append(label)

    ew = _most_common(ew_votes)
    ns = _most_common(ns_votes)
    if ew or ns:
        source = "road_topology"

    # One reliable axis determines the other road at a two-road intersection.
    known_pair = [road for road in road_pair if road]
    if len(known_pair) == 2:
        if ew and not ns:
            ns = next((road for road in known_pair if road != ew), None)
        elif ns and not ew:
            ew = next((road for road in known_pair if road != ns), None)
        if ew and ew == ns:
            other = next((road for road in known_pair if road != ew), None)
            if other:
                if len(ew_votes) >= len(ns_votes):
                    ns = other
                else:
                    ew = other

    if not ew and not ns:
        a, b = road_pair
        if a and b:
            source = "intersection_name_unordered"

    available = bool(ew or ns or all(road_pair))
    return {
        "ew_road": ew,
        "ns_road": ns,
        "road_pair": [road for road in road_pair if road],
        "available": available,
        "source": source if available else "none",
    }
