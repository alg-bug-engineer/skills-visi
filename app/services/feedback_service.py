"""Persist plan accept/reject feedback after plan generation."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.services.plan_fingerprint import (
    build_feedback_tags,
    build_metrics_summary,
    build_topology_hash,
    fingerprint_similarity,
)

logger = logging.getLogger(__name__)

PlanDecision = Literal["accept", "reject"]


class PlanFeedbackService:
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self._records: list[dict[str, Any]] | None = None

    def record_decision(
        self,
        *,
        trace_id: str,
        plan_id: str,
        decision: PlanDecision,
        rejection_reason: str | None = None,
        plan_snapshot: dict[str, Any] | None = None,
        diagnosis_ticket: dict[str, Any] | None = None,
        artifacts_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if decision == "reject" and rejection_reason is not None:
            rejection_reason = rejection_reason.strip() or None

        artifacts = artifacts_summary or {}
        diagnosis = artifacts.get("data_analysis_diagnosis") or {}
        topology = diagnosis.get("topology") or artifacts.get("topology")
        ticket = diagnosis_ticket or artifacts.get("diagnosis_ticket") or {}
        cause_analysis = artifacts.get("cause_analysis") or {}
        strategy_generation = artifacts.get("strategy_generation") or {}

        fingerprint = {
            "problem_type": ticket.get("problem_type"),
            "topology_hash": build_topology_hash(topology),
            "metrics_summary": build_metrics_summary(diagnosis),
        }
        tags = build_feedback_tags(
            diagnosis_ticket=ticket,
            cause_analysis=cause_analysis,
            strategy_generation=strategy_generation,
        )

        entry = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "trace_id": trace_id,
            "plan_id": plan_id,
            "decision": decision,
            "rejection_reason": rejection_reason if decision == "reject" else None,
            "plan_snapshot": plan_snapshot,
            "diagnosis_ticket": ticket,
            "inter_id": ticket.get("inter_id"),
            "fingerprint": fingerprint,
            "tags": tags,
            "retrieval": {
                "as_recommended_case": decision == "accept",
                "as_risk_case": decision == "reject",
            },
        }

        self._append_jsonl(entry)
        self._records = None
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
            "fingerprint": fingerprint,
            "tags": tags,
        }

    def search_accepted_plans(
        self,
        *,
        fingerprint: dict[str, Any] | None = None,
        inter_id: str | None = None,
        problem_type: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        scored: list[tuple[float, dict[str, Any]]] = []
        for record in self._load():
            if record.get("decision") != "accept":
                continue
            if inter_id and record.get("inter_id") != inter_id:
                continue
            score = 1.0
            record_fp = record.get("fingerprint") or {}
            if fingerprint:
                score += fingerprint_similarity(fingerprint, record_fp)
            if problem_type and (record_fp.get("problem_type") == problem_type):
                score += 1.0
            if score > 0:
                scored.append((score, record))

        scored.sort(key=lambda item: item[0], reverse=True)
        results: list[dict[str, Any]] = []
        for score, record in scored[:limit]:
            results.append(
                {
                    "trace_id": record.get("trace_id"),
                    "plan_id": record.get("plan_id"),
                    "decision": record.get("decision"),
                    "tags": record.get("tags") or {},
                    "fingerprint": record.get("fingerprint") or {},
                    "plan_snapshot": record.get("plan_snapshot"),
                    "score": score,
                }
            )
        return results

    def search_rejected_patterns(
        self,
        *,
        inter_id: str | None = None,
        problem_type: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for record in self._load():
            if record.get("decision") != "reject":
                continue
            if inter_id and record.get("inter_id") != inter_id:
                continue
            fp = record.get("fingerprint") or {}
            if problem_type and fp.get("problem_type") != problem_type:
                continue
            results.append(
                {
                    "trace_id": record.get("trace_id"),
                    "plan_id": record.get("plan_id"),
                    "rejection_reason": record.get("rejection_reason"),
                    "tags": record.get("tags") or {},
                    "plan_snapshot": record.get("plan_snapshot"),
                    "fingerprint": fp,
                }
            )
            if len(results) >= limit:
                break
        return results

    def _load(self) -> list[dict[str, Any]]:
        if self._records is not None:
            return self._records
        if not self.log_path.exists():
            self._records = []
            return self._records

        records: list[dict[str, Any]] = []
        with self.log_path.open(encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    logger.warning("方案反馈第 %d 行解析失败: %s", line_no, exc)
        self._records = records
        return self._records

    def _append_jsonl(self, entry: dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
