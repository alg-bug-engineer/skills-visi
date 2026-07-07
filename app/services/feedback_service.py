"""Persist plan accept/reject feedback after plan generation."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

PlanDecision = Literal["accept", "reject"]


class PlanFeedbackService:
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path

    def record_decision(
        self,
        *,
        trace_id: str,
        plan_id: str,
        decision: PlanDecision,
        rejection_reason: str | None = None,
        plan_snapshot: dict[str, Any] | None = None,
        diagnosis_ticket: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if decision == "reject" and rejection_reason is not None:
            rejection_reason = rejection_reason.strip() or None

        entry = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "trace_id": trace_id,
            "plan_id": plan_id,
            "decision": decision,
            "rejection_reason": rejection_reason if decision == "reject" else None,
            "plan_snapshot": plan_snapshot,
            "diagnosis_ticket": diagnosis_ticket,
        }

        self._append_jsonl(entry)
        logger.info(
            "方案反馈已记录 trace_id=%s plan_id=%s decision=%s",
            trace_id,
            plan_id,
            decision,
        )
        return {
            "ok": True,
            "trace_id": trace_id,
            "plan_id": plan_id,
            "decision": decision,
            "rejection_reason": entry["rejection_reason"],
            "recorded_at": entry["recorded_at"],
        }

    def _append_jsonl(self, entry: dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
