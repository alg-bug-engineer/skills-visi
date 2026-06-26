"""Load traffic thresholds from YAML."""

from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from intersection_agent.config import get_settings

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_CHECKLIST_THRESHOLDS = (
    _BACKEND_ROOT.parent / "docs" / "intersection" / "common" / "thresholds.yaml"
)
_EXTENSIONS_PATH = _BACKEND_ROOT / "rules" / "thresholds_extensions.yaml"
_LEGACY_PATH = _BACKEND_ROOT / "rules" / "thresholds.yaml"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


@lru_cache
def load_thresholds() -> dict[str, Any]:
    """Return cached thresholds: checklist真源 + backend extensions."""
    if _CHECKLIST_THRESHOLDS.is_file():
        base = _load_yaml(_CHECKLIST_THRESHOLDS)
    else:
        base = _load_yaml(get_settings().rules_dir / "thresholds.yaml")

    extensions = _load_yaml(_EXTENSIONS_PATH)
    if not extensions and _LEGACY_PATH.is_file() and not _CHECKLIST_THRESHOLDS.is_file():
        return _load_yaml(_LEGACY_PATH)

    return _deep_merge(base, extensions)


def threshold_value(*path: str, default: float) -> float:
    """Read nested threshold, e.g. threshold_value('delay', 'excess_delay_s')."""
    node: Any = load_thresholds()
    for key in path:
        if not isinstance(node, dict):
            return default
        node = node.get(key)
    if node is None:
        return default
    return float(node)
