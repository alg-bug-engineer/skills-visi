"""Resolve user pick from corridor scan ranking."""

from __future__ import annotations

import re
from typing import Any

from intersection_agent.utils.corridor_geometry import extract_junction_roads, normalize_road_token

_RANK_PATTERNS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"最堵|最拥堵|最严重|第一|排名第?一|第一个|头一个|首位"), 1),
    (re.compile(r"第二|排名第?二|第二个"), 2),
    (re.compile(r"第三|排名第?三|第三个"), 3),
    (re.compile(r"第四|排名第?四|第四个"), 4),
    (re.compile(r"第五|排名第?五|第五个"), 5),
]


def resolve_corridor_pick(
    user_text: str,
    ranked: list[dict[str, Any]],
    *,
    inter_id: str | None = None,
    inter_name: str | None = None,
) -> dict[str, Any] | None:
    if not ranked:
        return None
    if inter_id:
        for item in ranked:
            if str(item.get("inter_id")) == str(inter_id):
                return item
    if inter_name:
        matched = _match_by_name(inter_name, ranked)
        if matched:
            return matched
    text = user_text.strip()
    if not text:
        return None
    for pattern, rank in _RANK_PATTERNS:
        if pattern.search(text):
            return _by_rank(ranked, rank)
    junction = extract_junction_roads(text)
    if junction:
        matched = _match_by_junction(junction, ranked)
        if matched:
            return matched
    matched = _match_by_name(text, ranked)
    if matched:
        return matched
    for token in re.findall(r"[\u4e00-\u9fff]{2,14}路", text):
        norm = normalize_road_token(token)
        candidates = [item for item in ranked if norm in str(item.get("inter_name") or "")]
        if len(candidates) == 1:
            return candidates[0]
    return None


def _match_by_junction(
    junction: tuple[str, str],
    ranked: list[dict[str, Any]],
) -> dict[str, Any] | None:
    a, b = junction
    best: dict[str, Any] | None = None
    best_score = -1
    for item in ranked:
        iname = str(item.get("inter_name") or "")
        if not iname:
            continue
        score = 0
        if a in iname:
            score += 2
        if b in iname:
            score += 2
        if score > best_score:
            best_score = score
            best = item
    if best_score >= 4:
        return best
    return None


def _match_by_name(text: str, ranked: list[dict[str, Any]]) -> dict[str, Any] | None:
    name = text.strip().replace("交叉口", "")
    if not name:
        return None
    compact = name.replace("路口", "")
    for item in ranked:
        iname = str(item.get("inter_name") or "")
        iname_compact = iname.replace("路口", "")
        if not iname:
            continue
        if name in iname or iname in name:
            return item
        if compact and (compact in iname_compact or iname_compact in compact):
            return item
    junction = extract_junction_roads(name)
    if junction:
        return _match_by_junction(junction, ranked)
    return None


def _by_rank(ranked: list[dict[str, Any]], rank: int) -> dict[str, Any] | None:
    with_rank = [r for r in ranked if r.get("has_data") and r.get("rank") is not None]
    with_rank.sort(key=lambda x: int(x.get("rank") or 999))
    for item in with_rank:
        if int(item.get("rank") or 0) == rank:
            return item
    if rank == 1 and with_rank:
        return with_rank[0]
    if 0 < rank <= len(with_rank):
        return with_rank[rank - 1]
    return None
