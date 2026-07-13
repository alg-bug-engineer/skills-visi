"""Rule-based structured tags for textbook cases (需求30)."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "data/intersection_config/case_tag_schema.yaml"
)


@lru_cache(maxsize=1)
def _load_schema(schema_path: str | None = None) -> dict[str, Any]:
    path = Path(schema_path) if schema_path else DEFAULT_SCHEMA_PATH
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class CaseTagExtractor:
    def __init__(self, schema_path: str | None = None) -> None:
        self.schema = _load_schema(schema_path)
        self.dimension_labels: dict[str, str] = self.schema.get("dimension_labels") or {}
        self.match_weights: dict[str, float] = {
            k: float(v) for k, v in (self.schema.get("match_weights") or {}).items()
        }
        self.high_threshold = float(self.schema.get("high_similarity_threshold") or 4.0)
        self._dimensions: dict[str, dict[str, dict[str, Any]]] = self.schema.get("dimensions") or {}
        self._query_mappings: dict[str, dict[str, str]] = self.schema.get("query_mappings") or {}

    def case_text(self, case: dict[str, Any]) -> str:
        parts = [
            case.get("案例场景") or case.get("scene") or "",
            case.get("交通问题诊断") or case.get("diagnosis") or "",
            case.get("治理方案") or case.get("solution") or "",
            case.get("预期效果") or case.get("effect") or "",
        ]
        return " ".join(str(p) for p in parts if p)

    def extract_tags(self, case: dict[str, Any]) -> dict[str, list[str]]:
        return self.extract_from_text(self.case_text(case))

    def extract_from_text(self, text: str) -> dict[str, list[str]]:
        tags: dict[str, list[str]] = {}
        if not text:
            return tags
        for dimension, values in self._dimensions.items():
            hits: list[str] = []
            for value_key, spec in values.items():
                keywords = spec.get("keywords") or []
                if any(kw in text for kw in keywords):
                    hits.append(value_key)
            if hits:
                tags[dimension] = hits
        return tags

    def merge_tags(self, *tag_dicts: dict[str, list[str]]) -> dict[str, list[str]]:
        merged: dict[str, list[str]] = {}
        for tags in tag_dicts:
            for dimension, values in (tags or {}).items():
                bucket = merged.setdefault(dimension, [])
                for value in values:
                    if value not in bucket:
                        bucket.append(value)
        return merged

    def tags_to_labels(self, tags: dict[str, list[str]]) -> dict[str, list[str]]:
        labeled: dict[str, list[str]] = {}
        for dimension, values in tags.items():
            dim_spec = self._dimensions.get(dimension) or {}
            labels: list[str] = []
            for value_key in values:
                label = (dim_spec.get(value_key) or {}).get("label") or value_key
                labels.append(label)
            if labels:
                group = self.dimension_labels.get(dimension, dimension)
                labeled[group] = labels
        return labeled

    def build_query_profile(
        self,
        ticket: dict[str, Any] | None = None,
        diagnosis: dict[str, Any] | None = None,
    ) -> dict[str, list[str]]:
        ticket = ticket or {}
        diagnosis = diagnosis or {}
        profile: dict[str, list[str]] = {}

        problem_type = ticket.get("problem_type") or ""
        pt_map = self._query_mappings.get("problem_type") or {}
        for key, value_key in pt_map.items():
            if key in problem_type:
                profile.setdefault("problem_type", []).append(value_key)
        if not profile.get("problem_type") and problem_type:
            if any(k in problem_type for k in ("溢出", "溢流", "排队")):
                profile.setdefault("problem_type", []).append("queue_overflow")

        period = ticket.get("period") or ticket.get("time_period") or ""
        period_map = self._query_mappings.get("period") or {}
        for key, value_key in period_map.items():
            if key in str(period):
                profile.setdefault("time_period", []).append(value_key)

        time_range = str(ticket.get("time_range") or "")
        if "早" in time_range and "morning_peak" not in (profile.get("time_period") or []):
            profile.setdefault("time_period", []).append("morning_peak")
        if "晚" in time_range and "evening_peak" not in (profile.get("time_period") or []):
            profile.setdefault("time_period", []).append("evening_peak")

        bottleneck = diagnosis.get("bottleneck_analysis") or {}
        bn_type = bottleneck.get("bottleneck_type") or ""
        bn_map = self._query_mappings.get("bottleneck_type") or {}
        if bn_type in bn_map:
            profile.setdefault("spatial_topology", []).append(bn_map[bn_type])

        downstream = diagnosis.get("downstream_diagnosis") or {}
        scenario = downstream.get("scenario") or ""
        ds_map = self._query_mappings.get("downstream_scenario") or {}
        if scenario in ds_map:
            profile.setdefault("spatial_topology", []).append(ds_map[scenario])
        if downstream.get("release_answer") in ("blocked", "limited", False):
            profile.setdefault("traffic_pattern", []).append("release_blocked")

        if diagnosis.get("arterial_coordination_needed"):
            profile.setdefault("scope_type", []).append("arterial_coordination")

        overflow = diagnosis.get("overflow_verification") or {}
        if overflow.get("verified"):
            profile.setdefault("problem_type", []).append("queue_overflow")

        metrics = diagnosis.get("metrics") or {}
        sat = metrics.get("saturation") or metrics.get("saturation_rate")
        try:
            if sat is not None and float(sat) >= 0.85:
                profile.setdefault("problem_type", []).append("saturation_high")
        except (TypeError, ValueError):
            pass

        for dim, values in profile.items():
            profile[dim] = list(dict.fromkeys(values))
        return profile

    def score_match(
        self,
        case_tags: dict[str, list[str]],
        query_profile: dict[str, list[str]] | None,
        *,
        problem_type: str = "",
    ) -> tuple[float, list[dict[str, str]], dict[str, float]]:
        dim_scores: dict[str, float] = {}
        matched_dims: list[dict[str, str]] = []
        score = 0.0

        if problem_type:
            text_problem = case_tags.get("problem_type") or []
            if "queue_overflow" in text_problem and any(
                k in problem_type for k in ("溢出", "溢流", "排队")
            ):
                w = self.match_weights.get("problem_type", 3.0)
                score += w
                dim_scores["problem_type"] = w
                matched_dims.append(
                    {"key": "problem_type", "label": "问题形态：排队溢出"}
                )

        if not query_profile:
            return score, matched_dims, dim_scores

        for dimension, query_values in query_profile.items():
            case_values = case_tags.get(dimension) or []
            overlap = [v for v in query_values if v in case_values]
            if not overlap:
                continue
            weight = self.match_weights.get(dimension, 1.0)
            dim_score = weight * min(len(overlap), 2) / max(len(query_values), 1)
            dim_score = min(weight, dim_score + weight * 0.25 * (len(overlap) - 1))
            score += dim_score
            dim_scores[dimension] = dim_score
            dim_spec = self._dimensions.get(dimension) or {}
            labels = [
                (dim_spec.get(v) or {}).get("label") or v for v in overlap[:2]
            ]
            group_label = self.dimension_labels.get(dimension, dimension)
            matched_dims.append(
                {
                    "key": dimension,
                    "label": f"{group_label}：{'、'.join(labels)}",
                }
            )

        return score, matched_dims, dim_scores

    def is_high_similarity(self, score: float) -> bool:
        return score >= self.high_threshold
