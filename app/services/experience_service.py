"""Persist user experiences extracted during NLU."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


def experience_signature(entry: dict[str, Any]) -> str:
    """内容指纹：仅取语义字段（忽略 record_id/recorded_at/trace_id），用于去重。

    含认知/诊断经验的 content、来源片段、标签（标签内含 inter_id/路口名，
    故同内容不同路口不会误判为重复）。
    """
    payload = {
        "experience_type": entry.get("experience_type"),
        "content": (entry.get("content") or "").strip(),
        "source_span": (entry.get("source_span") or "").strip(),
        "tags": entry.get("tags") or {},
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class ExperienceService:
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self._signatures: set[str] | None = None

    def persist_from_intent(
        self,
        *,
        trace_id: str,
        user_experiences: list[dict[str, Any]],
        diagnosis_ticket: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not user_experiences:
            return []

        signatures = self._load_signatures()
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
            sig = experience_signature(entry)
            if sig in signatures:
                logger.info(
                    "用户经验已存在，跳过重复 trace_id=%s type=%s",
                    trace_id,
                    entry["experience_type"],
                )
                continue
            self._append_jsonl(entry)
            signatures.add(sig)
            recorded.append(entry)
            logger.info(
                "用户经验已沉淀 trace_id=%s type=%s record_id=%s",
                trace_id,
                entry["experience_type"],
                entry["record_id"],
            )
        return recorded

    def _load_signatures(self) -> set[str]:
        if self._signatures is not None:
            return self._signatures
        signatures: set[str] = set()
        if self.log_path.exists():
            with self.log_path.open(encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        signatures.add(experience_signature(json.loads(line)))
                    except json.JSONDecodeError:
                        continue
        self._signatures = signatures
        return signatures

    def _append_jsonl(self, entry: dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
