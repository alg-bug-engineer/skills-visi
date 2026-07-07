"""Persist user experiences extracted during NLU."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class ExperienceService:
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path

    def persist_from_intent(
        self,
        *,
        trace_id: str,
        user_experiences: list[dict[str, Any]],
        diagnosis_ticket: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not user_experiences:
            return []

        recorded: list[dict[str, Any]] = []
        for item in user_experiences:
            entry = {
                "record_id": f"ue_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid4().hex[:8]}",
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "trace_id": trace_id,
                "experience_type": item.get("experience_type"),
                "content": item.get("content"),
                "source_span": item.get("source_span"),
                "tags": item.get("tags") or {},
                "diagnosis_ticket_snapshot": diagnosis_ticket or {},
            }
            self._append_jsonl(entry)
            recorded.append(entry)
            logger.info(
                "用户经验已沉淀 trace_id=%s type=%s record_id=%s",
                trace_id,
                entry["experience_type"],
                entry["record_id"],
            )
        return recorded

    def _append_jsonl(self, entry: dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
