"""Skill domain models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_PROBLEM_TYPE = "congestion"


@dataclass
class SkillRecord:
    """Persisted intersection skill (index + package metadata)."""

    skill_id: str
    skill_dir: str
    intersection: str
    inter_id: str
    problem_type: str
    time_period_label: str
    match_keywords: list[str]
    data_query_spec: dict[str, Any]
    rule_ids: list[str]
    suggestion_formula: str
    created_at: str
    updated_at: str | None = None
    user_constraints: str | None = None
    quantitative_constraints: dict[str, Any] | None = None
    tags: dict[str, Any] | None = None


@dataclass
class SkillMatchResult:
    """Outcome of matching a user request against persisted skills."""

    skill: SkillRecord | None
    matched: bool
    reason: str  # matched | no_skill | direction_mismatch | constraint_mismatch
    detail: str | None = None


@dataclass
class SkillDiff:
    """Difference between persisted skill and current session diagnosis."""

    has_material_diff: bool
    changes: list[str]


@dataclass
class SkillUpsertResult:
    """Outcome of persisting a skill from session."""

    record: SkillRecord
    action: str  # created | updated | unchanged
