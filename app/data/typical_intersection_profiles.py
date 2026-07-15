"""典型路口取数策略配置。

命中 profile 时仅覆盖「如何从 PG 聚合」；数值仍实时查询。
未命中则由调用方继续走项目固定逻辑。
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT
from app.trace.topology import resolve_dir8_turn

logger = logging.getLogger(__name__)

DEFAULT_PROFILE_PATH = PROJECT_ROOT / "data" / "typical_intersections.json"
ALLOWED_QUEUE_FIELDS = frozenset({"queue_len_avg", "queue_len_max"})
ALLOWED_SELECTIONS = frozenset({"cross_week_peak", "cross_week_mean"})


def normalize_selection(value: Any, *, default: str) -> str:
    raw = str(value or "").strip()
    return raw if raw in ALLOWED_SELECTIONS else default


def _norm_text(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "")


def _direction_aliases(direction: str) -> set[str]:
    raw = str(direction or "").strip()
    if not raw:
        return set()
    aliases = {raw, _norm_text(raw)}
    try:
        dir8, _ = resolve_dir8_turn(raw, "直行")
        from app.trace.topology import DIR8_ENTRY, DIRECTION_MOVEMENT

        entry = DIR8_ENTRY.get(int(dir8))
        if entry:
            aliases.add(entry)
            aliases.add(_norm_text(entry))
        for label, pair in DIRECTION_MOVEMENT.items():
            if int(pair[0]) == int(dir8):
                aliases.add(label)
                aliases.add(_norm_text(label))
    except Exception:  # noqa: BLE001 - 别名失败不阻断匹配
        pass
    return {a for a in aliases if a}


def _movement_aliases(movement: str) -> set[str]:
    raw = str(movement or "").strip()
    if not raw:
        return {"直行", "through", "straight"}
    mapping = {
        "直行": {"直行", "through", "straight"},
        "左转": {"左转", "left", "left_turn"},
        "右转": {"右转", "right", "right_turn"},
        "掉头": {"掉头", "uturn", "u_turn"},
    }
    aliases = {raw, _norm_text(raw)}
    for key, vals in mapping.items():
        if raw == key or _norm_text(raw) in {_norm_text(v) for v in vals}:
            aliases.update(vals)
            aliases.add(key)
    return aliases


@lru_cache(maxsize=4)
def load_typical_intersection_catalog(path: str | None = None) -> dict[str, Any]:
    target = Path(path) if path else DEFAULT_PROFILE_PATH
    if not target.exists():
        logger.warning("典型路口配置不存在 path=%s", target)
        return {"version": 0, "profiles": []}
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"version": 0, "profiles": []}
    profiles = data.get("profiles") or []
    if not isinstance(profiles, list):
        data["profiles"] = []
    return data


def clear_typical_profile_cache() -> None:
    load_typical_intersection_catalog.cache_clear()


def list_typical_profiles(*, path: str | None = None) -> list[dict[str, Any]]:
    catalog = load_typical_intersection_catalog(path)
    return [p for p in (catalog.get("profiles") or []) if isinstance(p, dict)]


def resolve_typical_profile(
    ticket: dict[str, Any] | None,
    *,
    path: str | None = None,
) -> dict[str, Any] | None:
    """按 inter_id + direction + movement 解析典型路口策略。"""
    ticket = ticket or {}
    inter_id = str(ticket.get("inter_id") or "").strip()
    inter_name = str(ticket.get("intersection_name") or "").strip()
    direction = str(ticket.get("direction") or "").strip()
    movement = str(ticket.get("movement") or "直行").strip()
    dir_aliases = _direction_aliases(direction)
    mov_aliases = _movement_aliases(movement)

    for profile in list_typical_profiles(path=path):
        match = profile.get("match") or {}
        if not isinstance(match, dict):
            continue
        mid = str(match.get("inter_id") or "").strip()
        mname = str(match.get("intersection_name") or "").strip()
        if mid and inter_id and mid != inter_id:
            continue
        if not mid and mname and inter_name and mname not in inter_name and inter_name not in mname:
            continue
        if not mid and not mname:
            continue
        if not mid and not inter_name:
            continue

        match_dir = str(match.get("direction") or "").strip()
        match_mov = str(match.get("movement") or "直行").strip()
        if match_dir and dir_aliases.isdisjoint(_direction_aliases(match_dir)):
            continue
        if match_mov and mov_aliases.isdisjoint(_movement_aliases(match_mov)):
            continue

        metrics = dict(profile.get("metrics") or {})
        target_field = str(metrics.get("target_queue_field") or "queue_len_avg")
        down_field = str(metrics.get("downstream_queue_field") or "queue_len_avg")
        peak_field = str(
            metrics.get("downstream_peak_disclose_field")
            or metrics.get("target_queue_field")
            or "queue_len_avg"
        )
        if target_field not in ALLOWED_QUEUE_FIELDS:
            target_field = "queue_len_avg"
        if down_field not in ALLOWED_QUEUE_FIELDS:
            down_field = "queue_len_avg"
        if peak_field not in ALLOWED_QUEUE_FIELDS:
            peak_field = "queue_len_avg"

        return {
            "id": profile.get("id"),
            "label": profile.get("label"),
            "opt_type": profile.get("opt_type"),
            "inherit_project_fixed": bool(metrics.get("inherit_project_fixed")),
            "target_queue_field": target_field,
            "target_selection": normalize_selection(
                metrics.get("target_selection"), default="cross_week_peak"
            ),
            "downstream_queue_field": down_field,
            "downstream_selection": normalize_selection(
                metrics.get("downstream_selection"), default="cross_week_mean"
            ),
            "downstream_peak_disclose_field": peak_field,
            "downstream_approach_queue_avg": bool(
                metrics.get("downstream_approach_queue_avg", True)
            ),
            "raw": profile,
        }
    return None


def metric_options_from_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    """供 load 路径消费的取数选项；无 profile 时返回项目固定默认。"""
    if not profile or profile.get("inherit_project_fixed"):
        return {
            "typical_profile_id": None,
            "target_queue_field": "queue_len_avg",
            "target_selection": "cross_week_peak",
            "downstream_queue_field": "queue_len_avg",
            "downstream_selection": "cross_week_mean",
            "downstream_peak_disclose_field": "queue_len_avg",
            "downstream_approach_queue_avg": False,
            "use_typical_policy": False,
        }
    return {
        "typical_profile_id": profile.get("id"),
        "typical_profile_label": profile.get("label"),
        "typical_opt_type": profile.get("opt_type"),
        "target_queue_field": profile.get("target_queue_field") or "queue_len_avg",
        "target_selection": normalize_selection(
            profile.get("target_selection"), default="cross_week_peak"
        ),
        "downstream_queue_field": profile.get("downstream_queue_field") or "queue_len_avg",
        "downstream_selection": normalize_selection(
            profile.get("downstream_selection"), default="cross_week_mean"
        ),
        "downstream_peak_disclose_field": profile.get("downstream_peak_disclose_field")
        or "queue_len_avg",
        "downstream_approach_queue_avg": bool(profile.get("downstream_approach_queue_avg")),
        "use_typical_policy": True,
    }
