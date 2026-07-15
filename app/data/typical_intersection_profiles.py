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


def normalize_screening_anchor(raw: Any) -> dict[str, Any] | None:
    """筛查尖峰锚点：溢流判定优先于工单时段周型剖面。

    硬门槛：目标与直接下游都必须具备排队样本；缺下游排队则整锚点作废
   （与 cycle-signal 筛选「下游必须有排队」一致，禁止仅凭饱和度入典型）。
    """
    if not isinstance(raw, dict):
        return None
    try:
        queue_m = float(raw.get("queue_length_m"))
        storage_m = float(raw.get("storage_length_m"))
    except (TypeError, ValueError):
        return None
    if queue_m < 0 or storage_m <= 0:
        return None
    try:
        ratio = float(raw.get("queue_ratio"))
    except (TypeError, ValueError):
        ratio = round(queue_m / storage_m, 4)
    if ratio < 0:
        return None

    down_queue = _optional_float(raw.get("downstream_queue_length_m"))
    down_storage = _optional_float(raw.get("downstream_storage_length_m"))
    down_ratio = _optional_float(raw.get("downstream_queue_ratio"))
    if down_ratio is None and down_queue is not None and down_storage is not None and down_storage > 0:
        down_ratio = round(down_queue / down_storage, 4)
    # 典型 Case 闸门：下游排队样本不可缺
    if down_queue is None and down_ratio is None:
        logger.warning(
            "screening_anchor 缺少下游排队，已拒绝入典型 case_id=%s",
            raw.get("case_id"),
        )
        return None

    return {
        "queue_length_m": round(queue_m, 4),
        "storage_length_m": round(storage_m, 4),
        "queue_ratio": round(ratio, 4),
        "downstream_queue_length_m": down_queue,
        "downstream_storage_length_m": down_storage,
        "downstream_queue_ratio": down_ratio,
        "event_date": str(raw.get("event_date") or "").strip() or None,
        "peak_time": str(raw.get("peak_time") or "").strip() or None,
        "case_id": str(raw.get("case_id") or "").strip() or None,
        "source": str(raw.get("source") or "screening_anchor").strip(),
    }


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def validate_typical_profiles(*, path: str | None = None) -> list[str]:
    """校验典型配置：带 screening_anchor 的条目必须通过下游排队闸门。"""
    errors: list[str] = []
    for profile in list_typical_profiles(path=path):
        pid = str(profile.get("id") or "?")
        metrics = profile.get("metrics") or {}
        raw_anchor = metrics.get("screening_anchor") or profile.get("screening_anchor")
        if not raw_anchor:
            continue
        if normalize_screening_anchor(raw_anchor) is None:
            errors.append(f"{pid}: screening_anchor 缺少下游排队，不得作为典型 Case")
    return errors


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
            "screening_anchor": normalize_screening_anchor(
                metrics.get("screening_anchor") or profile.get("screening_anchor")
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
            "screening_anchor": None,
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
        "screening_anchor": normalize_screening_anchor(profile.get("screening_anchor")),
    }


def apply_screening_anchor_to_metrics(
    metrics: dict[str, Any],
    anchor: dict[str, Any] | None,
) -> dict[str, Any]:
    """筛查尖峰溢流优先：覆盖队列主证据，周型窗值保留为审计字段。"""
    if not metrics or not anchor:
        return metrics
    ratio = float(anchor.get("queue_ratio") or 0)
    if ratio < 0.8:
        return metrics
    out = dict(metrics)
    out["window_queue_length_m"] = out.get("queue_length_m")
    out["window_storage_length_m"] = out.get("storage_length_m")
    try:
        wq = out.get("queue_length_m")
        ws = out.get("storage_length_m")
        out["window_queue_ratio"] = (
            round(float(wq) / float(ws), 4) if wq is not None and ws and float(ws) > 0 else None
        )
    except (TypeError, ValueError):
        out["window_queue_ratio"] = None
    out["queue_length_m"] = float(anchor["queue_length_m"])
    out["storage_length_m"] = float(anchor["storage_length_m"])
    out["queue_available"] = True
    out["storage_available"] = True
    out["queue_statistic"] = "screening_event_peak"
    out["queue_source"] = "screening_anchor"
    out["metric_selection_policy"] = "screening_event_anchor"
    out["statistic_scope"] = "screening_event"
    out["screening_anchor"] = dict(anchor)
    out["screening_queue_ratio"] = ratio
    if anchor.get("peak_time"):
        out["screening_peak_time"] = anchor.get("peak_time")
    if anchor.get("event_date"):
        out["screening_event_date"] = anchor.get("event_date")
    return out
