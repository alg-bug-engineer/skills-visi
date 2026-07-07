"""Search persisted user experiences."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _tag_value(tags: dict[str, Any], key: str) -> str:
    value = tags.get(key)
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value)


class ExperienceLibraryService:
    def __init__(self, library_path: Path) -> None:
        self.library_path = library_path
        self._records: list[dict[str, Any]] | None = None

    def _load(self) -> list[dict[str, Any]]:
        if self._records is not None:
            return self._records
        if not self.library_path.exists():
            self._records = []
            return self._records

        records: list[dict[str, Any]] = []
        with self.library_path.open(encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    logger.warning("用户经验库第 %d 行解析失败: %s", line_no, exc)
        self._records = records
        logger.info("用户经验库加载完成 path=%s count=%d", self.library_path, len(records))
        return self._records

    def reload(self) -> None:
        self._records = None

    def _score_record(
        self,
        record: dict[str, Any],
        *,
        inter_id: str | None = None,
        intersection_name: str | None = None,
        problem_type: str | None = None,
        cause_dimension: str | None = None,
        keywords: list[str] | None = None,
        strategy_action: str | None = None,
        time_period: str | None = None,
    ) -> float:
        tags = record.get("tags") or {}
        score = 0.0
        content = f"{record.get('content', '')} {_tag_value(tags, 'cause_keywords')}"

        if inter_id and tags.get("inter_id") == inter_id:
            score += 3.0
        if intersection_name and tags.get("intersection_name") == intersection_name:
            score += 2.0
        elif intersection_name and intersection_name in _tag_value(tags, "intersection_name"):
            score += 1.0

        if problem_type and problem_type in _tag_value(tags, "problem_type"):
            score += 1.5
        if time_period and tags.get("time_period") == time_period:
            score += 1.0
        if cause_dimension and tags.get("cause_dimension") == cause_dimension:
            score += 2.0
        if strategy_action and tags.get("strategy_action") == strategy_action:
            score += 2.0

        for kw in keywords or []:
            if kw and kw in content:
                score += 0.5

        return score

    def search_cognitive(
        self,
        *,
        inter_id: str | None = None,
        intersection_name: str | None = None,
        problem_type: str | None = None,
        time_period: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        return self._search(
            experience_type="cognitive",
            inter_id=inter_id,
            intersection_name=intersection_name,
            problem_type=problem_type,
            time_period=time_period,
            limit=limit,
        )

    def search_diagnostic(
        self,
        *,
        inter_id: str | None = None,
        intersection_name: str | None = None,
        cause_dimension: str | None = None,
        keywords: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        return self._search(
            experience_type="diagnostic",
            inter_id=inter_id,
            intersection_name=intersection_name,
            cause_dimension=cause_dimension,
            keywords=keywords,
            limit=limit,
        )

    def search_solution(
        self,
        *,
        inter_id: str | None = None,
        intersection_name: str | None = None,
        strategy_action: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        return self._search(
            experience_type="solution",
            inter_id=inter_id,
            intersection_name=intersection_name,
            strategy_action=strategy_action,
            limit=limit,
        )

    def search_all_for_context(
        self,
        *,
        ticket: dict[str, Any],
        limit_per_type: int = 3,
    ) -> dict[str, list[dict[str, Any]]]:
        inter_id = ticket.get("inter_id")
        intersection_name = ticket.get("intersection_name")
        problem_type = ticket.get("problem_type")
        time_period = None
        return {
            "cognitive": self.search_cognitive(
                inter_id=inter_id,
                intersection_name=intersection_name,
                problem_type=problem_type,
                time_period=time_period,
                limit=limit_per_type,
            ),
            "diagnostic": self.search_diagnostic(
                inter_id=inter_id,
                intersection_name=intersection_name,
                limit=limit_per_type,
            ),
            "solution": self.search_solution(
                inter_id=inter_id,
                intersection_name=intersection_name,
                limit=limit_per_type,
            ),
        }

    def _search(
        self,
        *,
        experience_type: str,
        limit: int,
        **criteria: Any,
    ) -> list[dict[str, Any]]:
        scored: list[tuple[float, dict[str, Any]]] = []
        for record in self._load():
            if record.get("experience_type") != experience_type:
                continue
            score = self._score_record(record, **criteria)
            if score > 0:
                scored.append((score, record))

        scored.sort(key=lambda item: item[0], reverse=True)
        results: list[dict[str, Any]] = []
        for score, record in scored[:limit]:
            results.append(
                {
                    "record_id": record.get("record_id"),
                    "trace_id": record.get("trace_id"),
                    "experience_type": record.get("experience_type"),
                    "content": record.get("content"),
                    "tags": record.get("tags") or {},
                    "score": score,
                }
            )
        return results

    def count(self) -> int:
        return len(self._load())
