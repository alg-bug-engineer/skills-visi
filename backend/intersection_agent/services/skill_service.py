"""Skill persistence — standard Agent Skill packages under data/skills/."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from intersection_agent.config import Settings, get_settings
from intersection_agent.models.domain import NluResult, Session
from intersection_agent.models.skill import (
    DEFAULT_PROBLEM_TYPE,
    SkillDiff,
    SkillMatchResult,
    SkillRecord,
    SkillUpsertResult,
)
from intersection_agent.skills.interleaved_skill_persist_visualizer import (
    InterleavedSkillPersistVisualizer,
)
from intersection_agent.skills.package_builder import SkillPackageBuilder, skill_dir_name
from intersection_agent.services.skill_matcher import build_skill_tags, compare_content_tags, match_skill
from intersection_agent.services.user_constraint_merge import merge_user_constraints
from intersection_agent.skills.tag_helpers import increment_usage_meta, merge_usage_meta, read_hit_count, read_last_hit_at

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from intersection_agent.hooks.execution_emitter import ExecutionEmitter


class SkillService:
    """Skill store: one directory per skill (SKILL.md + scripts + reference)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._root = Path(self._settings.skill_dir_path)
        self._root.mkdir(parents=True, exist_ok=True)
        self._builder = SkillPackageBuilder(self._root)

    def find_match(self, nlu: NluResult, inter_id: str | None, raw_text: str) -> SkillRecord | None:
        """Find skill by intersection id, problem type, and keywords."""
        result = self.find_match_result(nlu, inter_id, raw_text)
        return result.skill if result.matched else None

    def find_match_result(
        self, nlu: NluResult, inter_id: str | None, raw_text: str
    ) -> SkillMatchResult:
        """Find skill with structured match reason for orchestrator and SSE."""
        if not inter_id or not nlu.time_period:
            return SkillMatchResult(None, False, "no_skill", None)
        return match_skill(self.list_skills(), nlu, inter_id, raw_text)

    def get_by_id(self, skill_id: str) -> SkillRecord | None:
        """Load skill by id from package directory."""
        return self._builder.load_by_id(skill_id)

    def diff_with_session(self, skill: SkillRecord, session: Session) -> SkillDiff:
        """Compare persisted skill snapshot with current session diagnosis."""
        changes: list[str] = []
        if not session.diagnosis or not session.diagnosis.matched_rules:
            return SkillDiff(has_material_diff=False, changes=[])

        new_rule_ids = [r["id"] for r in session.diagnosis.matched_rules]
        if set(new_rule_ids) != set(skill.rule_ids):
            changes.append(f"命中规则: {skill.rule_ids} → {new_rule_ids}")

        rule = session.diagnosis.matched_rules[0]
        formula = rule.get("action", {}).get("formula", "")
        if formula and formula != skill.suggestion_formula:
            changes.append("建议计算公式已变化")

        candidate_constraints = (session.nlu.user_suggestion if session.nlu else None) or ""
        if (skill.user_constraints or "") != candidate_constraints:
            changes.append(
                f"治理约束: {skill.user_constraints or '无'} → {candidate_constraints or '无'}"
            )

        quantitative = session.data_payload.get("quantitative_constraints")
        candidate_tags = build_skill_tags(
            intersection=skill.intersection,
            inter_id=skill.inter_id,
            problem_type=skill.problem_type,
            time_period_label=skill.time_period_label,
            directions=list(session.nlu.directions or []) if session.nlu else [],
            match_keywords=skill.match_keywords,
            rule_ids=new_rule_ids,
            user_constraints=candidate_constraints or None,
            quantitative_constraints=quantitative,
            suggestion_formula=formula or skill.suggestion_formula,
        )
        changes.extend(compare_content_tags(skill.tags, candidate_tags))

        deduped: list[str] = []
        seen: set[str] = set()
        for line in changes:
            if line not in seen:
                seen.add(line)
                deduped.append(line)

        return SkillDiff(has_material_diff=bool(deduped), changes=deduped)

    def build_from_session(
        self,
        session: Session,
        *,
        preserve_created_at: str | None = None,
    ) -> SkillRecord:
        """Build skill record from session without persisting."""
        assert session.nlu is not None
        assert session.diagnosis is not None
        assert session.diagnosis.matched_rules

        rule = session.diagnosis.matched_rules[0]
        skill_id = self._skill_id_for_session(session)
        time_period_dump = (
            session.nlu.time_period.model_dump() if session.nlu.time_period else {}
        )
        label = session.nlu.time_period.label if session.nlu.time_period else "unknown"
        now = datetime.now(timezone.utc).isoformat()
        match_keywords = _extract_keywords(session.raw_user_context)
        directions = list(session.nlu.directions or [])
        existing = self.get_by_id(skill_id)
        user_constraints = session.nlu.user_suggestion
        if existing:
            user_constraints = merge_user_constraints(existing.user_constraints, user_constraints)
        quantitative_constraints = session.data_payload.get("quantitative_constraints")
        flow_gov = session.data_payload.get("flow_timing_governance") or {}
        issue_codes = [
            str(p["category"])
            for p in (flow_gov.get("problems") or [])
            if p.get("detected") and p.get("category")
        ]
        data_window = (
            session.data_payload.get("meta", {}).get("data_window")
            if session.data_payload
            else None
        )
        tags = build_skill_tags(
            intersection=session.resolved_intersection or session.nlu.intersection or "",
            inter_id=session.inter_id or "",
            problem_type=session.nlu.problem_type or DEFAULT_PROBLEM_TYPE,
            time_period_label=label,
            directions=directions,
            match_keywords=match_keywords,
            rule_ids=[r["id"] for r in session.diagnosis.matched_rules],
            user_constraints=user_constraints,
            quantitative_constraints=quantitative_constraints,
            suggestion_formula=rule["action"]["formula"],
            issue_codes=issue_codes,
            data_window=data_window,
            source_utterance_summary=_summarize_context(session),
        )
        if existing and existing.tags:
            tags = merge_usage_meta(existing.tags, tags)
        return SkillRecord(
            skill_id=skill_id,
            skill_dir=skill_dir_name(session.inter_id or "", DEFAULT_PROBLEM_TYPE, label),
            intersection=session.resolved_intersection or session.nlu.intersection or "",
            inter_id=session.inter_id or "",
            problem_type=session.nlu.problem_type or DEFAULT_PROBLEM_TYPE,
            time_period_label=label,
            match_keywords=match_keywords,
            data_query_spec={
                "inter_id": session.inter_id,
                "time_period": time_period_dump,
                "problem_type": DEFAULT_PROBLEM_TYPE,
                "data_window": (
                    session.data_payload.get("meta", {}).get("data_window")
                    if session.data_payload
                    else None
                ),
            },
            rule_ids=[r["id"] for r in session.diagnosis.matched_rules],
            suggestion_formula=rule["action"]["formula"],
            created_at=preserve_created_at or now,
            updated_at=now,
            user_constraints=user_constraints,
            quantitative_constraints=quantitative_constraints,
            tags=tags,
        )

    def upsert_from_session(self, session: Session) -> SkillUpsertResult:
        """Create, update, or no-op skill package from session diagnosis."""
        candidate = self.build_from_session(session)
        existing = self.get_by_id(candidate.skill_id)

        if existing:
            merged_keywords = _merge_keywords(existing.match_keywords, candidate.match_keywords)
            candidate = SkillRecord(
                skill_id=candidate.skill_id,
                skill_dir=existing.skill_dir,
                intersection=candidate.intersection,
                inter_id=candidate.inter_id,
                problem_type=candidate.problem_type,
                time_period_label=candidate.time_period_label,
                match_keywords=merged_keywords,
                data_query_spec=candidate.data_query_spec,
                rule_ids=candidate.rule_ids,
                suggestion_formula=candidate.suggestion_formula,
                created_at=existing.created_at,
                updated_at=datetime.now(timezone.utc).isoformat(),
                user_constraints=candidate.user_constraints,
                quantitative_constraints=candidate.quantitative_constraints,
                tags=candidate.tags,
            )
            if _snapshot_equal(existing, candidate):
                return SkillUpsertResult(record=existing, action="unchanged")
            self._write_package(candidate, session)
            return SkillUpsertResult(record=candidate, action="updated")

        self._write_package(candidate, session)
        return SkillUpsertResult(record=candidate, action="created")

    async def upsert_from_session_visual(
        self,
        session: Session,
        emitter: ExecutionEmitter,
    ) -> SkillUpsertResult:
        """Persist skill package with streamed build events for the frontend."""

        candidate = self.build_from_session(session)
        existing = self.get_by_id(candidate.skill_id)
        diff = self.diff_with_session(existing, session) if existing else SkillDiff(False, [])
        snapshot_equal = bool(existing and _snapshot_equal(existing, candidate))

        if existing:
            candidate = SkillRecord(
                skill_id=candidate.skill_id,
                skill_dir=existing.skill_dir,
                intersection=candidate.intersection,
                inter_id=candidate.inter_id,
                problem_type=candidate.problem_type,
                time_period_label=candidate.time_period_label,
                match_keywords=_merge_keywords(existing.match_keywords, candidate.match_keywords),
                data_query_spec=candidate.data_query_spec,
                rule_ids=candidate.rule_ids,
                suggestion_formula=candidate.suggestion_formula,
                created_at=existing.created_at,
                updated_at=candidate.updated_at,
                user_constraints=candidate.user_constraints,
                quantitative_constraints=candidate.quantitative_constraints,
                tags=candidate.tags,
            )

        interleaved = InterleavedSkillPersistVisualizer(self, self._builder)
        report, result = await interleaved.emit(
            session=session,
            candidate=candidate,
            existing=existing,
            diff=diff,
            snapshot_equal=snapshot_equal,
            upsert_action="update" if existing else "created",
            emitter=emitter,
        )
        candidate = SkillRecord(
            skill_id=candidate.skill_id,
            skill_dir=candidate.skill_dir if not existing else existing.skill_dir,
            intersection=candidate.intersection,
            inter_id=candidate.inter_id,
            problem_type=candidate.problem_type,
            time_period_label=candidate.time_period_label,
            match_keywords=candidate.match_keywords,
            data_query_spec=candidate.data_query_spec,
            rule_ids=candidate.rule_ids,
            suggestion_formula=candidate.suggestion_formula,
            created_at=existing.created_at if existing else candidate.created_at,
            updated_at=candidate.updated_at,
            user_constraints=candidate.user_constraints,
            quantitative_constraints=candidate.quantitative_constraints,
            tags=merge_usage_meta(existing.tags if existing else None, report.tags),
        )

        if result.action == "unchanged":
            return result

        if existing:
            merged_keywords = _merge_keywords(existing.match_keywords, candidate.match_keywords)
            candidate.match_keywords = merged_keywords

        return result

    def package_zip(self, skill_id: str) -> tuple[bytes, str]:
        """Return zip bytes and filename for a skill package."""
        record = self.get_by_id(skill_id)
        if not record:
            raise FileNotFoundError(skill_id)
        return self._builder.package_zip(record), f"{record.skill_dir}.zip"

    def create_from_session(self, session: Session) -> SkillRecord:
        """Persist skill from completed diagnosis session."""
        return self.upsert_from_session(session).record

    @staticmethod
    def _skill_id_for_session(session: Session) -> str:
        """Deterministic skill primary key for session."""
        assert session.nlu is not None
        label = session.nlu.time_period.label if session.nlu.time_period else "unknown"
        return f"skill_{session.inter_id}_{DEFAULT_PROBLEM_TYPE}_{label}"

    def list_skills(self, intersection: str | None = None) -> list[SkillRecord]:
        """List all skills from package directories."""
        records = self._builder.load_all()
        if intersection:
            records = [r for r in records if intersection in r.intersection]
        return records

    def list_leaderboard(
        self,
        *,
        sort: str = "hits",
        intersection: str | None = None,
    ) -> list[SkillRecord]:
        """List skills ordered for leaderboard display."""
        records = self.list_skills(intersection)
        if sort == "created":
            records.sort(key=lambda r: r.created_at, reverse=True)
        elif sort == "updated":
            records.sort(key=lambda r: r.updated_at or r.created_at, reverse=True)
        else:
            records.sort(
                key=lambda r: (read_hit_count(r.tags), r.created_at),
                reverse=True,
            )
        return records

    def record_hit(self, skill_id: str) -> int | None:
        """Increment reuse counter when a skill is matched on the fast path."""
        record = self.get_by_id(skill_id)
        if not record:
            return None
        tags = increment_usage_meta(record.tags)
        updated = SkillRecord(
            skill_id=record.skill_id,
            skill_dir=record.skill_dir,
            intersection=record.intersection,
            inter_id=record.inter_id,
            problem_type=record.problem_type,
            time_period_label=record.time_period_label,
            match_keywords=record.match_keywords,
            data_query_spec=record.data_query_spec,
            rule_ids=record.rule_ids,
            suggestion_formula=record.suggestion_formula,
            created_at=record.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
            user_constraints=record.user_constraints,
            quantitative_constraints=record.quantitative_constraints,
            tags=tags,
        )
        files = self._builder.build_file_contents(updated, session=None)
        self._builder.write_package_files(updated, files)
        count = read_hit_count(tags)
        logger.info("skill.hit_recorded skill_id=%s hit_count=%s", skill_id, count)
        return count

    def _write_package(self, record: SkillRecord, session: Session) -> None:
        """Write standard skill package to disk."""
        pkg_path = self._builder.write_package(record, session)
        logger.info("skill.created path=%s", pkg_path)


def _summarize_context(session: Session) -> str:
    from intersection_agent.skills.tag_helpers import summarize_utterance

    return summarize_utterance(session.raw_user_context or session.user_messages_text())


def _extract_keywords(text: str) -> list[str]:
    """Extract simple keywords from user input."""
    keywords: list[str] = []
    for token in ("拥堵", "堵车", "排队", "晚高峰", "早高峰", "平峰", "南北向"):
        if token in text:
            keywords.append(token)
    return keywords


def _merge_keywords(existing: list[str], new: list[str]) -> list[str]:
    """Merge keyword lists preserving order."""
    seen: set[str] = set()
    merged: list[str] = []
    for kw in existing + new:
        if kw not in seen:
            seen.add(kw)
            merged.append(kw)
    return merged


def _snapshot_equal(left: SkillRecord, right: SkillRecord) -> bool:
    """Whether two skill snapshots are materially identical."""
    return (
        left.rule_ids == right.rule_ids
        and left.suggestion_formula == right.suggestion_formula
        and left.user_constraints == right.user_constraints
        and left.quantitative_constraints == right.quantitative_constraints
        and left.data_query_spec == right.data_query_spec
        and left.match_keywords == right.match_keywords
        and _tags_materially_equal(left.tags, right.tags)
    )


def _tags_materially_equal(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> bool:
    """Compare tag layers excluding volatile meta timestamps and library counters."""
    if left == right:
        return True
    if not left or not right:
        return left == right

    def _strip_volatile(tags: dict[str, Any]) -> dict[str, Any]:
        copied = dict(tags)
        meta = dict(copied.get("meta") or {})
        for key in (
            "absorbed_at",
            "library_count_before",
            "library_count_after",
            "hit_count",
            "last_hit_at",
        ):
            meta.pop(key, None)
        copied["meta"] = meta
        return copied

    return (
        (left.get("match") or {}) == (right.get("match") or {})
        and (left.get("content") or {}) == (right.get("content") or {})
        and _strip_volatile(left).get("meta") == _strip_volatile(right).get("meta")
    )
