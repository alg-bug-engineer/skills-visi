"""Cap saturation metrics for display and rule evaluation (checklist: min(1.5, V/C))."""

from __future__ import annotations

from typing import Any

SATURATION_CAP = 1.5


def cap_saturation(value: float | None, *, ceiling: float = SATURATION_CAP) -> float | None:
    """Return capped saturation or None."""
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return numeric
    return min(ceiling, numeric)


def cap_saturation_dict(data: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Cap numeric saturation fields in-place and return the same dict."""
    for key in keys:
        if key in data and data[key] is not None:
            capped = cap_saturation(data[key])
            if capped is not None:
                data[key] = capped
    return data
