"""Aggregate textbook cases and plan feedback for frontend case panels."""

from __future__ import annotations

import logging
from typing import Any

from app.services.case_library import CaseLibraryService
from app.services.feedback_service import PlanFeedbackService

logger = logging.getLogger(__name__)


class CasesCatalogService:
    def __init__(
        self,
        case_service: CaseLibraryService,
        feedback_service: PlanFeedbackService,
        skill_service: Any | None = None,
    ) -> None:
        self.case_service = case_service
        self.feedback_service = feedback_service
        # 固化技能服务（SkillSolidificationService）；缺省时不 join，仅影响下载入口。
        self.skill_service = skill_service

    def _skill_index(self) -> dict[str, list[dict[str, Any]]]:
        """按 inter_id 归集已固化技能，供路口案例 join 下载入口。"""
        if self.skill_service is None:
            return {}
        index: dict[str, list[dict[str, Any]]] = {}
        try:
            skills = self.skill_service.list_skills()
        except Exception as exc:  # pragma: no cover - 目录缺失等降级
            logger.warning("固化技能列表读取失败，跳过 join: %s", exc)
            return {}
        for meta in skills:
            inter_id = meta.get("inter_id")
            if not inter_id:
                match = (meta.get("tags") or {}).get("match") or {}
                inter_id = match.get("inter_id")
            if not inter_id:
                continue
            index.setdefault(str(inter_id), []).append(meta)
        return index

    @staticmethod
    def _match_skill(
        skills: list[dict[str, Any]],
        *,
        time_period: str | None,
    ) -> dict[str, Any] | None:
        if not skills:
            return None
        if time_period:
            for meta in skills:
                match = (meta.get("tags") or {}).get("match") or {}
                if time_period in (
                    meta.get("time_period_label"),
                    match.get("time_period"),
                ):
                    return meta
        return skills[0]

    def list_cases(
        self,
        *,
        problem_type: str | None = None,
        inter_id: str | None = None,
        category: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        cases: list[dict[str, Any]] = []
        skill_index = self._skill_index()

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
                        "action": card.get("action") or card.get("historical_action"),
                        "outcome": card.get("outcome"),
                        "lesson": card.get("lesson"),
                        "structured_tags": card.get("structured_tags") or {},
                        "similarity_dimensions": card.get("similarity_dimensions") or [],
                        "transferable_actions": card.get("transferable_actions") or [],
                    }
                )

        if category in (None, "recommended"):
            # 去重：同路口 + 同策略 + 同时段视为同一沉淀方案，保留最新一条。
            seen_recommended: set[tuple[Any, Any, Any]] = set()
            for record in self.feedback_service.search_accepted_plans(
                inter_id=inter_id,
                problem_type=problem_type,
                limit=limit,
            ):
                tags = record.get("tags") or {}
                rec_inter_id = record.get("inter_id")
                time_period = record.get("time_period")
                strategy_applied = tags.get("strategy_applied")
                dedup_key = (rec_inter_id, strategy_applied, time_period)
                if dedup_key in seen_recommended:
                    continue
                seen_recommended.add(dedup_key)

                skill_meta = self._match_skill(
                    skill_index.get(str(rec_inter_id), []),
                    time_period=time_period,
                )
                cases.append(
                    {
                        "case_id": f"recommended_{record.get('trace_id')}_{record.get('plan_id')}",
                        "category": "recommended",
                        "title": strategy_applied or record.get("plan_id"),
                        "trace_id": record.get("trace_id"),
                        "plan_id": record.get("plan_id"),
                        "inter_id": rec_inter_id,
                        "intersection_name": record.get("intersection_name"),
                        "time_period": time_period,
                        "recorded_at": record.get("recorded_at"),
                        "lesson": tags.get("primary_cause") or "历史接受方案",
                        "tags": tags,
                        "skill": (
                            {
                                "skill_id": skill_meta.get("skill_id"),
                                "download_url": skill_meta.get("download_url"),
                                "time_period_label": skill_meta.get("time_period_label"),
                            }
                            if skill_meta
                            else None
                        ),
                    }
                )

        if category in (None, "risk"):
            seen_risk: set[tuple[Any, Any]] = set()
            for record in self.feedback_service.search_rejected_patterns(
                inter_id=inter_id,
                problem_type=problem_type,
                limit=limit,
            ):
                rec_inter_id = record.get("inter_id")
                rejection_reason = record.get("rejection_reason")
                dedup_key = (rec_inter_id, rejection_reason)
                if dedup_key in seen_risk:
                    continue
                seen_risk.add(dedup_key)
                cases.append(
                    {
                        "case_id": f"risk_{record.get('trace_id')}_{record.get('plan_id')}",
                        "category": "risk",
                        "title": record.get("plan_id"),
                        "trace_id": record.get("trace_id"),
                        "plan_id": record.get("plan_id"),
                        "inter_id": rec_inter_id,
                        "intersection_name": record.get("intersection_name"),
                        "time_period": record.get("time_period"),
                        "recorded_at": record.get("recorded_at"),
                        "lesson": rejection_reason or "历史否决方案",
                        "tags": record.get("tags") or {},
                    }
                )

        if category:
            cases = [item for item in cases if item.get("category") == category]

        total = len(cases)
        logger.info(
            "list_cases category=%s inter_id=%s problem_type=%s total=%d",
            category,
            inter_id,
            problem_type,
            total,
        )
        return {"cases": cases[:limit], "total": total}
