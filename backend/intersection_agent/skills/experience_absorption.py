"""Build experience-absorption reports from session and skill library state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from intersection_agent.models.domain import Session
from intersection_agent.models.skill import SkillDiff, SkillRecord
from intersection_agent.services.skill_matcher import (
    build_skill_tags,
    match_layer,
    resolve_match_tags,
)
from intersection_agent.skills.package_builder import PACKAGE_FILE_PATHS
from intersection_agent.skills.tag_helpers import summarize_utterance

AbsorptionAction = Literal["CREATE", "UPDATE", "UNCHANGED"]


@dataclass
class AbsorptionRetrieveResult:
    """Skill library scan for absorption stage."""

    total_skills: int
    hit_count: int
    matched: bool
    candidates: list[dict[str, Any]] = field(default_factory=list)
    query: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExperienceAbsorptionReport:
    """Structured absorption payload for renderer and SSE."""

    action: AbsorptionAction
    skill_id: str
    intersection: str
    session_id: str
    utterance_summary: str
    tags: dict[str, Any]
    retrieve: AbsorptionRetrieveResult
    diff: SkillDiff
    what: dict[str, Any]
    why_rows: list[dict[str, str]]
    delta_rows: list[str]
    blueprint_files: list[str]
    package_dir: str
    library_count_before: int
    library_count_after: int
    version: int
    experience_points: list[str] = field(default_factory=list)


def build_experience_points(
    *,
    session: Session,
    candidate: SkillRecord,
    tags: dict[str, Any],
    diff: SkillDiff,
) -> list[str]:
    """Concrete experience deposition bullets for narrative and value stage."""
    points: list[str] = []
    nlu = session.nlu
    if nlu and nlu.user_suggestion:
        points.append(f"一线约束：{nlu.user_suggestion.strip()}")
    if candidate.user_constraints and candidate.user_constraints.strip():
        constraint = candidate.user_constraints.strip()
        if not points or constraint not in points[0]:
            points.append(f"治理边界：{constraint}")
    content = tags.get("content") or {}
    intent = content.get("constraint_intent")
    if intent:
        points.append(f"量化意图：{intent}")
    issue_codes = content.get("issue_codes") or []
    if issue_codes:
        points.append(f"诊断问题类：{', '.join(str(c) for c in issue_codes)}")
    if candidate.rule_ids:
        points.append(f"命中规则：{', '.join(candidate.rule_ids)}")
    if candidate.suggestion_formula:
        points.append(f"建议公式已固化")
    for change in diff.changes[:3]:
        points.append(f"相对库内增量：{change}")
    return points


def extract_issue_codes(session: Session) -> list[str]:
    """Detected flow-timing problem categories from governance payload."""
    flow_gov = session.data_payload.get("flow_timing_governance") or {}
    codes: list[str] = []
    for problem in flow_gov.get("problems") or []:
        if problem.get("detected") and problem.get("category"):
            codes.append(str(problem["category"]))
    return codes


def determine_absorption_action(
    existing: SkillRecord | None,
    *,
    snapshot_equal: bool,
) -> AbsorptionAction:
    """Map persist branch to absorption narrative action."""
    if existing is None:
        return "CREATE"
    if snapshot_equal:
        return "UNCHANGED"
    return "UPDATE"


def build_retrieve_result(
    skills: list[SkillRecord],
    candidate: SkillRecord,
    session: Session,
) -> AbsorptionRetrieveResult:
    """Scan library using the same match dimensions as fast path."""
    assert session.nlu is not None
    from intersection_agent.services.skill_matcher import match_skill

    match_result = match_skill(
        skills,
        session.nlu,
        candidate.inter_id,
        session.raw_user_context,
    )
    query = resolve_match_tags(candidate.tags or {})
    candidates: list[dict[str, Any]] = []
    for skill in skills:
        if skill.inter_id != candidate.inter_id:
            continue
        if skill.problem_type != candidate.problem_type:
            continue
        if skill.time_period_label != candidate.time_period_label:
            continue
        match_tags = resolve_match_tags(skill.tags or {})
        candidates.append(
            {
                "skill_id": skill.skill_id,
                "created_at": skill.created_at,
                "tags_match": match_tags,
            }
        )

    slot_hit = any(c["skill_id"] == candidate.skill_id for c in candidates)
    return AbsorptionRetrieveResult(
        total_skills=len(skills),
        hit_count=len(candidates),
        matched=slot_hit or bool(match_result.matched),
        candidates=candidates,
        query={
            "inter_id": query.get("inter_id"),
            "time_period": query.get("time_period"),
            "problem_type": query.get("problem_type"),
            "directions": query.get("directions") or [],
        },
    )


def build_why_rows(
    *,
    action: AbsorptionAction,
    skill_id: str,
    library_count_before: int,
    library_count_after: int,
) -> list[dict[str, str]]:
    """Fact table rows for value stage — no marketing copy."""
    fast_after = skill_id if action in ("CREATE", "UPDATE") else skill_id
    return [
        {
            "key": "retrievable",
            "label": "可检索",
            "before": "false",
            "after": "true" if action != "UNCHANGED" else "true",
        },
        {
            "key": "fast_path",
            "label": "快路径",
            "before": "不可用",
            "after": fast_after,
        },
        {
            "key": "constraint_snapshot",
            "label": "约束快照",
            "before": "仅本次会话",
            "after": "写入 tags.content" if action != "UNCHANGED" else "已与库一致",
        },
        {
            "key": "library_entries",
            "label": "经验库条目",
            "before": str(library_count_before),
            "after": str(library_count_after),
        },
    ]


def build_what_block(candidate: SkillRecord, tags: dict[str, Any]) -> dict[str, Any]:
    """What is being absorbed — business-facing bullets from real fields."""
    match_tags = match_layer(tags)
    content_tags = tags.get("content") or {}
    directions = match_tags.get("directions") or []
    direction_text = "、".join(directions) if directions else "—"
    title = f"{candidate.intersection} · {candidate.time_period_label} · {direction_text}"

    bullets = [
        (
            "场景键："
            f"{match_tags.get('inter_id')} + {match_tags.get('time_period')} + {direction_text}"
        ),
        f"判别规则：{', '.join(candidate.rule_ids) or '—'}",
    ]
    if content_tags.get("constraint_intent"):
        bullets.append(f"治理边界：{content_tags['constraint_intent']}")
    elif candidate.user_constraints:
        bullets.append(f"治理边界：{candidate.user_constraints}")
    profile = content_tags.get("data_window_profile")
    if profile:
        bullets.append(f"查数口径：{profile}")

    return {"title": title, "bullets": bullets}


def next_version(existing: SkillRecord | None, action: AbsorptionAction) -> int:
    """Version counter stored in tags.meta."""
    if action == "CREATE":
        return 1
    if existing and existing.tags:
        meta = existing.tags.get("meta") or {}
        if isinstance(meta.get("version"), int):
            return int(meta["version"]) + 1
    return 2


def build_absorption_report(
    *,
    session: Session,
    candidate: SkillRecord,
    existing: SkillRecord | None,
    diff: SkillDiff,
    all_skills: list[SkillRecord],
    snapshot_equal: bool,
) -> ExperienceAbsorptionReport:
    """Assemble full absorption report from real session and library data."""
    assert session.nlu is not None
    library_count_before = len(all_skills)
    action = determine_absorption_action(existing, snapshot_equal=snapshot_equal)
    if action == "CREATE":
        library_count_after = library_count_before + 1
    else:
        library_count_after = library_count_before

    version = next_version(existing, action)
    utterance = summarize_utterance(session.raw_user_context or session.user_messages_text())
    quantitative = session.data_payload.get("quantitative_constraints")
    issue_codes = extract_issue_codes(session)
    data_window = None
    if candidate.data_query_spec:
        data_window = candidate.data_query_spec.get("data_window")

    # Rebuild tags with meta counts for persistence preview
    tags = build_skill_tags(
        intersection=candidate.intersection,
        inter_id=candidate.inter_id,
        problem_type=candidate.problem_type,
        time_period_label=candidate.time_period_label,
        directions=list(session.nlu.directions or []),
        match_keywords=candidate.match_keywords,
        rule_ids=candidate.rule_ids,
        user_constraints=candidate.user_constraints,
        quantitative_constraints=quantitative,
        suggestion_formula=candidate.suggestion_formula,
        issue_codes=issue_codes,
        data_window=data_window,
        source_utterance_summary=utterance,
        library_count_before=library_count_before,
        library_count_after=library_count_after,
        version=version,
    )

    retrieve = build_retrieve_result(all_skills, candidate, session)
    what = build_what_block(candidate, tags)
    why_rows = build_why_rows(
        action=action,
        skill_id=candidate.skill_id,
        library_count_before=library_count_before,
        library_count_after=library_count_after,
    )
    experience_points = build_experience_points(
        session=session,
        candidate=candidate,
        tags=tags,
        diff=diff,
    )

    return ExperienceAbsorptionReport(
        action=action,
        skill_id=candidate.skill_id,
        intersection=candidate.intersection,
        session_id=session.session_id,
        utterance_summary=utterance,
        tags=tags,
        retrieve=retrieve,
        diff=diff,
        what=what,
        why_rows=why_rows,
        delta_rows=list(diff.changes),
        blueprint_files=list(PACKAGE_FILE_PATHS),
        package_dir=candidate.skill_dir,
        library_count_before=library_count_before,
        library_count_after=library_count_after,
        version=version,
        experience_points=experience_points,
    )


def tags_to_evidence_chips(tags: dict[str, Any]) -> list[dict[str, str]]:
    """Flatten tag layers into UI chips."""
    chips: list[dict[str, str]] = []
    for layer in ("match", "content", "meta"):
        layer_data = tags.get(layer) or {}
        if not isinstance(layer_data, dict):
            continue
        for key, value in layer_data.items():
            if value in (None, "", [], {}):
                continue
            chips.append(
                {
                    "key": f"{layer}.{key}",
                    "label": key,
                    "value": _stringify_chip_value(value),
                }
            )
    return chips


def _stringify_chip_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)

