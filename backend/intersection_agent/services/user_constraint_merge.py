"""Merge user governance constraints without duplicating clauses."""

from __future__ import annotations

import re

_CLAUSE_SPLIT = re.compile(r"[，,。；;]")


def _normalize_clause(text: str) -> str:
    return re.sub(r"\s+", "", text.strip())


def merge_user_constraints(
    existing: str | None,
    new: str | None,
) -> str | None:
    """Append new governance clauses to existing; dedupe by normalized clause text."""
    parts: list[str] = []
    seen: set[str] = set()

    def add(text: str | None) -> None:
        if not text or not text.strip():
            return
        for clause in _CLAUSE_SPLIT.split(text.strip()):
            cleaned = clause.strip()
            if not cleaned:
                continue
            norm = _normalize_clause(cleaned)
            if norm in seen:
                continue
            seen.add(norm)
            parts.append(cleaned)

    add(existing)
    add(new)
    if not parts:
        return None
    return "，".join(parts)
