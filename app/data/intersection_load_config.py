"""Intersection checklist/threshold config (adapted from references/intersection/common)."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

_CONFIG_DIR = Path(__file__).resolve().parent / "intersection_config"


def _read_yaml(path: Path) -> dict[str, Any]:
    import yaml

    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid YAML root in {path}")
    return data


@functools.lru_cache(maxsize=1)
def load_thresholds() -> dict[str, Any]:
    return _read_yaml(_CONFIG_DIR / "thresholds.yaml")


@functools.lru_cache(maxsize=1)
def load_scene_cognition_checklist() -> list[dict[str, Any]]:
    data = _read_yaml(_CONFIG_DIR / "scene_cognition_checklist.yaml")
    return list(data.get("items") or [])


def threshold(path: str, default: float | int | None = None) -> float:
    node: Any = load_thresholds()
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            if default is not None:
                return float(default)
            raise KeyError(f"Unknown threshold: {path}")
        node = node[part]
    return float(node)
