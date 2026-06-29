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
        cats: list[str] = list(self._cfg.get("base", {}).get("focus_categories", []))
        packs = self._cfg.get("packs", {})
        for pt in problem_types:
            for c in packs.get(pt, {}).get("focus_categories", []):
                if c not in cats:
                    cats.append(c)
        return cats
