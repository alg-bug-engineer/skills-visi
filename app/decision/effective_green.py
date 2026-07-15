"""目标转向有效绿：跨搭接阶段求和。"""

from __future__ import annotations

from typing import Any


def movement_key_from_ticket(ticket: dict[str, Any] | None) -> str | None:
    ticket = ticket or {}
    if ticket.get("dir8_code") is not None and ticket.get("turn_dir_no") is not None:
        return f"d{int(ticket['dir8_code'])}_t{int(ticket['turn_dir_no'])}"
    key = ticket.get("movement_key") or ticket.get("target_movement_key")
    return str(key) if key else None


def stage_green_s(stage: dict[str, Any]) -> float:
    for key in ("green_time_s", "greenTime", "green_sec", "greenSec"):
        if stage.get(key) is not None:
            try:
                return float(stage[key])
            except (TypeError, ValueError):
                continue
    timing = stage.get("currentTiming") or {}
    if timing.get("greenSec") is not None:
        try:
            return float(timing["greenSec"])
        except (TypeError, ValueError):
            pass
    return 0.0


def stage_movement_keys(stage: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    mk = stage.get("movement_key") or stage.get("movementKey")
    if mk and str(mk).startswith("d") and "_t" in str(mk):
        keys.add(str(mk))
    for item in stage.get("movements") or []:
        if not isinstance(item, dict):
            continue
        if item.get("movement_key") or item.get("movementKey"):
            keys.add(str(item.get("movement_key") or item.get("movementKey")))
            continue
        if item.get("dir8_code") is not None and item.get("turn_dir_no") is not None:
            keys.add(f"d{int(item['dir8_code'])}_t{int(item['turn_dir_no'])}")
        elif item.get("dir8No") is not None and item.get("turnDirNo") is not None:
            keys.add(f"d{int(item['dir8No'])}_t{int(item['turnDirNo'])}")
    for item in stage.get("phaseDirInfoDTOList") or stage.get("phase_dir_info_list") or []:
        if not isinstance(item, dict):
            continue
        mk = item.get("movementKey") or item.get("movement_key")
        if mk:
            keys.add(str(mk))
        elif item.get("dir8No") is not None and item.get("turnDirNo") is not None:
            keys.add(f"d{int(item['dir8No'])}_t{int(item['turnDirNo'])}")
    return keys


def effective_green_by_movement(stages: list[dict[str, Any]] | None) -> dict[str, float]:
    greens: dict[str, float] = {}
    for stage in stages or []:
        green = stage_green_s(stage)
        for key in stage_movement_keys(stage):
            greens[key] = greens.get(key, 0.0) + green
    return {k: round(v, 4) for k, v in greens.items()}


def compute_target_effective_green_delta(
    *,
    before_stages: list[dict[str, Any]] | None,
    after_stages: list[dict[str, Any]] | None,
    movement_key: str,
) -> dict[str, Any]:
    before_map = effective_green_by_movement(before_stages)
    after_map = effective_green_by_movement(after_stages)
    before_s = float(before_map.get(movement_key, 0.0))
    after_s = float(after_map.get(movement_key, 0.0))
    return {
        "movement_key": movement_key,
        "before_s": round(before_s, 4),
        "after_s": round(after_s, 4),
        "delta_s": round(after_s - before_s, 4),
        "before_by_movement": before_map,
        "after_by_movement": after_map,
    }


def max_stage_change_ratio(
    before_stages: list[dict[str, Any]] | None,
    after_stages: list[dict[str, Any]] | None,
) -> float:
    before = list(before_stages or [])
    after = list(after_stages or [])
    by_id: dict[str, float] = {}
    for idx, stage in enumerate(before):
        key = str(stage.get("phase_stage_id") or stage.get("phaseStageId") or idx)
        by_id[key] = stage_green_s(stage)
    worst = 0.0
    for idx, stage in enumerate(after):
        key = str(stage.get("phase_stage_id") or stage.get("phaseStageId") or idx)
        base = by_id.get(key)
        if base is None or base <= 0:
            continue
        ratio = abs(stage_green_s(stage) - base) / base
        worst = max(worst, ratio)
    return round(worst, 4)
