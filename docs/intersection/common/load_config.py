"""Load shared intersection skillpack configuration (YAML single source of truth)."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

_COMMON_DIR = Path(__file__).resolve().parent


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to load intersection skillpack config") from exc
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid YAML root in {path}")
    return data


@functools.lru_cache(maxsize=1)
def load_thresholds() -> dict[str, Any]:
    return _read_yaml(_COMMON_DIR / "thresholds.yaml")


@functools.lru_cache(maxsize=1)
def load_scene_cognition_checklist() -> list[dict[str, Any]]:
    data = _read_yaml(_COMMON_DIR / "scene_cognition_checklist.yaml")
    return list(data.get("items") or [])


@functools.lru_cache(maxsize=1)
def load_diagnosis_checklist() -> list[dict[str, Any]]:
    data = _read_yaml(_COMMON_DIR / "diagnosis_checklist.yaml")
    return list(data.get("items") or [])


@functools.lru_cache(maxsize=1)
def load_scene_type_rules() -> dict[str, Any]:
    return _read_yaml(_COMMON_DIR / "scene_type_rules.yaml")


@functools.lru_cache(maxsize=1)
def load_cause_dimension_map() -> dict[str, str]:
    data = _read_yaml(_COMMON_DIR / "cause_dimension_map.yaml")
    mapping = data.get("issue_to_dimension") or {}
    return {str(key): str(value) for key, value in mapping.items()}


@functools.lru_cache(maxsize=1)
def load_diagnosis_cause_dimensions() -> dict[str, dict[str, float]]:
    """Return issue_code -> cause dimension weights from diagnosis checklist."""
    weights: dict[str, dict[str, float]] = {}
    for item in load_diagnosis_checklist():
        item_weights = item.get("cause_dimensions") or {}
        if not isinstance(item_weights, dict):
            continue
        issue_codes = item.get("issue_codes") or []
        for code in issue_codes:
            bucket = weights.setdefault(str(code), {})
            for dimension, value in item_weights.items():
                bucket[str(dimension)] = bucket.get(str(dimension), 0.0) + float(value)
    return weights


def threshold(path: str, default: float | int | None = None) -> float:
    """Resolve dotted threshold path, e.g. ``saturation.oversaturation``."""
    node: Any = load_thresholds()
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            if default is not None:
                return float(default)
            raise KeyError(f"Unknown threshold: {path}")
        node = node[part]
    return float(node)


def diagnosis_checklist_by_id() -> dict[str, dict[str, Any]]:
    return {str(item["item_id"]): item for item in load_diagnosis_checklist()}


def scene_cognition_checklist_by_id() -> dict[str, dict[str, Any]]:
    return {str(item["item_id"]): item for item in load_scene_cognition_checklist()}


def resolve_scene_type(profile: dict[str, Any]) -> str:
    """Pick scene type using scene_type_rules.yaml match conditions."""
    rules = load_scene_type_rules()
    scene_types = rules.get("scene_types") or {}
    scope = profile.get("scope") if isinstance(profile.get("scope"), dict) else {}
    level = str(scope.get("level") or "intersection")
    context = profile.get("context") if isinstance(profile.get("context"), dict) else {}
    tags = set(profile.get("context_tags") or [])
    for key in ("time_period", "weather"):
        if context.get(key):
            tags.add(str(context[key]))
    for key in ("poi", "events", "complaints", "special_requests"):
        for item in context.get(key) or []:
            tags.add(str(item))
    if context.get("emergency"):
        tags.add("emergency")

    explicit = profile.get("scene_type")
    if explicit and explicit in scene_types:
        return str(explicit)

    matched: list[tuple[int, str]] = []
    for name, spec in scene_types.items():
        match = spec.get("match") or {}
        score = 0
        if match.get("default"):
            score = 1
        if match.get("scope_level") == level:
            score += 3
        wanted_tags = set(match.get("context_tags") or [])
        if wanted_tags.intersection(tags):
            score += 2
        if match.get("context_flag") == "emergency" and context.get("emergency"):
            score += 4
        if score > 0:
            matched.append((score, name))
    if matched:
        matched.sort(key=lambda item: item[0], reverse=True)
        return matched[0][1]
    return "单点配时优化"


def build_profile_evidence_refs(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten profile evidence + metrics_insights facts for downstream diagnosis."""
    refs: list[dict[str, Any]] = []
    for index, item in enumerate(profile.get("evidence") or []):
        if not isinstance(item, dict):
            continue
        refs.append(
            {
                "ref_id": item.get("fact_id") or f"profile.evidence.{index}",
                "kind": "profile_evidence",
                "metric": item.get("metric"),
                "value": item.get("value"),
                "checklist_item_id": item.get("checklist_item_id"),
                "source": item.get("source"),
            }
        )
    insights = profile.get("metrics_insights") if isinstance(profile.get("metrics_insights"), dict) else {}
    for index, fact in enumerate(insights.get("facts") or []):
        if not isinstance(fact, dict):
            text = str(fact)
            refs.append({"ref_id": f"metrics_insights.facts.{index}", "kind": "metrics_fact", "text": text})
            continue
        refs.append(
            {
                "ref_id": fact.get("fact_id") or f"metrics_insights.facts.{index}",
                "kind": "metrics_fact",
                "text": fact.get("text") or str(fact),
                "checklist_item_id": fact.get("checklist_item_id"),
                "metric": fact.get("metric"),
            }
        )
    return refs
