"""Aggregate textbook cases and plan feedback for frontend case panels."""

from __future__ import annotations

from typing import Any

from app.services.case_library import CaseLibraryService
from app.services.feedback_service import PlanFeedbackService


class CasesCatalogService:
    def __init__(
        self,
        case_service: CaseLibraryService,
        feedback_service: PlanFeedbackService,
    ) -> None:
        self.case_service = case_service
        self.feedback_service = feedback_service

    def list_cases(
        self,
        *,
        problem_type: str | None = None,
        inter_id: str | None = None,
        category: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        cases: list[dict[str, Any]] = []

        if category in (None, "textbook"):
            cards = self.case_service.search_case_cards(
                problem_type=problem_type or "排队溢出",
                limit=limit,
            )
            for index, card in enumerate(cards.get("cards") or []):
                cases.append(
                    {
                        "case_id": f"textbook_{index}",
                        "category": "textbook",
                        "title": card.get("title") or "教科书案例",
                        "similarity": card.get("similarity"),
                        "action": card.get("action"),
                        "outcome": card.get("outcome"),
                        "lesson": card.get("lesson"),
                    }
                )

        if category in (None, "recommended"):
            for record in self.feedback_service.search_accepted_plans(
                inter_id=inter_id,
                problem_type=problem_type,
                limit=limit,
            ):
                tags = record.get("tags") or {}
                cases.append(
                    {
                        "case_id": f"recommended_{record.get('trace_id')}_{record.get('plan_id')}",
                        "category": "recommended",
                        "title": tags.get("strategy_applied") or record.get("plan_id"),
                        "trace_id": record.get("trace_id"),
                        "plan_id": record.get("plan_id"),
                        "lesson": tags.get("primary_cause") or "历史接受方案",
                        "tags": tags,
                    }
                )

        if category in (None, "risk"):
            for record in self.feedback_service.search_rejected_patterns(
                inter_id=inter_id,
                problem_type=problem_type,
                limit=limit,
            ):
                cases.append(
                    {
                        "case_id": f"risk_{record.get('trace_id')}_{record.get('plan_id')}",
                        "category": "risk",
                        "title": record.get("plan_id"),
                        "trace_id": record.get("trace_id"),
                        "plan_id": record.get("plan_id"),
                        "lesson": record.get("rejection_reason") or "历史否决方案",
                        "tags": record.get("tags") or {},
                    }
                )

        if category:
            cases = [item for item in cases if item.get("category") == category]

        total = len(cases)
        return {"cases": cases[:limit], "total": total}
