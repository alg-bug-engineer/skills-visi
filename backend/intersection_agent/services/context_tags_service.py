"""Complaint, manual survey, and field survey evidence tags."""

from __future__ import annotations

import logging
from typing import Any

from intersection_agent.config import Settings, get_settings
from intersection_agent.db.postgres import PostgresPool

logger = logging.getLogger(__name__)


class ContextTagsService:
    """Aggregate qualitative external evidence for diagnosis narrative."""

    def __init__(
        self,
        pool: PostgresPool | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._pool = pool or PostgresPool()
        self._settings = settings or get_settings()

    async def build(self, inter_id: str, inter_name: str) -> dict[str, Any]:
        if self._settings.mock_db:
            return self._mock_tags(inter_name)

        await self._pool.connect()
        flow_schema = self._settings.pg_flow_schema
        query_trace: list[dict[str, Any]] = []

        complaint_rows = await self._fetch(
            query_trace,
            "complaints",
            f"""
            SELECT complaint_type,
                   SUM(complaint_count) AS complaint_count,
                   MAX(core_problem_desc) AS sample_desc
            FROM {flow_schema}.dwd_tfc_complaint_inter_issue
            WHERE inter_id = $1 AND is_deleted = 0 AND match_status = 'matched'
            GROUP BY complaint_type
            ORDER BY complaint_count DESC
            LIMIT 8
            """,
            inter_id,
        )

        manual_rows = await self._fetch(
            query_trace,
            "manual_survey",
            f"""
            SELECT issue_type, issue_desc, issue_level
            FROM {flow_schema}.dwd_ctl_inter_manual_survey_issue
            WHERE inter_id = $1 AND is_deleted = 0
            ORDER BY issue_level DESC NULLS LAST
            LIMIT 5
            """,
            inter_id,
        )

        field_rows = await self._fetch(
            query_trace,
            "field_survey",
            f"""
            SELECT issue_category, issue_desc, severity
            FROM {flow_schema}.dwd_tfc_field_survey_inter_issue
            WHERE inter_id = $1 AND is_deleted = 0
            ORDER BY severity DESC NULLS LAST
            LIMIT 5
            """,
            inter_id,
        )

        complaints = [
            {
                "type": str(r.get("complaint_type") or "其他"),
                "count": int(r.get("complaint_count") or 0),
                "sample": str(r.get("sample_desc") or "")[:120],
            }
            for r in complaint_rows
        ]
        complaint_total = sum(c["count"] for c in complaints)

        manual_issues = [
            {
                "type": str(r.get("issue_type") or "信控问题"),
                "desc": str(r.get("issue_desc") or "")[:120],
                "level": r.get("issue_level"),
            }
            for r in manual_rows
        ]
        field_issues = [
            {
                "category": str(r.get("issue_category") or "交通组织"),
                "desc": str(r.get("issue_desc") or "")[:120],
                "severity": r.get("severity"),
            }
            for r in field_rows
        ]

        tags: list[str] = []
        if complaint_total > 0:
            tags.append("public_complaint")
            top = complaints[0]["type"] if complaints else ""
            if "配时" in top or "信号" in top:
                tags.append("signal_complaint")
        if manual_issues:
            tags.append("manual_survey")
        if field_issues:
            tags.append("field_survey")

        narrative_parts: list[str] = []
        if complaint_total > 0:
            types = "、".join(c["type"] for c in complaints[:3])
            narrative_parts.append(f"民意投诉 {complaint_total} 件，主要类型：{types}")
        if manual_issues:
            narrative_parts.append(
                f"信控人工调查记录 {len(manual_issues)} 条：{manual_issues[0].get('desc', '')[:40]}"
            )
        if field_issues:
            narrative_parts.append(
                f"交通组织调研问题 {len(field_issues)} 条：{field_issues[0].get('desc', '')[:40]}"
            )
        if not narrative_parts:
            narrative_parts.append("暂无投诉或现场调研台账，诊断完全基于运行数据")

        return {
            "complaint_total": complaint_total,
            "complaints": complaints,
            "manual_survey": manual_issues,
            "field_survey": field_issues,
            "tags": tags,
            "has_external_evidence": bool(complaint_total or manual_issues or field_issues),
            "narrative": "；".join(narrative_parts),
            "query_trace": query_trace,
        }

    async def _fetch(self, trace: list, label: str, sql: str, *params: Any) -> list[Any]:
        try:
            rows = await self._pool.fetch(sql, *params)
            trace.append({"label": label, "sql": sql, "params": [str(p) for p in params]})
            return rows
        except Exception as exc:
            logger.warning("context_tags query failed: %s %s", label, exc)
            trace.append({"label": label, "error": str(exc)})
            return []

    @staticmethod
    def _mock_tags(inter_name: str) -> dict[str, Any]:
        return {
            "complaint_total": 12,
            "complaints": [
                {"type": "信号配时不合理", "count": 8, "sample": "晚高峰东向等待时间过长"},
                {"type": "直行放行不足", "count": 4, "sample": "直行排队溢出"},
            ],
            "manual_survey": [
                {"type": "相位失衡", "desc": "东西向流量差异大，配时未区分", "level": "高"},
            ],
            "field_survey": [],
            "tags": ["public_complaint", "signal_complaint", "manual_survey"],
            "has_external_evidence": True,
            "narrative": (
                "民意投诉 12 件，主要类型：信号配时不合理、直行放行不足；"
                "信控人工调查记录 1 条：东西向流量差异大，配时未区分"
            ),
            "query_trace": [],
        }
