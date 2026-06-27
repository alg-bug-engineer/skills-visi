"""Skill matching by tags, directions, and user constraints."""

from __future__ import annotations

import re
from typing import Any

from intersection_agent.models.domain import NluResult
from intersection_agent.models.skill import DEFAULT_PROBLEM_TYPE, SkillMatchResult, SkillRecord
from intersection_agent.skills.tag_helpers import (
    absorbed_at_iso,
    formula_hash,
    summarize_data_window_profile,
    summarize_utterance,
)


def match_layer(tags: dict[str, Any] | None) -> dict[str, Any]:
    """Return match-layer tags from nested or legacy flat structure."""
    return resolve_match_tags(tags or {})


def content_layer(tags: dict[str, Any] | None) -> dict[str, Any]:
    """Return content-layer tags from nested or legacy flat structure."""
    if not tags:
        return {}
    if "content" in tags and isinstance(tags["content"], dict):
        return dict(tags["content"])
    legacy_keys = (
        "rule_ids",
        "constraint_intent",
        "has_user_constraints",
        "issue_codes",
        "suggestion_formula_hash",
        "data_window_profile",
    )
    return {k: tags[k] for k in legacy_keys if k in tags}


def resolve_match_tags(tags: dict[str, Any]) -> dict[str, Any]:
    """Normalize tags to match-layer dict for retrieval and fast path."""
    if "match" in tags and isinstance(tags["match"], dict):
        return dict(tags["match"])
    return {
        "intersection": tags.get("intersection"),
        "inter_id": tags.get("inter_id"),
        "time_period": tags.get("time_period"),
        "problem_type": tags.get("problem_type"),
        "directions": tags.get("directions") or [],
        "match_keywords": tags.get("match_keywords") or [],
    }


def build_skill_tags(
    *,
    intersection: str,
    inter_id: str,
    problem_type: str,
    time_period_label: str,
    directions: list[str],
    match_keywords: list[str],
    rule_ids: list[str],
    user_constraints: str | None,
    quantitative_constraints: dict[str, Any] | None,
    suggestion_formula: str = "",
    issue_codes: list[str] | None = None,
    data_window: dict[str, Any] | None = None,
    source_utterance_summary: str = "",
    library_count_before: int | None = None,
    library_count_after: int | None = None,
    version: int = 1,
) -> dict[str, Any]:
    """Build searchable three-layer tag index for a skill package."""
    constraint_intent = None
    if quantitative_constraints:
        constraint_intent = quantitative_constraints.get("intent")

    match: dict[str, Any] = {
        "intersection": intersection,
        "inter_id": inter_id,
        "time_period": time_period_label,
        "problem_type": problem_type,
        "directions": list(directions),
        "match_keywords": list(match_keywords),
    }
    content: dict[str, Any] = {
        "rule_ids": list(rule_ids),
        "has_user_constraints": bool((user_constraints or "").strip()),
    }
    if issue_codes:
        content["issue_codes"] = list(issue_codes)
    if constraint_intent:
        content["constraint_intent"] = constraint_intent
    if suggestion_formula:
        content["suggestion_formula_hash"] = formula_hash(suggestion_formula)
    profile = summarize_data_window_profile(data_window)
    if profile != "unknown":
        content["data_window_profile"] = profile

    meta: dict[str, Any] = {
        "experience_source": "field_officer",
        "contributor_role": "一线民警",
        "version": version,
    }
    if source_utterance_summary:
        meta["source_utterance_summary"] = source_utterance_summary
    if library_count_before is not None:
        meta["library_count_before"] = library_count_before
    if library_count_after is not None:
        meta["library_count_after"] = library_count_after
    if library_count_before is not None or library_count_after is not None:
        meta["absorbed_at"] = absorbed_at_iso()

    return {"match": match, "content": content, "meta": meta}


def compare_content_tags(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> list[str]:
    """Human-readable diffs between content tag layers."""
    left_content = content_layer(left)
    right_content = content_layer(right)
    changes: list[str] = []
    keys = sorted(set(left_content) | set(right_content))
    for key in keys:
        if left_content.get(key) != right_content.get(key):
            changes.append(f"tags.content.{key}: {left_content.get(key)} → {right_content.get(key)}")
    return changes


def backfill_tags(skill: SkillRecord) -> dict[str, Any]:
    """Derive tags from legacy skill records missing the nested structure."""
    if skill.tags and "match" in skill.tags:
        return dict(skill.tags)
    if skill.tags:
        return build_skill_tags(
            intersection=skill.intersection,
            inter_id=skill.inter_id,
            problem_type=skill.problem_type,
            time_period_label=skill.time_period_label,
            directions=_directions_from_keywords(skill.match_keywords),
            match_keywords=skill.match_keywords,
            rule_ids=skill.rule_ids,
            user_constraints=skill.user_constraints,
            quantitative_constraints=skill.quantitative_constraints,
            suggestion_formula=skill.suggestion_formula,
            source_utterance_summary=summarize_utterance(skill.user_constraints or ""),
            version=1,
        )
    return build_skill_tags(
        intersection=skill.intersection,
        inter_id=skill.inter_id,
        problem_type=skill.problem_type,
        time_period_label=skill.time_period_label,
        directions=_directions_from_keywords(skill.match_keywords),
        match_keywords=skill.match_keywords,
        rule_ids=skill.rule_ids,
        user_constraints=skill.user_constraints,
        quantitative_constraints=skill.quantitative_constraints,
        suggestion_formula=skill.suggestion_formula,
        version=1,
    )


def match_skill(
    skills: list[SkillRecord],
    nlu: NluResult,
    inter_id: str,
    raw_text: str,
) -> SkillMatchResult:
    """Find the best matching skill for the current NLU result."""
    problem_type = nlu.problem_type or DEFAULT_PROBLEM_TYPE
    if not nlu.time_period:
        return SkillMatchResult(None, False, "no_skill", "缺少时段信息，无法匹配历史技能")

    candidates = [
        s
        for s in skills
        if s.inter_id == inter_id
        and s.problem_type == problem_type
        and s.time_period_label == nlu.time_period.label
    ]
    if not candidates:
        return SkillMatchResult(None, False, "no_skill", None)

    candidates.sort(key=lambda s: s.created_at, reverse=True)
    user_constraint = (nlu.user_suggestion or "").strip()

    for skill in candidates:
        tags = backfill_tags(skill)
        match_tags = match_layer(tags)
        direction_ok, direction_detail = _directions_compatible(
            match_tags.get("directions") or [], nlu.directions
        )
        if not direction_ok:
            continue

        constraint_ok, constraint_detail = _constraints_compatible(
            skill.user_constraints, user_constraint
        )
        if not constraint_ok:
            return SkillMatchResult(
                skill,
                False,
                "constraint_mismatch",
                constraint_detail
                or f"用户约束「{user_constraint}」与历史技能不一致，将重新完整诊断",
            )

        if not _keyword_compatible(skill, raw_text):
            continue

        detail = _format_match_detail(skill, match_tags)
        return SkillMatchResult(skill, True, "matched", detail)

    if nlu.directions:
        return SkillMatchResult(
            None,
            False,
            "direction_mismatch",
            f"未找到与进口方向「{'、'.join(nlu.directions)}」匹配的历史技能",
        )

    return SkillMatchResult(None, False, "no_skill", None)


def _directions_compatible(skill_directions: list[str], nlu_directions: list[str]) -> tuple[bool, str | None]:
    """Skill and NLU directions must overlap when skill has direction tags."""
    if not skill_directions:
        return True, None
    if not nlu_directions:
        return True, None
    skill_set = set(skill_directions)
    nlu_set = set(nlu_directions)
    if skill_set & nlu_set:
        return True, None
    return (
        False,
        f"历史技能方向为「{'、'.join(skill_directions)}」，与本次「{'、'.join(nlu_directions)}」不一致",
    )


def _constraints_compatible(
    skill_constraint: str | None,
    user_constraint: str,
) -> tuple[bool, str | None]:
    """User constraints must be absent or equal to the skill snapshot."""
    if not user_constraint:
        return True, None
    skill_norm = _normalize_constraint(skill_constraint or "")
    user_norm = _normalize_constraint(user_constraint)
    if not skill_norm:
        return (
            False,
            f"本次新增治理约束「{user_constraint}」，与无约束的历史技能不匹配",
        )
    if skill_norm == user_norm:
        return True, None
    return (
        False,
        f"用户约束「{user_constraint}」与历史技能约束「{skill_constraint}」不一致",
    )


def _keyword_compatible(skill: SkillRecord, raw_text: str) -> bool:
    """Optional keyword gate when skill defines match_keywords."""
    if not skill.match_keywords:
        return True
    text_lower = raw_text.lower()
    return any(kw.lower() in text_lower for kw in skill.match_keywords)


def _normalize_constraint(text: str) -> str:
    normalized = text.strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _format_match_detail(skill: SkillRecord, tags: dict[str, Any]) -> str:
    period = tags.get("time_period") or skill.time_period_label
    directions = tags.get("directions") or []
    direction_text = "、".join(directions) if directions else "—"
    lines = [
        f"发现沉淀技能：{skill.intersection} · {period} · {direction_text}",
        f"Skill ID：`{skill.skill_id}`",
    ]
    if skill.user_constraints:
        lines.append(f"历史约束：{skill.user_constraints}")
    lines.append("将基于历史经验辅助本次诊断。")
    return "\n".join(lines)


def _directions_from_keywords(keywords: list[str]) -> list[str]:
    directions: list[str] = []
    for token in ("东西向", "南北向", "东南向", "西南向", "东北向", "西北向"):
        if token in keywords:
            directions.append(token)
    return directions
