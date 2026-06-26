"""Generated draft from EXP-SCENE-006: 数据冲突与不确定性.

This file is a human-review draft. Do not import it into runtime until reviewed.
"""

from __future__ import annotations

from typing import Any


def check_conflict(profile: dict[str, Any]) -> dict[str, Any]:
    """Draft evaluator generated from expert experience."""
    return {
        "triggered": False,
        "status": "pending_review",
        "summary": "写入 `quality_tags` 或 `uncertainty`，并提示补采下游阻塞、停车占道、公交停靠、慢行冲突或渠化数据。",
        "evidence": [],
        "source_experience_id": "EXP-SCENE-006",
        "requires_human_review": True,
    }
