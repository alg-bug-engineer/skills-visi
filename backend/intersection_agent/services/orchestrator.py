"""Conversation orchestrator — state machine driver."""

from __future__ import annotations

import logging
import re
from typing import Any

from intersection_agent.hooks.execution_emitter import ExecutionEmitter
from intersection_agent.logging.helpers import log_event, safe_preview
from intersection_agent.models.domain import (
    DiagnosisResult,
    MessageRecord,
    NluResult,
    ReplyType,
    Session,
    SessionState,
    SuggestionResult,
    TimePeriod,
)
from intersection_agent.services.data_fetcher import DataFetcher
from intersection_agent.services.flow_timing_governance_service import FlowTimingGovernanceService
from intersection_agent.services.follow_up_service import FollowUpService
from intersection_agent.services.expert_rules_summary import format_expert_rules_markdown
from intersection_agent.services.intent_detector import detect_confirmation_intent
from intersection_agent.services.intersection_cognition_service import (
    IntersectionCognitionService,
    _build_direction_groups,
    fill_arm_metrics_from_overall,
)
from intersection_agent.utils.turn_metrics import attach_turn_metrics_to_cognition
from intersection_agent.utils.saturation_granularity import apply_canonical_saturation_to_payload
from intersection_agent.services.intersection_resolver import IntersectionResolver
from intersection_agent.services.map_presentation_service import (
    build_links_narration_payload,
    build_map_scene,
    build_narration_steps,
    build_understanding_card,
    enrich_narration_step,
    pick_narration_step,
)
from intersection_agent.services.case_library_service import CaseLibraryService
from intersection_agent.services.dimension_pack_service import DimensionPackService
from intersection_agent.services.experience_reuse_service import ExperienceReuseService
from intersection_agent.services.experience_classifier import ExperienceClassifier
from intersection_agent.stores.intersection_profile_store import IntersectionProfileStore
from intersection_agent.stores.intersection_case_store import (
    IntersectionCaseRecord,
    IntersectionCaseStore,
)
from intersection_agent.services.nlu_service import NluService, extract_user_suggestion_text
from intersection_agent.services.rule_engine import RuleEngine, evaluate_formula
from intersection_agent.services.skill_service import SkillService, SkillUpsertResult
from intersection_agent.services.skill_matcher import backfill_tags
from intersection_agent.config import get_settings
from intersection_agent.services.constraint_resolver_service import ConstraintResolverService
from intersection_agent.services.context_tags_service import ContextTagsService
from intersection_agent.services.intent_classifier_service import IntentClassifierService
from intersection_agent.services.problem_evidence_service import ProblemEvidenceService
from intersection_agent.services.suggestion_service import SuggestionService
from intersection_agent.services.suggestion_context import (
    compose_monitoring_feedback_narrative,
    derive_suggestion_references,
    is_healthy_monitoring_case,
    prepare_suggestion_data,
)
from intersection_agent.services.user_constraint_merge import merge_user_constraints
from intersection_agent.services.sustained_metrics_service import SustainedMetricsService
from intersection_agent.services.timing_profile_service import TimingProfileService
from intersection_agent.services.upstream_governance_trace_service import (
    UpstreamGovernanceTraceService,
)
from intersection_agent.utils.thresholds_loader import threshold_value
from intersection_agent.utils.traffic_labels import DIR8_LABELS
from intersection_agent.utils.terminal_report import (
    format_evidence_report,
    format_evidence_summary_markdown,
)
from intersection_agent.utils.demo_config import demo_meta_for_intersection, is_demo_mode

logger = logging.getLogger(__name__)

# 长方位标签优先匹配（"东北" 先于 "东"），用于 by_turn label 缺 dir8_code 时回退。
_DIR8_BY_LABEL = sorted(
    ((name, code) for code, name in DIR8_LABELS.items()),
    key=lambda kv: len(kv[0]),
    reverse=True,
)


_PROBLEM_LABELS: dict[str, str] = {
    "congestion": "拥堵",
    "spillover": "溢出",
    "queue": "排队",
    "delay": "延误",
}


def _compose_cognition_text(nlu: "NluResult | None") -> str:
    """从 NLU 结构化字段兜底拼装认知画像文本：时段 + 方向 + 问题（路口名见卡头）。"""
    if nlu is None:
        return ""
    parts: list[str] = []
    if nlu.time_period and nlu.time_period.label:
        parts.append(nlu.time_period.label)
    if nlu.directions:
        parts.append("".join(nlu.directions) + "向")
    parts.append(_PROBLEM_LABELS.get(nlu.problem_type or "congestion", "拥堵"))
    return "".join(parts)


_DIRECTION_DIR8: dict[str, tuple[int, ...]] = {
    "南北向": (0, 4),
    "南北": (0, 4),
    "东西向": (2, 6),
    "东西": (2, 6),
}


def _dir8s_from_directions(
    directions: list[str] | None, available: set[int]
) -> list[int]:
    """NLU 方向 → dir8：「南北向」展开为北(0)+南(4)，「X进口」取单向；仅保留实际有数据的进口。"""
    out: set[int] = set()
    for raw in directions or []:
        token = str(raw).strip()
        if token in _DIRECTION_DIR8:
            out.update(_DIRECTION_DIR8[token])
            continue
        for code, label in DIR8_LABELS.items():
            if token.startswith(label):
                out.add(code)
                break
    return [d for d in out if d in available]


_TURN_HINTS = ("左", "直", "右", "调", "掉头")


def _turn_specific_dir8s(
    directions: list[str] | None, available: set[int]
) -> list[int]:
    """含转向语义的方向（如「西左转」）→ 仅对应进口，避免把附带提及的其它进口一并溯源。"""
    out: set[int] = set()
    for raw in directions or []:
        token = str(raw).strip()
        if not any(h in token for h in _TURN_HINTS):
            continue
        for code, label in DIR8_LABELS.items():
            if token.startswith(label):
                out.add(code)
                break
    return [d for d in sorted(out) if d in available]


def _row_dir8(row: dict[str, Any]) -> int | None:
    """从 by_turn 行解析进口道 dir8：优先 dir8_code，否则按 label 首方位回退。"""
    d8 = row.get("dir8_code")
    if d8 is not None:
        return int(d8)
    label = str(row.get("label") or "")
    for name, code in _DIR8_BY_LABEL:
        if label.startswith(name):
            return code
    return None


class Orchestrator:
    """Drive session state transitions for each user message."""

    def __init__(
        self,
        nlu: NluService | None = None,
        resolver: IntersectionResolver | None = None,
        fetcher: DataFetcher | None = None,
        cognition: IntersectionCognitionService | None = None,
        rules: RuleEngine | None = None,
        suggestions: SuggestionService | None = None,
        skills: SkillService | None = None,
        follow_ups: FollowUpService | None = None,
        evidence: ProblemEvidenceService | None = None,
        constraints: ConstraintResolverService | None = None,
        timing: TimingProfileService | None = None,
        intent_classifier: IntentClassifierService | None = None,
        context_tags: ContextTagsService | None = None,
        flow_governance: FlowTimingGovernanceService | None = None,
        sustained: SustainedMetricsService | None = None,
        profile_store: IntersectionProfileStore | None = None,
        case_store: IntersectionCaseStore | None = None,
        upstream_trace: UpstreamGovernanceTraceService | None = None,
        experience_classifier: ExperienceClassifier | None = None,
    ) -> None:
        self._nlu = nlu or NluService()
        self._resolver = resolver or IntersectionResolver()
        self._fetcher = fetcher or DataFetcher()
        self._cognition = cognition or IntersectionCognitionService()
        self._rules = rules or RuleEngine()
        self._dimension_packs = DimensionPackService()
        self._suggestions = suggestions or SuggestionService()
        self._skills = skills or SkillService()
        self._follow_ups = follow_ups or FollowUpService()
        self._evidence = evidence or ProblemEvidenceService()
        self._constraints = constraints or ConstraintResolverService()
        self._timing = timing or TimingProfileService()
        self._intent_classifier = intent_classifier or IntentClassifierService()
        self._context_tags = context_tags or ContextTagsService()
        self._flow_governance = flow_governance or FlowTimingGovernanceService(rules=self._rules)
        self._sustained = sustained or SustainedMetricsService()
        self._profile_store = profile_store or IntersectionProfileStore()
        self._case_store = case_store or IntersectionCaseStore()
        self._experience_reuse = ExperienceReuseService(self._profile_store)
        self._case_library = CaseLibraryService()
        self._upstream_trace = upstream_trace or UpstreamGovernanceTraceService()
        self._experience_classifier = experience_classifier or ExperienceClassifier()
        self._settings = get_settings()

    async def handle_message(
        self,
        session: Session,
        content: str,
        emitter: ExecutionEmitter | None = None,
    ) -> dict[str, Any]:
        """Process user message and return API response payload."""
        session.messages.append(MessageRecord(role="user", content=content))
        session.raw_user_context = session.user_messages_text()
        log_event(
            logger,
            logging.INFO,
            "orchestrator.start",
            session_id=session.session_id,
            state=session.state.value,
            input=safe_preview(content),
        )
        if emitter:
            await emitter.emit(
                "orchestrator.start",
                "running",
                data={"state": session.state.value, "input_preview": safe_preview(content)},
            )

        if session.state == SessionState.AWAITING_CONFIRM:
            return await self._handle_confirmation(session, content, emitter)

        if session.state == SessionState.INTERSECTION_AMBIGUOUS:
            return await self._handle_candidate_pick(session, content, emitter)

        if session.state == SessionState.NLU_INCOMPLETE:
            return await self._continue_nlu(session, emitter)

        if session.state in (SessionState.IDLE, SessionState.DONE):
            session.state = SessionState.PROCESSING

        return await self._run_pipeline(session, emitter)

    async def _record_problem_experience(
        self,
        session: Session,
        diagnosis: DiagnosisResult,
        governance: dict[str, Any] | None,
        emitter: ExecutionEmitter | None = None,
    ) -> None:
        """三类经验沉淀（大模型理解用户原话归类）：

        - 认知画像 cognition：问题记录（路口/方向/时段拥堵）。数据支撑→verified，否则→data_doubt(待验证)。
        - 诊断经验 diagnosis：用户口述、库内通常无记录的原因（如"附近学校放学"）。
        - 方案诊断经验 solution：用户给出的治理经验（对向不溢出、绿灯±x 秒、加左转车道）。

        严格栅栏：每步先落库，再 emit 对应 step_conclusion。
        """
        inter_id = session.inter_id
        if not inter_id:
            return
        nlu = session.nlu

        raw_text = session.raw_user_context or session.user_messages_text()
        classified = await self._experience_classifier.classify(raw_text)

        # 认知画像：问题记录 = 路口/方向/时段拥堵；数据支撑→verified，否则→data_doubt(待验证)
        verified = bool(diagnosis.diagnosed and diagnosis.matched_rules)
        cognition_text = classified.get("problem") or _compose_cognition_text(nlu)
        if cognition_text:
            status = "verified" if verified else "data_doubt"
            _, cognition_action = self._profile_store.add_cognition(
                inter_id,
                text=cognition_text,
                status=status,
                source="data" if verified else "user",
                evidence=(diagnosis.metrics_snapshot or {}) if verified else {},
            )
            if emitter:
                await emitter.emit(
                    "experience_cognition",
                    "completed",
                    data={
                        "inter_id": inter_id,
                        "text": cognition_text,
                        "status": status,
                        "action": cognition_action,
                        "tags": [
                            "认知画像",
                            "问题记录",
                            "已验证" if status == "verified" else "待验证",
                        ],
                    },
                )

        # 诊断经验：用户口述、库内通常无记录的原因
        for cause in classified.get("causes") or []:
            _, diagnosis_action = self._profile_store.add_diagnosis(
                inter_id,
                cause=cause,
                dimension="user_observation",
                source="user",
                confidence=0.0,
            )
            if emitter:
                await emitter.emit(
                    "experience_diagnosis",
                    "completed",
                    data={
                        "inter_id": inter_id,
                        "cause": cause,
                        "dimension": "user_observation",
                        "action": diagnosis_action,
                        "tags": ["诊断经验", "用户口述", "用户观察"],
                    },
                )

        # 方案诊断经验：用户口述措施仅 emit 事件，不写入案例库（案例须生成方案后显式落盘）

    async def _record_solution_ref(
        self,
        session: Session,
        result: SkillUpsertResult,
        emitter: ExecutionEmitter | None = None,
    ) -> None:
        """出方案步：skill 固化后在档案追加 solution_ref，并显式写入 data/cases/。"""
        inter_id = session.inter_id
        if not inter_id or not result or not result.record:
            return
        if not session.suggestion or not (session.suggestion.narrative or "").strip():
            return
        record = result.record
        qualitative = (session.nlu.user_suggestion if session.nlu else None) or (
            record.user_constraints
        )
        _, solution_action = self._profile_store.add_solution_ref(
            inter_id,
            skill_id=record.skill_id,
            qualitative=qualitative,
            quantified=record.suggestion_formula or None,
        )
        profile = self._profile_store.load(inter_id)
        self._case_store.save(
            IntersectionCaseRecord(
                skill_id=record.skill_id,
                inter_id=inter_id,
                intersection=record.intersection,
                time_period_label=record.time_period_label,
                suggestion_narrative=session.suggestion.narrative,
                suggestion_formula=record.suggestion_formula or "",
                solution_measure=record.solution_measure,
                qualitative=qualitative,
                cognition=list(profile.cognition),
                diagnosis=list(profile.diagnosis),
            )
        )
        if emitter:
            await emitter.emit(
                "experience_solution",
                "completed",
                data={
                    "inter_id": inter_id,
                    "skill_id": record.skill_id,
                    "quantified": record.suggestion_formula or None,
                    "action": solution_action,
                },
            )

    async def _handle_confirmation(
        self,
        session: Session,
        content: str,
        emitter: ExecutionEmitter | None,
    ) -> dict[str, Any]:
        """Handle yes/no after diagnosis."""
        if session.pending_suggestion_action == "generate":
            return await self._handle_suggestion_confirmation(session, content, emitter)

        if emitter:
            await emitter.emit("confirm_intent", "running", data={"input": safe_preview(content)})
        intent = detect_confirmation_intent(content)
        log_event(logger, logging.INFO, "orchestrator.confirm_intent", intent=intent)
        if emitter:
            await emitter.emit("confirm_intent", "completed", data={"intent": intent})
        if intent == "confirm":
            if emitter:
                await emitter.emit("skill_create", "running")
                result = await self._skills.upsert_from_session_visual(session, emitter)
            else:
                result = self._skills.upsert_from_session(session)
            await self._record_solution_ref(session, result, emitter)
            session.state = SessionState.DONE
            action = session.pending_skill_action or "create"
            log_event(
                logger,
                logging.INFO,
                "skill.persisted",
                skill_id=result.record.skill_id,
                persist_action=result.action,
                confirm_action=action,
            )
            if emitter:
                await emitter.emit(
                    "skill_create",
                    "completed",
                    data={"skill_id": result.record.skill_id, "action": result.action},
                )
            return self._finalize_skill_confirm(session, result, action)

        if intent == "deny":
            session.state = SessionState.DONE
            if session.pending_skill_action == "update":
                return self._build_response(
                    session,
                    ReplyType.TEXT,
                    "好的，本次结论仅供参考，未修改 Skill。",
                    extra={"skill_action": "declined_update"},
                )
            return self._build_response(
                session,
                ReplyType.TEXT,
                "好的，本次分析未固化。如需再次诊断，请重新描述问题。",
                extra={"skill_action": "declined_create"},
            )

        follow_up = await self._follow_ups.for_skill_confirm(
            session.raw_user_context,
            action=session.pending_skill_action or "create",
        )
        return self._build_response(session, ReplyType.FOLLOW_UP, follow_up)

    async def _handle_suggestion_confirmation(
        self,
        session: Session,
        content: str,
        emitter: ExecutionEmitter | None,
    ) -> dict[str, Any]:
        """Handle confirmation before generating governance suggestions."""
        assert session.nlu is not None
        suggestion_text = extract_user_suggestion_text(content)
        intent = "confirm" if suggestion_text else detect_confirmation_intent(content)
        if emitter:
            await emitter.emit(
                "confirm_intent",
                "completed",
                data={
                    "intent": intent,
                    "user_suggestion": safe_preview(suggestion_text),
                },
            )
        log_event(
            logger,
            logging.INFO,
            "orchestrator.suggestion_confirm_intent",
            intent=intent,
            user_suggestion=suggestion_text,
        )

        if intent == "deny":
            session.pending_suggestion_action = None
            session.state = SessionState.DONE
            return self._build_response(
                session,
                ReplyType.TEXT,
                "好的，本次已确认问题存在，但未生成治理建议。如需继续，可重新发起诊断。",
                extra={"suggestion_action": "declined"},
            )

        if intent != "confirm":
            return self._build_response(
                session,
                ReplyType.FOLLOW_UP,
                "是否需要我基于本次诊断生成治理建议？可以回复「是」，也可以直接补充约束或建议。",
                extra={"suggestion_action": "awaiting_generate"},
            )

        session.pending_suggestion_action = None
        if suggestion_text:
            base = self._base_user_suggestion_for_merge(session)
            merged = merge_user_constraints(base, suggestion_text)
            session.nlu.user_suggestion = merged
            problem_evidence = session.data_payload.get("problem_evidence")
            quantitative_constraints = self._constraints.resolve(
                merged or suggestion_text,
                nlu_directions=session.nlu.directions,
                problem_evidence=problem_evidence,
            )
            if quantitative_constraints:
                session.data_payload["quantitative_constraints"] = quantitative_constraints
                self._log_evidence_debug(problem_evidence, quantitative_constraints)

        content = await self._generate_suggestion_content(session, emitter=emitter)
        if session.skill_reuse_mode:
            session.skill_reuse_mode = False
            if suggestion_text:
                return await self._await_skill_create_confirmation(
                    session,
                    content,
                    emitter=emitter,
                    suggestion_action="generated_with_user_suggestion",
                )
            session.state = SessionState.DONE
            return self._build_response(
                session,
                ReplyType.DIAGNOSIS,
                content,
                extra={
                    "suggestion_action": "generated",
                    "skill_action": "reused_no_persist",
                    "skill_reused": True,
                },
            )

        if suggestion_text:
            return await self._await_skill_create_confirmation(
                session,
                content,
                emitter=emitter,
                suggestion_action="generated_with_user_suggestion",
            )

        session.state = SessionState.DONE
        return self._build_response(
            session,
            ReplyType.DIAGNOSIS,
            content,
            extra={
                "suggestion_action": "generated",
                "skill_action": "skipped_no_user_suggestion",
            },
        )

    async def _handle_candidate_pick(
        self,
        session: Session,
        content: str,
        emitter: ExecutionEmitter | None,
    ) -> dict[str, Any]:
        """Resolve user selection from intersection candidates."""
        if emitter:
            await emitter.emit(
                "intersection",
                "running",
                data={"mode": "candidate_pick", "input": safe_preview(content)},
            )
        result = await self._resolver.resolve_candidate_selection(
            content, session.intersection_candidates
        )
        if result and result.inter_id:
            session.inter_id = result.inter_id
            session.resolved_intersection = result.inter_name
            session.resolution_source = result.source
            session.state = SessionState.PROCESSING
            if emitter:
                await emitter.emit(
                    "intersection",
                    "completed",
                    data={
                        "inter_id": result.inter_id,
                        "inter_name": result.inter_name,
                        "source": result.source,
                    },
                )
            return await self._diagnose(
                session,
                resolution_note=f"已匹配为：{result.inter_name}",
                emitter=emitter,
            )

        session.state = SessionState.PROCESSING
        return await self._run_pipeline(session, emitter)

    @staticmethod
    def _merge_preserved_nlu(session: Session, nlu_result: dict[str, Any]) -> dict[str, Any]:
        preserved = session.nlu
        if not preserved or nlu_result.get("status") not in ("complete", "incomplete"):
            return nlu_result
        data = nlu_result.get("data")
        if data is None:
            return nlu_result
        if preserved.intersection and not data.intersection:
            data.intersection = preserved.intersection
        if preserved.time_period and not data.time_period:
            data.time_period = preserved.time_period
        nlu_result["data"] = data
        if nlu_result["status"] == "incomplete":
            missing = []
            if not data.intersection:
                missing.append("intersection")
            if not data.time_period:
                missing.append("time_period")
            if not data.directions:
                missing.append("directions")
            nlu_result["missing"] = missing
            if not missing:
                nlu_result["status"] = "complete"
        return nlu_result

    async def _continue_nlu(
        self,
        session: Session,
        emitter: ExecutionEmitter | None,
    ) -> dict[str, Any]:
        """Continue NLU completion flow with merged user context."""
        session.state = SessionState.PROCESSING
        return await self._run_pipeline(session, emitter)

    async def _run_pipeline(
        self,
        session: Session,
        emitter: ExecutionEmitter | None,
    ) -> dict[str, Any]:
        """Full pipeline with optional skill fast path."""
        if emitter:
            await emitter.emit(
                "nlu",
                "running",
                data={"context_preview": safe_preview(session.raw_user_context)},
            )
        nlu_result = await self._nlu.extract(session.raw_user_context)
        nlu_result = self._merge_preserved_nlu(session, nlu_result)
        if nlu_result.get("status") == "error":
            log_event(logger, logging.WARNING, "nlu.error", error=nlu_result.get("error"))
            if emitter:
                await emitter.emit(
                    "nlu",
                    "failed",
                    data={"error": nlu_result.get("error", "理解失败")},
                )
            session.state = SessionState.DONE
            return self._build_response(
                session, ReplyType.ERROR, nlu_result.get("error", "理解失败")
            )

        if nlu_result["status"] == "incomplete":
            session.nlu = nlu_result["data"]
            session.state = SessionState.NLU_INCOMPLETE
            session.pending_follow_up_field = nlu_result.get("follow_up_field")
            log_event(
                logger,
                logging.INFO,
                "nlu.incomplete",
                missing=nlu_result.get("missing"),
                follow_up_field=nlu_result.get("follow_up_field"),
            )
            if emitter:
                await emitter.emit(
                    "nlu",
                    "completed",
                    data={
                        "status": "incomplete",
                        "missing": nlu_result.get("missing", []),
                        "partial": session.nlu.model_dump() if session.nlu else None,
                        "follow_up_field": nlu_result.get("follow_up_field"),
                    },
                )
            return self._build_response(
                session,
                ReplyType.FOLLOW_UP,
                nlu_result.get("follow_up", "请补充信息"),
                extra={"missing_fields": nlu_result.get("missing", [])},
            )

        session.nlu = nlu_result["data"]
        if emitter:
            await emitter.emit(
                "nlu",
                "completed",
                data={"status": "complete", "nlu": session.nlu.model_dump()},
            )
            await self._emit_map_sequence(
                emitter,
                action="input_dock",
                data={"phase": "engage", "locked": True},
            )
        return await self._run_nlu(session, emitter)

    async def _run_nlu(
        self,
        session: Session,
        emitter: ExecutionEmitter | None,
    ) -> dict[str, Any]:
        """NLU complete — resolve intersection and diagnose."""
        assert session.nlu is not None

        if emitter:
            await emitter.emit("skill_match", "running")
        prelim = await self._resolver.resolve_with_context(
            session.nlu.intersection or "",
            session.raw_user_context,
        )
        inter_id = prelim.inter_id if prelim.inter_id else None
        match_result = self._skills.find_match_result(
            session.nlu, inter_id, session.raw_user_context
        )
        if match_result.matched and match_result.skill:
            skill = match_result.skill
            session.matched_skill_id = skill.skill_id
            session.skill_reuse_mode = True
            hit_count = self._skills.record_hit(skill.skill_id)
            session.inter_id = skill.inter_id
            session.resolved_intersection = skill.intersection
            session.resolution_source = "skill_fast_path"
            log_event(
                logger,
                logging.INFO,
                "skill.fast_path",
                skill_id=skill.skill_id,
                reason=match_result.reason,
            )
            if emitter:
                await emitter.emit(
                    "skill_match",
                    "completed",
                    data={
                        "matched": True,
                        "skill_id": skill.skill_id,
                        "reason": match_result.reason,
                        "reuse_notice": match_result.detail,
                        "tags": backfill_tags(skill),
                        "hit_count": hit_count,
                    },
                )
                await emitter.emit(
                    "intersection",
                    "completed",
                    data={
                        "inter_id": session.inter_id,
                        "inter_name": session.resolved_intersection,
                        "source": "skill_fast_path",
                    },
                )
                await self._emit_map_sequence(
                    emitter,
                    action="show_understanding",
                    data=build_understanding_card(
                        session.nlu,
                        resolved_name=session.resolved_intersection,
                        resolution_source="skill_fast_path",
                    ),
                )
            return await self._diagnose(
                session,
                skill_rule_ids=skill.rule_ids,
                skill_reuse_notice=match_result.detail,
                emitter=emitter,
            )

        if match_result.reason == "constraint_mismatch":
            log_event(
                logger,
                logging.INFO,
                "skill.constraint_mismatch",
                detail=match_result.detail,
                skill_id=match_result.skill.skill_id if match_result.skill else None,
            )
            if emitter:
                await emitter.emit(
                    "skill_match",
                    "completed",
                    data={
                        "matched": False,
                        "reason": match_result.reason,
                        "reuse_notice": match_result.detail,
                        "skill_id": match_result.skill.skill_id if match_result.skill else None,
                    },
                )
        elif emitter:
            await emitter.emit(
                "skill_match",
                "completed",
                data={"matched": False, "reason": match_result.reason},
            )

        if emitter:
            await emitter.emit(
                "intersection",
                "running",
                data={"input": session.nlu.intersection},
            )
        resolution = await self._resolver.resolve_with_context(
            session.nlu.intersection or "",
            session.raw_user_context,
        )
        log_event(
            logger,
            logging.INFO,
            "intersection.resolved",
            input=session.nlu.intersection,
            source=resolution.source,
            inter_id=resolution.inter_id,
            inter_name=resolution.inter_name,
        )
        if resolution.inter_id:
            session.inter_id = resolution.inter_id
            session.resolved_intersection = resolution.inter_name
            session.resolution_source = resolution.source
            if emitter:
                await emitter.emit(
                    "intersection",
                    "completed",
                    data={
                        "inter_id": resolution.inter_id,
                        "inter_name": resolution.inter_name,
                        "source": resolution.source,
                    },
                )
                await self._emit_map_sequence(
                    emitter,
                    action="show_understanding",
                    data=build_understanding_card(
                        session.nlu,
                        resolved_name=resolution.inter_name,
                        resolution_source=resolution.source,
                    ),
                )
            note = ""
            if resolution.source == "variant":
                note = f"已自动匹配为：{resolution.inter_name}"
            return await self._diagnose(session, resolution_note=note, emitter=emitter)

        if resolution.candidates:
            session.state = SessionState.INTERSECTION_AMBIGUOUS
            session.intersection_candidates = resolution.candidates
            if emitter:
                await emitter.emit(
                    "intersection",
                    "completed",
                    data={
                        "status": "ambiguous",
                        "candidates": resolution.candidates,
                    },
                )
            follow_up = await self._follow_ups.for_intersection_candidates(
                session.raw_user_context,
                input_name=session.nlu.intersection or "",
                candidates=resolution.candidates,
            )
            return self._build_response(
                session,
                ReplyType.FOLLOW_UP,
                follow_up,
                extra={"candidates": resolution.candidates},
            )

        if emitter:
            await emitter.emit(
                "intersection",
                "failed",
                data={"status": "not_found"},
            )
        session.state = SessionState.DONE
        follow_up = await self._follow_ups.for_intersection_not_found(
            session.raw_user_context,
            input_name=session.nlu.intersection or "",
        )
        return self._build_response(session, ReplyType.ERROR, follow_up)

    async def _diagnose(
        self,
        session: Session,
        resolution_note: str = "",
        skill_rule_ids: list[str] | None = None,
        skill_reuse_notice: str | None = None,
        emitter: ExecutionEmitter | None = None,
    ) -> dict[str, Any]:
        """Fetch data, run rules, generate suggestion."""
        assert session.nlu is not None
        assert session.inter_id is not None
        assert session.resolved_intersection is not None

        cognition: dict[str, Any] = {}
        if emitter:
            await emitter.emit(
                "intersection_cognition",
                "running",
                data={"inter_id": session.inter_id},
            )
        cognition = await self._cognition.fetch(
            session.inter_id,
            session.resolved_intersection,
            session.nlu,
        )
        session.data_payload["cognition"] = cognition
        if emitter:
            await emitter.emit(
                "intersection_cognition",
                "completed",
                data={"cognition": cognition},
            )
            await self._emit_map_sequence(
                emitter,
                action="fly_to_intersection",
                data={
                    "city": cognition.get("city"),
                    "intersection": cognition.get("intersection"),
                },
            )
            if cognition.get("links") or cognition.get("arms"):
                await self._emit_map_sequence(
                    emitter,
                    action="highlight_links",
                    data={
                        "intersection": cognition.get("intersection"),
                        "links": cognition.get("links") or [],
                        "arms": cognition.get("arms") or [],
                    },
                )
                link_step = build_links_narration_payload(cognition)
                await self._emit_map_sequence(
                    emitter, action="narration", data={**link_step, "index": 0, "total": 6}
                )

        if emitter:
            await emitter.emit(
                "data_fetch",
                "running",
                data={"inter_id": session.inter_id, "intersection": session.resolved_intersection},
            )
        data = await self._fetcher.fetch(
            session.inter_id,
            session.resolved_intersection,
            session.nlu,
        )
        data["meta"] = {
            **(data.get("meta") or {}),
            **demo_meta_for_intersection(session.inter_id),
            "demo_mode": is_demo_mode() or self._settings.demo_mode,
        }
        session.data_payload = {**session.data_payload, **data}
        apply_canonical_saturation_to_payload(session.data_payload)

        timing_profile = await self._timing.build(
            session.inter_id,
            session.nlu,
            data_payload=session.data_payload,
        )
        corridor_context = {
            "in_corridor": False,
            "corridor_name": None,
            "corridor_nodes": [],
            "narrative": "",
        }
        external_evidence = {
            "has_external_evidence": False,
            "complaint_total": 0,
            "complaints": [],
            "narrative": "",
        }
        flow_green = timing_profile.get("flow_green_fit") or {}
        session.data_payload["timing_profile"] = timing_profile
        session.data_payload["timing"] = {
            "cycle_length": timing_profile.get("cycle_length"),
            "cycle_issue": timing_profile.get("cycle_issue"),
            "plan_granularity_low": timing_profile.get("plan_granularity_low"),
            "green_deficit_ratio_max": timing_profile.get("green_deficit_ratio_max"),
            "flow_green_verdict": flow_green.get("verdict"),
            "flow_green_tau": flow_green.get("spearman_tau"),
        }
        session.data_payload["corridor"] = {
            "in_corridor": corridor_context.get("in_corridor"),
            "corridor_name": corridor_context.get("corridor_name"),
            "green_wave_break_risk": corridor_context.get("green_wave_break_risk"),
            "avg_coord_stop_times": corridor_context.get("avg_coord_stop_times"),
        }
        session.data_payload["corridor_context"] = corridor_context
        session.data_payload["external_evidence"] = external_evidence
        data = session.data_payload
        log_event(
            logger,
            logging.INFO,
            "data.fetched",
            inter_id=session.inter_id,
            missing_dws=data.get("meta", {}).get("missing_dws_coverage"),
            metrics=data.get("evaluation"),
        )
        if emitter:
            await emitter.emit(
                "data_fetch",
                "completed",
                data={
                    "metrics": data.get("evaluation"),
                    "traffic_flow": data.get("traffic_flow"),
                    "granularity": data.get("granularity"),
                    "timing_profile": timing_profile,
                    "corridor_context": corridor_context,
                    "external_evidence": external_evidence,
                    "missing_dws": data.get("meta", {}).get("missing_dws_coverage"),
                    "data_window": data.get("meta", {}).get("data_window"),
                },
            )
            merged_metrics = cognition.get("metrics_by_arm") or []
            overall_sat = (data.get("traffic_flow") or {}).get("saturation_rate")
            if not merged_metrics and overall_sat is not None:
                for arm in cognition.get("arms") or []:
                    merged_metrics.append(
                        {
                            "link_id": arm["link_id"],
                            "dir4_label": arm.get("dir4_label", ""),
                            "saturation": overall_sat,
                            "level": (
                                "high"
                                if overall_sat >= 0.85
                                else "medium"
                                if overall_sat >= 0.65
                                else "low"
                            ),
                        }
                    )
            elif overall_sat is not None:
                merged_metrics = fill_arm_metrics_from_overall(
                    cognition.get("arms") or [],
                    merged_metrics,
                    float(overall_sat),
                )
            cognition["metrics_by_arm"] = merged_metrics
            metrics_by_turn = attach_turn_metrics_to_cognition(cognition, data)
            merged_metrics = cognition.get("metrics_by_arm") or merged_metrics
            apply_canonical_saturation_to_payload(session.data_payload)
            if not metrics_by_turn:
                cognition["direction_groups"] = _build_direction_groups(
                    cognition.get("arms") or [], merged_metrics
                )
            session.data_payload["cognition"] = cognition
            await self._emit_map_sequence(
                emitter,
                action="update_metrics",
                data={
                    "metrics_by_arm": merged_metrics,
                    "metrics_by_turn": metrics_by_turn,
                    "direction_groups": cognition.get("direction_groups"),
                    "evaluation": data.get("evaluation"),
                    "traffic_flow": data.get("traffic_flow"),
                    "show_metrics": True,
                },
            )
            all_steps = build_narration_steps(cognition=cognition, data=data, nlu=session.nlu)
            for phase in (
                "traffic",
                "direction",
                "timing",
                "imbalance",
            ):
                step = pick_narration_step(all_steps, phase)
                if step:
                    await self._emit_map_sequence(
                        emitter,
                        action="narration",
                        data={**step, "index": 0, "total": 1},
                    )
                    scene = build_map_scene(
                        phase,
                        cognition=cognition,
                        data=data,
                        nlu=session.nlu,
                    )
                    await self._emit_map_sequence(emitter, action="map_scene", data=scene)
        else:
            session.data_payload["cognition"] = cognition

        problem_evidence = await self._evidence.build(
            session.inter_id,
            session.resolved_intersection or "",
            session.nlu,
            data_payload=session.data_payload,
            user_context=session.raw_user_context,
        )
        session.data_payload["problem_evidence"] = problem_evidence

        sustained_metrics = await self._sustained.build(
            session.inter_id,
            session.nlu,
            data_payload=session.data_payload,
        )
        session.data_payload["sustained_metrics"] = sustained_metrics
        data = session.data_payload
        quantitative_constraints = None
        if session.nlu.user_suggestion:
            quantitative_constraints = self._constraints.resolve(
                session.nlu.user_suggestion,
                nlu_directions=session.nlu.directions,
                problem_evidence=problem_evidence,
            )
            if quantitative_constraints:
                session.data_payload["quantitative_constraints"] = quantitative_constraints
        self._log_evidence_debug(problem_evidence, quantitative_constraints)
        if emitter:
            pe_data: dict[str, Any] = {
                "summary": problem_evidence.get("summary"),
                "chronic": problem_evidence.get("chronic"),
                "dow_pattern": problem_evidence.get("dow_pattern"),
                "metrics": problem_evidence.get("metrics"),
                "by_direction": problem_evidence.get("by_direction"),
                "by_turn": problem_evidence.get("by_turn"),
                "by_approach": problem_evidence.get("by_approach"),
                "timing_profile": problem_evidence.get("timing_profile"),
                "corridor_context": problem_evidence.get("corridor_context"),
                "external_evidence": problem_evidence.get("external_evidence"),
                "diagnosis_story": problem_evidence.get("diagnosis_story"),
                "sustained_metrics": sustained_metrics,
            }
            if quantitative_constraints:
                pe_data["quantitative_constraints"] = quantitative_constraints
            await emitter.emit(
                "problem_evidence",
                "completed",
                data=pe_data,
            )

        data = session.data_payload

        problem_types = list(session.nlu.problem_types) if session.nlu else []
        focus_categories = (
            self._dimension_packs.focus_categories(problem_types)
            if problem_types
            else []
        )
        if emitter:
            await emitter.emit(
                "rule_engine",
                "running",
                data={
                    "problem_type": session.nlu.problem_type,
                    "problem_types": problem_types,
                    "focus_categories": focus_categories,
                },
            )
        if focus_categories:
            diagnosis = self._rules.diagnose_focused(focus_categories, data)
        else:
            diagnosis = self._rules.diagnose_comprehensive(data)
        if diagnosis.diagnosed and diagnosis.metrics_snapshot is not None:
            diagnosis.metrics_snapshot["matched_rule_count"] = len(diagnosis.matched_rules)

        flow_timing_governance = self._flow_governance.build(data)
        session.data_payload["flow_timing_governance"] = flow_timing_governance
        data = session.data_payload

        log_event(
            logger,
            logging.INFO,
            "rules.diagnosed",
            diagnosed=diagnosis.diagnosed,
            reason_code=diagnosis.reason_code,
            matched_rules=[r.get("id") for r in diagnosis.matched_rules],
        )
        if emitter:
            await emitter.emit(
                "rule_engine",
                "completed",
                data={
                    "diagnosed": diagnosis.diagnosed,
                    "reason_code": diagnosis.reason_code,
                    "matched_rules": diagnosis.matched_rules,
                    "metrics_snapshot": diagnosis.metrics_snapshot,
                    "flow_timing_governance": flow_timing_governance,
                },
            )
            rule_step = pick_narration_step(
                build_narration_steps(
                    cognition=cognition, data=data, diagnosis=diagnosis, nlu=session.nlu
                ),
                "rule",
            )
            if rule_step and diagnosis.diagnosed:
                await self._emit_map_sequence(
                    emitter, action="narration", data={**rule_step, "index": 0, "total": 1}
                )

        if skill_rule_ids:
            diagnosis = self._filter_skill_rules(diagnosis, skill_rule_ids)

        session.diagnosis = diagnosis

        # 复用先于沉淀：先采集历史档案中各步可复用经验（本轮写入之前）
        if session.inter_id:
            reuse_badges: list[str] = []
            for step in ("identify", "attribution", "solution"):
                reuse_badges.extend(
                    self._experience_reuse.for_step(session.inter_id, step).reuse_badges
                )
            if reuse_badges:
                session.data_payload["reused_experience"] = reuse_badges

        await self._record_problem_experience(
            session, diagnosis, flow_timing_governance, emitter
        )

        if session.skill_reuse_mode and session.matched_skill_id:
            skill = self._skills.get_by_id(session.matched_skill_id)
            if skill and skill.user_constraints and not session.nlu.user_suggestion:
                session.nlu.user_suggestion = skill.user_constraints
                quantitative_constraints = self._constraints.resolve(
                    skill.user_constraints,
                    nlu_directions=session.nlu.directions,
                    problem_evidence=session.data_payload.get("problem_evidence"),
                )
                if quantitative_constraints:
                    session.data_payload["quantitative_constraints"] = quantitative_constraints
            if skill and skill.quantitative_constraints and not session.data_payload.get(
                "quantitative_constraints"
            ):
                session.data_payload["quantitative_constraints"] = skill.quantitative_constraints

        if not diagnosis.diagnosed or not diagnosis.matched_rules:
            flow_gov = session.data_payload.get("flow_timing_governance") or {}
            if is_healthy_monitoring_case(flow_gov):
                content = await self._generate_monitoring_feedback_content(
                    session,
                    cognition=cognition,
                    data=data,
                    resolution_note=resolution_note,
                    emitter=emitter,
                )
                session.pending_suggestion_action = None
                session.state = SessionState.DONE
                return self._build_response(
                    session,
                    ReplyType.DIAGNOSIS,
                    content,
                    extra={
                        "suggestion_action": "monitoring_recorded",
                        "skill_action": "skipped_no_user_suggestion",
                    },
                )
            if emitter:
                step = pick_narration_step(
                    build_narration_steps(
                        cognition=cognition, data=data, diagnosis=diagnosis, nlu=session.nlu
                    ),
                    "rule",
                )
                if step:
                    await self._emit_map_sequence(
                        emitter, action="narration", data={**step, "index": 0, "total": 1}
                    )
            session.state = SessionState.DONE
            reason = diagnosis.reason_code or "no_rule_matched"
            msg = _no_diagnosis_message(reason, data)
            return self._build_response(session, ReplyType.TEXT, msg, extra={"reason_code": reason})

        # 原因诊断成立后：立即上游溯源运镜（与 RULE 步骤同步；有溯源帧时跳过 rule 地图场景）
        gov_point_count = await self._run_upstream_trace(session, cognition, emitter)
        if emitter:
            trace = session.data_payload.get("upstream_trace") or {}
            storyboard = trace.get("storyboard") or {}
            if not storyboard.get("frames"):
                scene = build_map_scene(
                    "rule",
                    cognition=cognition,
                    data=data,
                    diagnosis=diagnosis,
                    nlu=session.nlu,
                )
                await self._emit_map_sequence(emitter, action="map_scene", data=scene)

        if session.skill_reuse_mode and session.matched_skill_id:
            reuse_note = skill_reuse_notice or ""
            if reuse_note and resolution_note:
                resolution_note = f"{reuse_note}\n{resolution_note}"
            elif reuse_note:
                resolution_note = reuse_note
            session.pending_suggestion_action = "generate"
            session.state = SessionState.AWAITING_CONFIRM
            if emitter:
                await self._emit_map_sequence(
                    emitter,
                    action="confirm_bubble",
                    data={
                        "action_type": "generate_suggestion",
                        "intersection": cognition.get("intersection"),
                        "message": "已基于沉淀技能完成诊断复核，是否生成治理建议？",
                    },
                )
                await self._emit_map_sequence(
                    emitter,
                    action="input_dock",
                    data={"phase": "confirm", "locked": False},
                )
            content = self._format_problem_confirm_message(session, resolution_note)
            content = (
                f"{content}\n\n---\n已基于沉淀技能完成诊断复核，是否需要生成治理建议？"
                "回复「是」生成，或直接补充治理约束/经验；回复「否」结束本次会话。"
            )
            return self._build_response(
                session,
                ReplyType.FOLLOW_UP,
                content,
                extra={
                    "suggestion_action": "awaiting_generate",
                    "skill_reused": True,
                    "skill_match_reason": "matched",
                },
            )

        if session.nlu.user_suggestion:
            content = await self._generate_suggestion_content(
                session,
                resolution_note=resolution_note,
                emitter=emitter,
            )
            return await self._await_skill_create_confirmation(
                session,
                content,
                emitter=emitter,
                suggestion_action="generated_with_user_suggestion",
            )

        # 主诊断路径（无用户建议）：零确认。溯源完成后直接生成（跨路口协调）治理建议，
        # 直接结束；本路径无新增用户约束故不固化技能（用户补充约束时走 user_suggestion 分支固化）。
        content = await self._generate_suggestion_content(
            session,
            resolution_note=resolution_note,
            emitter=emitter,
        )
        session.pending_suggestion_action = None
        session.state = SessionState.DONE
        suggestion_action = (
            "generated_cross_intersection" if gov_point_count > 0 else "generated"
        )
        return self._build_response(
            session,
            ReplyType.DIAGNOSIS,
            content,
            extra={
                "suggestion_action": suggestion_action,
                "skill_action": "skipped_no_user_suggestion",
            },
        )

    async def _generate_monitoring_feedback_content(
        self,
        session: Session,
        *,
        cognition: dict[str, Any],
        data: dict[str, Any],
        resolution_note: str = "",
        emitter: ExecutionEmitter | None = None,
    ) -> str:
        """Healthy intersection: data-based monitoring card, no skill solidification."""
        assert session.nlu is not None
        data = prepare_suggestion_data(session.data_payload)
        session.data_payload["flow_timing_governance"] = data.get("flow_timing_governance")
        narrative = compose_monitoring_feedback_narrative(data)
        flow_gov = data.get("flow_timing_governance") or {}
        action_plan = flow_gov.get("action_plan") or {}
        suggestion = SuggestionResult(
            delta_seconds=0,
            direction="none",
            narrative=narrative,
            confidence=float(action_plan.get("confidence") or 0.65),
            rule_id="monitoring_feedback",
            action_type="maintain",
            action_plan=action_plan,
        )
        session.suggestion = suggestion
        log_event(
            logger,
            logging.INFO,
            "suggestion.monitoring_recorded",
            inter_id=session.inter_id,
            saturation=(data.get("traffic_flow") or {}).get("saturation_rate"),
        )
        if emitter:
            await emitter.emit(
                "suggestion",
                "completed",
                data=suggestion.model_dump(),
            )
            conclusion = enrich_narration_step(
                {
                    "phase": "conclusion",
                    "title": "运行反馈",
                    "text": narrative,
                    "suggestion": suggestion.model_dump(),
                }
            )
            await self._emit_map_sequence(
                emitter,
                action="narration",
                data={**conclusion, "index": 0, "total": 1, "final": True},
            )
            scene = build_map_scene(
                "conclusion",
                cognition=cognition,
                data=data,
                diagnosis=session.diagnosis,
                suggestion=suggestion,
                nlu=session.nlu,
            )
            await self._emit_map_sequence(emitter, action="map_scene", data=scene)

        time_label = session.nlu.time_period.label if session.nlu.time_period else ""
        note = f"\n{resolution_note}" if resolution_note else ""
        intersection = session.nlu.intersection or session.resolved_intersection or ""
        return f"**运行监测** · {intersection} · {time_label}{note}\n\n{narrative}"

    async def _generate_suggestion_content(
        self,
        session: Session,
        *,
        resolution_note: str = "",
        emitter: ExecutionEmitter | None = None,
    ) -> str:
        """Generate governance suggestion after user confirms the need."""
        assert session.nlu is not None
        assert session.diagnosis is not None
        assert session.diagnosis.matched_rules
        data = prepare_suggestion_data(session.data_payload)
        session.data_payload["flow_timing_governance"] = data.get("flow_timing_governance")
        if data.get("flow_trace"):
            session.data_payload["flow_trace"] = data["flow_trace"]
        cognition = data.get("cognition") or {}
        rule = session.diagnosis.matched_rules[0]

        if emitter:
            await emitter.emit(
                "suggestion",
                "running",
                data={
                    "rule_id": rule.get("id"),
                    "user_suggestion": safe_preview(session.nlu.user_suggestion),
                },
            )
        # 专家经验库匹配：按问题类型 + 路口场景文本注入同类场景治理经验
        problem_types = session.nlu.problem_types or ["congestion"]
        scene_text = " ".join(
            str(part)
            for part in (
                session.resolved_intersection or "",
                session.raw_user_context or "",
                cognition,
            )
        )
        case_matches = self._case_library.match(problem_types, scene_text=scene_text, k=2)
        case_experience_block = self._case_library.format_experience_block(case_matches)
        if case_matches:
            session.data_payload["case_experience"] = case_matches

        raw_delta = evaluate_formula(rule["action"]["formula"], data)
        flow_gov = data.get("flow_timing_governance") or {}
        action_plan = flow_gov.get("action_plan") or {}
        plan_type = str(action_plan.get("action_type") or "")
        if plan_type in ("reallocate_green", "increase_green"):
            plan_delta = action_plan.get("transfer_seconds")
            if plan_delta is not None and int(plan_delta) > 0:
                raw_delta = int(plan_delta)
        elif plan_type in ("capacity_non_timing", "spillback_control", "maintain", "guidance_only"):
            raw_delta = 0
        direction_override = action_plan.get("direction")
        clipped_delta, clip_note = self._constraints.apply_to_delta(
            raw_delta,
            session.data_payload.get("quantitative_constraints"),
            problem_evidence=session.data_payload.get("problem_evidence"),
        )
        suggestion = await self._suggestions.generate(
            rule,
            data,
            user_suggestion=session.nlu.user_suggestion,
            quantitative_constraints=session.data_payload.get("quantitative_constraints"),
            delta_override=clipped_delta,
            direction_override=str(direction_override) if direction_override else None,
            case_experience=case_experience_block,
        )
        if clipped_delta != raw_delta and clip_note:
            suggestion = suggestion.model_copy(
                update={"narrative": f"{suggestion.narrative}（{clip_note}）"},
            )
        # 可溯源依据：同类专家案例 + 本路口复用经验 → 案例库跳转锚点
        references = derive_suggestion_references(
            case_matches,
            session.data_payload.get("reused_experience"),
            inter_id=session.inter_id,
        )
        if references:
            suggestion = suggestion.model_copy(update={"references": references})
        session.suggestion = suggestion
        log_event(
            logger,
            logging.INFO,
            "suggestion.generated",
            rule_id=suggestion.rule_id,
            delta_seconds=suggestion.delta_seconds,
            direction=suggestion.direction,
            user_suggestion=session.nlu.user_suggestion,
        )
        if emitter:
            await emitter.emit(
                "suggestion",
                "completed",
                data=suggestion.model_dump(),
            )
            conclusion = pick_narration_step(
                build_narration_steps(
                    cognition=cognition,
                    data=data,
                    diagnosis=session.diagnosis,
                    suggestion=suggestion,
                    nlu=session.nlu,
                ),
                "conclusion",
            )
            if conclusion:
                await self._emit_map_sequence(
                    emitter,
                    action="narration",
                    data={**conclusion, "index": 0, "total": 1, "final": True},
                )
                scene = build_map_scene(
                    "conclusion",
                    cognition=cognition,
                    data=data,
                    diagnosis=session.diagnosis,
                    suggestion=suggestion,
                    nlu=session.nlu,
                )
                await self._emit_map_sequence(emitter, action="map_scene", data=scene)

        time_label = session.nlu.time_period.label if session.nlu.time_period else ""
        return self._suggestions.format_diagnosis_message(
            suggestion,
            session.nlu.intersection or session.resolved_intersection or "",
            time_label,
            resolution_note,
            flow_timing_governance=session.data_payload.get("flow_timing_governance"),
        )

    async def _persist_skill_from_session(
        self,
        session: Session,
        *,
        action: str,
        emitter: ExecutionEmitter | None,
    ) -> SkillUpsertResult:
        """Persist current session as a Skill, optionally through visual SSE."""
        if emitter:
            await emitter.emit("skill_create", "running")
            result = await self._skills.upsert_from_session_visual(session, emitter)
        else:
            result = self._skills.upsert_from_session(session)
        await self._record_solution_ref(session, result, emitter)
        session.pending_skill_action = None
        log_event(
            logger,
            logging.INFO,
            "skill.persisted",
            skill_id=result.record.skill_id,
            persist_action=result.action,
            confirm_action=action,
        )
        if emitter:
            await emitter.emit(
                "skill_create",
                "completed",
                data={"skill_id": result.record.skill_id, "action": result.action},
            )
        return result

    def _base_user_suggestion_for_merge(self, session: Session) -> str | None:
        """Existing session or matched skill constraints before D1 supplement."""
        if session.nlu and session.nlu.user_suggestion and session.nlu.user_suggestion.strip():
            return session.nlu.user_suggestion
        if session.matched_skill_id:
            skill = self._skills.get_by_id(session.matched_skill_id)
            if skill and skill.user_constraints:
                return skill.user_constraints
        return None

    async def _await_skill_create_confirmation(
        self,
        session: Session,
        content: str,
        *,
        emitter: ExecutionEmitter | None,
        suggestion_action: str,
    ) -> dict[str, Any]:
        """Show generated suggestion, then wait for user confirmation before persisting Skill."""
        existing = (
            self._skills.get_by_id(self._skills._skill_id_for_session(session))
            if session.inter_id
            else None
        )
        session.pending_skill_action = "update" if existing else "create"
        session.state = SessionState.AWAITING_CONFIRM
        prompt = (
            "已生成治理建议，是否将本次新增约束更新到路口 Skill？"
            if existing
            else "已生成治理建议，是否将本次诊断和约束沉淀为路口 Skill？"
        )
        if emitter:
            await self._emit_map_sequence(
                emitter,
                action="confirm_bubble",
                data={"action_type": "create", "message": prompt},
            )
            await self._emit_map_sequence(
                emitter,
                action="input_dock",
                data={"phase": "confirm", "locked": False},
            )
        return self._build_response(
            session,
            ReplyType.DIAGNOSIS,
            f"{content}\n\n---\n{prompt}回复「是」固化，「否」仅保留本次建议。",
            extra={
                "suggestion_action": suggestion_action,
                "skill_action": "awaiting_create",
            },
        )

    @staticmethod
    def _format_problem_confirm_message(session: Session, resolution_note: str = "") -> str:
        """Format diagnosis-only text before governance suggestion generation."""
        assert session.nlu is not None
        assert session.diagnosis is not None
        rule = session.diagnosis.matched_rules[0] if session.diagnosis.matched_rules else {}
        time_label = session.nlu.time_period.label if session.nlu.time_period else ""
        note = f"\n{resolution_note}" if resolution_note else ""
        conclusion = _diagnosis_only_conclusion(
            str(rule.get("conclusion") or ""),
            fallback="已确认存在拥堵诊断问题",
        )
        title = session.nlu.intersection or session.resolved_intersection
        evidence_block = format_evidence_summary_markdown(
            session.data_payload.get("problem_evidence")
        )
        flow_gov = session.data_payload.get("flow_timing_governance") or {}
        expert_block = flow_gov.get("expert_rules_markdown") or format_expert_rules_markdown(
            flow_gov.get("expert_rules") or []
        )
        constraint_block = ""
        constraints = session.data_payload.get("quantitative_constraints")
        if constraints and constraints.get("narrative"):
            constraint_block = f"\n\n**约束量化**\n{constraints['narrative']}"

        body = f"""**问题诊断已成立** · {title} · {time_label}{note}

{conclusion}"""
        if evidence_block:
            body = f"{body}\n\n{evidence_block}"
        if expert_block:
            body = f"{body}\n\n{expert_block}"
        if constraint_block:
            body = f"{body}{constraint_block}"
        return body

    def _log_evidence_debug(
        self,
        evidence: dict[str, Any] | None,
        constraints: dict[str, Any] | None,
    ) -> None:
        """Print evidence report when EVIDENCE_DEBUG=1."""
        if not self._settings.evidence_debug:
            return
        report = format_evidence_report(evidence, constraints)
        print(report, flush=True)
        log_event(logger, logging.INFO, "evidence.debug", report=report)

    def _finalize_skill_confirm(
        self,
        session: Session,
        result: SkillUpsertResult,
        confirm_action: str,
        *,
        content_prefix: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build user reply after skill persist attempt."""
        skill = result.record
        base_extra = dict(extra or {})
        prefix = f"{content_prefix}\n\n---\n" if content_prefix else ""

        if result.action == "unchanged":
            base_extra.update({"skill_id": skill.skill_id, "skill_action": "unchanged"})
            return self._build_response(
                session,
                ReplyType.TEXT,
                f"{prefix}Skill `{skill.skill_id}` 已是最新，无需更新。",
                extra=base_extra,
            )

        if result.action == "updated" or confirm_action == "update":
            base_extra.update({"skill_id": skill.skill_id, "skill_action": "updated"})
            return self._build_response(
                session,
                ReplyType.SKILL_UPDATED,
                (
                    f"{prefix}✅ 已更新路口专属 Skill（ID: `{skill.skill_id}`）。"
                    "下次同类问题将沿用更新后的诊断模式。"
                ),
                extra=base_extra,
            )

        base_extra.update({"skill_id": skill.skill_id, "skill_action": "created"})
        return self._build_response(
            session,
            ReplyType.SKILL_CREATED,
            (
                f"{prefix}✅ 已固化为路口专属 Skill（ID: `{skill.skill_id}`）。"
                "下次同类问题将直接给出结论。"
            ),
            extra=base_extra,
        )

    async def _run_upstream_trace(
        self,
        session: Session,
        cognition: dict[str, Any],
        emitter: ExecutionEmitter | None,
    ) -> int:
        """溯源上游、定位治理落点。触发进口 = 过饱和进口 ∪ 用户明示方向。返回落点数；失败返回 0。"""
        if not session.inter_id:
            return 0
        data = session.data_payload
        by_turn = (data.get("granularity") or {}).get("by_turn") or []
        trigger = threshold_value("upstream_trace", "trigger_saturation", default=0.90)
        available = {d8 for r in by_turn if (d8 := _row_dir8(r)) is not None}
        saturated = {
            d8
            for r in by_turn
            if (r.get("turn_saturation") or 0.0) >= trigger
            and (d8 := _row_dir8(r)) is not None
        }
        # 收口：用户明示方向/转向（如「西进口」「南北向」）为最高优先级，命中时只溯该方向；
        # 用户未指定时，默认只聚焦诊断命中的「首个（最饱和）问题进口」一条链路，
        # 不再把其余过饱和进口自动并入，保证流量溯源始终是单一来流溯源。
        nlu_dirs = session.nlu.directions if session.nlu else None
        # 「西左转」等带转向语义时只溯该进口，不把同句里顺带提到的其它进口并入。
        turn_specific = _turn_specific_dir8s(nlu_dirs, available)
        directed = _dir8s_from_directions(nlu_dirs, available)
        if turn_specific:
            dir8s = turn_specific
        elif directed:
            dir8s = sorted(directed)
        elif saturated:
            top_row = max(
                (r for r in by_turn if _row_dir8(r) in saturated),
                key=lambda r: r.get("turn_saturation") or 0.0,
                default=None,
            )
            top_dir = _row_dir8(top_row) if top_row else None
            dir8s = [top_dir] if top_dir is not None else []
        else:
            dir8s = []
        approaches = [f"{DIR8_LABELS[d]}进口" for d in dir8s if d in DIR8_LABELS]
        if not approaches:
            return 0

        if emitter:
            await emitter.emit(
                "upstream_trace", "running", data={"approaches": approaches}
            )
        try:
            trace = await self._upstream_trace.build(
                session.inter_id,
                approaches=approaches,
                nlu=session.nlu,
                cognition=cognition,
            )
        except Exception as exc:  # noqa: BLE001 - 溯源失败不应阻断主诊断
            log_event(logger, logging.WARNING, "upstream_trace.failed", error=str(exc))
            return 0

        session.data_payload["upstream_trace"] = trace
        points = trace.get("governance_points") or []
        session.data_payload["upstream_governance_point_count"] = len(points)
        if emitter:
            await emitter.emit(
                "upstream_trace",
                "completed",
                data={
                    "governance_points": points,
                    "trees": len(trace.get("trees") or []),
                },
            )
            storyboard = trace.get("storyboard") or {}
            if storyboard.get("frames"):
                await self._emit_map_sequence(
                    emitter, action="upstream_tree", data={"storyboard": storyboard}
                )
        return len(points)

    @staticmethod
    async def _emit_map_sequence(
        emitter: ExecutionEmitter,
        *,
        action: str,
        data: dict[str, Any],
    ) -> None:
        """Emit map_action step for frontend animation."""
        await emitter.emit(
            "map_action",
            "running",
            data={"action": action, **data},
        )
        await emitter.emit(
            "map_action",
            "completed",
            data={"action": action, **data},
        )

    @staticmethod
    def _filter_skill_rules(diagnosis: DiagnosisResult, rule_ids: list[str]) -> DiagnosisResult:
        """Keep only rules from skill snapshot."""
        filtered = [r for r in diagnosis.matched_rules if r.get("id") in rule_ids]
        if filtered:
            diagnosis.matched_rules = filtered
            diagnosis.diagnosed = True
        return diagnosis

    @staticmethod
    def _build_response(
        session: Session,
        reply_type: ReplyType,
        content: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build standardized API response dict."""
        meta = {
            "matched_skill": session.matched_skill_id,
            "resolution_source": session.resolution_source,
            "inter_id": session.inter_id,
            "skill_reused": session.skill_reuse_mode or bool(session.matched_skill_id),
        }
        problem_types = list(session.nlu.problem_types) if session.nlu and session.nlu.problem_types else []
        if problem_types:
            meta["problem_types"] = problem_types
            # 驱动前端「无关卡片/图层/播报不出现」（_build_response 为 staticmethod，用模块级单例）
            meta["active_dimensions"] = _presentation_dimension_packs().presentation_dimensions(
                problem_types
            )
        if session.data_payload:
            data_meta = session.data_payload.get("meta", {})
            dw = data_meta.get("data_window")
            if dw:
                meta["data_window"] = dw
            query_trace = data_meta.get("query_trace")
            if query_trace:
                meta["query_trace"] = query_trace
            cognition = session.data_payload.get("cognition")
            if cognition:
                meta["cognition"] = cognition
            problem_evidence = session.data_payload.get("problem_evidence")
            if problem_evidence:
                meta["problem_evidence"] = problem_evidence
            quantitative_constraints = session.data_payload.get("quantitative_constraints")
            if quantitative_constraints:
                meta["quantitative_constraints"] = quantitative_constraints
            flow_gov = session.data_payload.get("flow_timing_governance")
            if flow_gov:
                meta["flow_timing_governance"] = flow_gov
            sustained = session.data_payload.get("sustained_metrics")
            if sustained:
                meta["sustained_metrics"] = sustained
            if data_meta.get("demo_mode"):
                meta["demo_mode"] = True
            reused_experience = session.data_payload.get("reused_experience")
            if reused_experience:
                meta["reused_experience"] = reused_experience
            case_experience = session.data_payload.get("case_experience")
            if case_experience:
                meta["case_experience"] = case_experience
        if extra:
            meta.update(extra)

        return {
            "session_id": session.session_id,
            "state": session.state.value,
            "reply": {"type": reply_type.value, "content": content},
            "nlu": session.nlu.model_dump() if session.nlu else None,
            "diagnosis": session.diagnosis.model_dump() if session.diagnosis else None,
            "suggestion": session.suggestion.model_dump() if session.suggestion else None,
            "meta": meta,
        }


_PRESENTATION_DIMENSION_PACKS: DimensionPackService | None = None


def _presentation_dimension_packs() -> DimensionPackService:
    """Module-level singleton (cheap YAML) for static _build_response usage."""
    global _PRESENTATION_DIMENSION_PACKS
    if _PRESENTATION_DIMENSION_PACKS is None:
        _PRESENTATION_DIMENSION_PACKS = DimensionPackService()
    return _PRESENTATION_DIMENSION_PACKS


def _no_diagnosis_message(reason_code: str, data: dict[str, Any]) -> str:
    """User message when no rule matches."""
    if reason_code == "missing_dws_coverage":
        return "该路口暂无完整运行数据（运行数据未覆盖），无法给出可靠拥堵诊断，请联系数据管理员补采。"
    snap = data.get("traffic_flow", {})
    return (
        "根据当前数据，暂未命中拥堵诊断规则，可能需要进一步现场调研或补充数据。"
        f"（饱和度 {snap.get('saturation_rate', 'N/A')}）"
    )


def _diagnosis_only_conclusion(conclusion: str, *, fallback: str) -> str:
    """Remove governance-action clauses from rule conclusions used before confirmation."""
    action_terms = (
        "建议",
        "治理",
        "措施",
        "增加",
        "减少",
        "延长",
        "缩短",
        "优化",
        "调整",
        "改善",
    )
    parts = [part.strip() for part in re.split(r"[，,。；;]", conclusion) if part.strip()]
    kept = [part for part in parts if not any(term in part for term in action_terms)]
    if kept:
        return "，".join(kept)
    return fallback
