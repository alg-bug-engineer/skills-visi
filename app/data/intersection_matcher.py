"""Intersection name matching: colloquial input, reversed road order, PG candidates."""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any

logger = logging.getLogger(__name__)

_ROAD_SPLIT = re.compile(r"[与和及/\、]+")
_SUFFIXES = ("交叉口", "路口", "十字路", "丁字路")


def normalize_name(name: str) -> str:
    text = re.sub(r"\s+", "", name or "").strip()
    for suffix in _SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)]
            break
    return text


def _road_parts(name: str) -> list[str]:
    base = normalize_name(name)
    parts = [p.strip() for p in _ROAD_SPLIT.split(base) if p.strip()]
    return parts


def generate_name_variants(name: str) -> list[str]:
    """Generate canonical variants, including reversed road order (B与A ↔ A与B)."""
    variants: set[str] = set()
    if not name:
        return []

    raw = re.sub(r"\s+", "", name).strip()
    variants.add(raw)
    base = normalize_name(raw)
    variants.add(base)
    variants.add(f"{base}路口")
    variants.add(f"{base}交叉口")

    parts = _road_parts(raw)
    if len(parts) >= 2:
        a, b = parts[0], parts[1]
        for suffix in ("路口", "交叉口", ""):
            variants.add(f"{a}与{b}{suffix}")
            variants.add(f"{b}与{a}{suffix}")
        if len(parts) > 2:
            joined = "与".join(parts)
            variants.add(f"{joined}路口")
            variants.add(f"{'与'.join(reversed(parts))}路口")

    return [v for v in variants if v]


def collect_search_terms(
    *,
    primary_name: str | None,
    candidates: list[str] | None,
    user_input: str,
) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    def _add(term: str) -> None:
        term = term.strip()
        if not term or term in seen:
            return
        seen.add(term)
        terms.append(term)

    for source in (primary_name, *(candidates or [])):
        if not source:
            continue
        _add(source)
        for variant in generate_name_variants(source):
            _add(variant)

    for match in re.findall(r"[\u4e00-\u9fff]{2,20}(?:路|街|道|大道|大街)", user_input or ""):
        _add(match)

    return terms


def _token_set(name: str) -> set[str]:
    base = normalize_name(name)
    tokens = set(_road_parts(base))
    tokens.add(base)
    for part in list(tokens):
        if part.endswith("路"):
            tokens.add(part[:-1])
    return {t for t in tokens if t}


def score_candidate(
    *,
    query_terms: list[str],
    user_input: str,
    candidate: dict[str, Any],
) -> float:
    name = str(candidate.get("inter_name") or "")
    cand_norm = normalize_name(name)
    best = 0.0

    for term in query_terms:
        term_norm = normalize_name(term)
        if not term_norm:
            continue
        if term_norm == cand_norm:
            best = max(best, 1.0)
            continue
        if term_norm in cand_norm or cand_norm in term_norm:
            best = max(best, 0.92)
            continue

        term_parts = _road_parts(term)
        cand_parts = _road_parts(name)
        if len(term_parts) >= 2 and len(cand_parts) >= 2:
            if set(term_parts) == set(cand_parts):
                best = max(best, 0.95)
            elif set(term_parts) <= set(cand_parts) or set(cand_parts) <= set(term_parts):
                best = max(best, 0.85)

        ratio = SequenceMatcher(None, term_norm, cand_norm).ratio()
        best = max(best, ratio * 0.9)

        if term in (user_input or ""):
            best = max(best, 0.8)

    token_overlap = len(_token_set(" ".join(query_terms)) & _token_set(name))
    if token_overlap:
        best = max(best, min(0.75 + token_overlap * 0.08, 0.98))

    return round(best, 4)


def search_pg_candidates(
    patterns: list[str],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    from app.config import get_settings

    settings = get_settings()
    if not settings.pg_dsn:
        return []

    from app.data.pg_client import read_pg_rows

    version_sql = (
        f"(SELECT version_id FROM {settings.pg_schema}.dim_data_version "
        "WHERE is_enable = 1 LIMIT 1)"
    )
    table = settings.pg_dim_inter_table
    schema = settings.pg_schema

    merged: dict[str, dict[str, Any]] = {}
    for pattern in patterns[:12]:
        term = pattern.replace("%", "").strip()
        if len(term) < 2:
            continue
        sql = f"""
            SELECT inter_id, inter_name, geom_center
            FROM {schema}.{table}
            WHERE version_id = {version_sql}
              AND is_signalized = 1
              AND inter_name LIKE %(pattern)s
            ORDER BY LENGTH(inter_name)
            LIMIT %(lim)s
        """
        try:
            rows = read_pg_rows(sql, {"pattern": f"%{term}%", "lim": limit}, limit=limit)
        except Exception as exc:
            logger.warning("PG 路口候选检索失败 pattern=%s err=%s", term, exc)
            continue
        for row in rows:
            merged[str(row["inter_id"])] = row

    return list(merged.values())


def match_intersection(
    *,
    primary_name: str | None,
    candidates: list[str] | None = None,
    user_input: str = "",
    min_confidence: float = 0.55,
) -> dict[str, Any]:
    """Match user/LLM intersection expression to PG registry record."""
    from app.data.intersection_registry import load_registry, _parse_geom_center

    query_terms = collect_search_terms(
        primary_name=primary_name,
        candidates=candidates,
        user_input=user_input,
    )

    registry = load_registry()
    registry_candidates = list(registry.values())

    pg_candidates = search_pg_candidates(query_terms, limit=15)
    all_candidates = registry_candidates + pg_candidates

    scored: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for cand in all_candidates:
        inter_id = str(cand.get("inter_id") or "")
        if inter_id in seen_ids:
            continue
        seen_ids.add(inter_id)
        confidence = score_candidate(
            query_terms=query_terms,
            user_input=user_input,
            candidate=cand,
        )
        scored.append(
            {
                "inter_id": inter_id,
                "inter_name": cand.get("inter_name"),
                "confidence": confidence,
                "source": cand.get("source", "pg" if cand in pg_candidates else "fixture"),
            }
        )

    scored.sort(key=lambda item: item["confidence"], reverse=True)
    top = scored[0] if scored else None

    if not top or top["confidence"] < min_confidence:
        return {
            "matched": False,
            "intersection_name": primary_name,
            "match_confidence": top["confidence"] if top else 0.0,
            "match_candidates": scored[:5],
            "match_method": "none",
            "query_terms": query_terms,
        }

    from app.data.intersection_registry import resolve_intersection

    lng: float | None = None
    lat: float | None = None
    for cand in pg_candidates:
        if str(cand.get("inter_id")) == top["inter_id"]:
            center = cand.get("geom_center")
            if center:
                from app.data.intersection_registry import _parse_geom_center

                lng, lat = _parse_geom_center(center)
            break
    if lng is None:
        record = resolve_intersection(top["inter_name"], inter_id=top["inter_id"])
        if record:
            lng = record.get("lng")
            lat = record.get("lat")

    return {
        "matched": True,
        "inter_id": top["inter_id"],
        "intersection_name": top["inter_name"],
        "lng": lng,
        "lat": lat,
        "match_confidence": top["confidence"],
        "match_candidates": scored[:5],
        "match_method": "reversed_order" if _is_reversed_match(query_terms, top["inter_name"]) else "fuzzy",
        "query_terms": query_terms,
    }


def _is_reversed_match(query_terms: list[str], matched_name: str) -> bool:
    cand_parts = _road_parts(matched_name)
    if len(cand_parts) < 2:
        return False
    for term in query_terms:
        parts = _road_parts(term)
        if len(parts) >= 2 and parts == list(reversed(cand_parts)):
            return True
    return False


def enrich_ticket_with_match(ticket: dict[str, Any], *, user_input: str = "") -> dict[str, Any]:
    """Enrich ticket using matcher; preserves explicit inter_id when already set."""
    enriched = dict(ticket)
    if enriched.get("inter_id"):
        enriched.setdefault("match_confidence", 1.0)
        enriched.setdefault("match_method", "explicit")
        return enriched

    match = match_intersection(
        primary_name=enriched.get("intersection_name"),
        candidates=enriched.get("intersection_name_candidates"),
        user_input=user_input,
    )
    if match.get("matched"):
        enriched["inter_id"] = match["inter_id"]
        enriched["intersection_name"] = match["intersection_name"]
        if match.get("lng") is not None:
            enriched["lng"] = match["lng"]
        if match.get("lat") is not None:
            enriched["lat"] = match["lat"]
    enriched["match_confidence"] = match.get("match_confidence", 0.0)
    enriched["match_candidates"] = match.get("match_candidates", [])
    enriched["match_method"] = match.get("match_method", "none")
    return enriched
