"""Resolve problem types into focus-category dimension packs."""

from __future__ import annotations

from pathlib import Path

import yaml


class DimensionPackService:
    """Map NLU problem types to the union of diagnosis focus categories."""

    def __init__(self) -> None:
        path = (
            Path(__file__).resolve().parent.parent
            / "config"
            / "problem_dimension_packs.yaml"
        )
        with open(path, encoding="utf-8") as f:
            self._cfg = yaml.safe_load(f)

    def focus_categories(self, problem_types: list[str]) -> list[str]:
        """Return base categories plus all activated packs' categories (deduped)."""
        return self._union("focus_categories", problem_types)

    def presentation_dimensions(self, problem_types: list[str]) -> list[str]:
        """Return base + activated packs' UI presentation dimensions (deduped).

        Drives the frontend's "show only relevant cards/layers/voice" gating —
        e.g. 配时方案/环图(timing_plan/ring) only surface for 空放(empty_green).
        """
        return self._union("presentation_dimensions", problem_types)

    def _union(self, key: str, problem_types: list[str]) -> list[str]:
        items: list[str] = list(self._cfg.get("base", {}).get(key, []))
        packs = self._cfg.get("packs", {})
        for pt in problem_types:
            for c in packs.get(pt, {}).get(key, []):
                if c not in items:
                    items.append(c)
        return items
