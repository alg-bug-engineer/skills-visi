"""Reusable overlap-structure detection for timing plans."""

from __future__ import annotations

from typing import Any


from preprocessing.timing.dir8_encoding import DIR8_LABELS
TURN_DIR_LABELS = {
    0: "掉头",
    1: "左转",
    2: "直行",
    3: "右转",
}


def detect_overlap_structure(stage_defs: list[dict[str, Any]]) -> dict[str, Any]:
    """识别方案中的搭接结构，并以现状方案绿灯为参照计算保形特征."""
    n = len(stage_defs)
    empty: dict[str, Any] = {"depth_terms": [], "ratio_groups": [], "slice_stage_idxs": []}
    if n < 2:
        return empty

    mov_sets = stage_movement_sets(stage_defs)
    g0 = [_to_float(stage.get("history_green_s")) for stage in stage_defs]

    mov_stages: dict[str, list[int]] = {}
    for idx, movs in enumerate(mov_sets):
        for mov in movs:
            mov_stages.setdefault(mov, []).append(idx)

    arcs: dict[str, tuple[int, int]] = {}
    for mov, idxs in mov_stages.items():
        arc = cyclic_arc(idxs, n)
        if arc is not None and arc[1] < n:
            arcs[mov] = arc

    def history_sum(idxs: list[int]) -> float | None:
        total = 0.0
        for j in idxs:
            if g0[j] is None or g0[j] <= 0:
                return None
            total += float(g0[j])
        return total

    depth_terms: list[dict[str, Any]] = []
    seen_pairs: dict[tuple[frozenset[int], frozenset[int]], dict[str, Any]] = {}
    slice_stage_idxs: set[int] = set()
    for mov, arc in arcs.items():
        m_set = set(arc_stage_seq(arc, n))
        parent: tuple[str, tuple[int, int]] | None = None
        for other, other_arc in arcs.items():
            if other == mov:
                continue
            other_set = set(arc_stage_seq(other_arc, n))
            if m_set < other_set and (parent is None or other_arc[1] < parent[1][1]):
                parent = (other, other_arc)
        if parent is None:
            continue
        parent_seq = arc_stage_seq(parent[1], n)
        offset = parent_seq.index(arc[0])
        late_stages = parent_seq[:offset]
        early_stages = parent_seq[offset + arc[1]:]
        if not late_stages and not early_stages:
            continue
        pair_key = (frozenset(m_set), frozenset(parent_seq))
        if pair_key in seen_pairs:
            seen_pairs[pair_key]["labels"].append(overlap_movement_label(mov))
            continue
        parent_total = history_sum(parent_seq)
        if parent_total is None or parent_total <= 0:
            continue
        term = {
            "labels": [overlap_movement_label(mov)],
            "movement_stages": sorted(m_set),
            "parent_stages": parent_seq,
            "late_stages": late_stages,
            "early_stages": early_stages,
            "ref_late_ratio": sum(float(g0[j]) for j in late_stages) / parent_total,
            "ref_early_ratio": sum(float(g0[j]) for j in early_stages) / parent_total,
        }
        seen_pairs[pair_key] = term
        depth_terms.append(term)
        slice_stage_idxs.update(late_stages)
        slice_stage_idxs.update(early_stages)

    parent_uf = list(range(n))

    def find(x: int) -> int:
        while parent_uf[x] != x:
            parent_uf[x] = parent_uf[parent_uf[x]]
            x = parent_uf[x]
        return x

    for i in range(n):
        j = (i + 1) % n
        if i != j and mov_sets[i] & mov_sets[j]:
            parent_uf[find(i)] = find(j)

    components: dict[int, list[int]] = {}
    for i in range(n):
        components.setdefault(find(i), []).append(i)

    ratio_groups: list[dict[str, Any]] = []
    for comp in components.values():
        if len(comp) < 2:
            continue
        arc = cyclic_arc(comp, n)
        if arc is None:
            continue
        comp_seq = arc_stage_seq(arc, n)
        comp_total = history_sum(comp_seq)
        if comp_total is None or comp_total <= 0:
            continue
        ratio_groups.append(
            {
                "stages": comp_seq,
                "ref_ratios": [float(g0[j]) / comp_total for j in comp_seq],
            }
        )

    return {
        "depth_terms": depth_terms,
        "ratio_groups": ratio_groups,
        "slice_stage_idxs": sorted(slice_stage_idxs),
    }


def structure_stage_indices_to_nos(
    structure: dict[str, Any],
    stage_nos: list[int | None],
) -> dict[str, Any]:
    """Return a persistence-friendly copy using stage_no fields."""
    out = {
        "depth_terms": [],
        "ratio_groups": [],
        "slice_stage_nos": [
            stage_nos[idx]
            for idx in structure.get("slice_stage_idxs") or []
            if 0 <= int(idx) < len(stage_nos) and stage_nos[int(idx)] is not None
        ],
    }
    for term in structure.get("depth_terms") or []:
        item = dict(term)
        for key in ("movement_stages", "parent_stages", "late_stages", "early_stages"):
            item[key.replace("_stages", "_stage_nos")] = _idxs_to_stage_nos(term.get(key), stage_nos)
        out["depth_terms"].append(item)
    for group in structure.get("ratio_groups") or []:
        item = dict(group)
        item["stage_nos"] = _idxs_to_stage_nos(group.get("stages"), stage_nos)
        out["ratio_groups"].append(item)
    return out


def structure_stage_nos_to_indices(
    structure: dict[str, Any],
    stage_no_to_idx: dict[int, int],
) -> dict[str, Any]:
    """Convert persisted stage_no fields back to optimizer stage indices."""
    out = {
        "depth_terms": [],
        "ratio_groups": [],
        "slice_stage_idxs": [
            stage_no_to_idx[int(no)]
            for no in structure.get("slice_stage_nos") or []
            if _to_int(no) in stage_no_to_idx
        ],
    }
    for term in structure.get("depth_terms") or []:
        item = dict(term)
        for key in ("movement", "parent", "late", "early"):
            nos_key = f"{key}_stage_nos"
            idx_key = f"{key}_stages"
            item[idx_key] = _stage_nos_to_idxs(term.get(nos_key), stage_no_to_idx)
        out["depth_terms"].append(item)
    for group in structure.get("ratio_groups") or []:
        item = dict(group)
        item["stages"] = _stage_nos_to_idxs(group.get("stage_nos"), stage_no_to_idx)
        out["ratio_groups"].append(item)
    return out


def stage_movement_sets(stage_defs: list[dict[str, Any]]) -> list[set[str]]:
    """各阶段放行流向集合：机动车 movementKey + 行人 p{dir8No}."""
    out: list[set[str]] = []
    for stage in stage_defs:
        movs = set(stage.get("movements") or [])
        movs.update(f"p{int(d)}" for d in stage.get("ped_dirs") or [] if _to_int(d) is not None)
        out.append(movs)
    return out


def cyclic_arc(indices: list[int], n: int) -> tuple[int, int] | None:
    """判断阶段索引集合是否为环上连续弧，返回 (起点索引, 弧长)，否则 None."""
    s = set(indices)
    if not s or n <= 0:
        return None
    for start in sorted(s):
        seq = {(start + k) % n for k in range(len(s))}
        if seq == s:
            return (start, len(s))
    return None


def arc_stage_seq(arc: tuple[int, int], n: int) -> list[int]:
    return [(arc[0] + k) % n for k in range(arc[1])]


def overlap_movement_label(key: str) -> str:
    if key.startswith("atom:"):
        parts = key.split(":")
        return parts[1] if len(parts) >= 2 and parts[1] else key
    if key.startswith("p"):
        return f"行人{DIR8_LABELS.get(_to_int(key[1:]) or 0, key[1:])}"
    if key.startswith("d") and "_t" in key:
        left, _, right = key.partition("_t")
        return f"{DIR8_LABELS.get(_to_int(left[1:]) or 0, left[1:])}-{TURN_DIR_LABELS.get(_to_int(right) or -1, right)}"
    return key


def _idxs_to_stage_nos(values: Any, stage_nos: list[int | None]) -> list[int]:
    out: list[int] = []
    for value in values or []:
        idx = _to_int(value)
        if idx is None or idx < 0 or idx >= len(stage_nos):
            continue
        stage_no = stage_nos[idx]
        if stage_no is not None:
            out.append(int(stage_no))
    return out


def _stage_nos_to_idxs(values: Any, stage_no_to_idx: dict[int, int]) -> list[int]:
    out: list[int] = []
    for value in values or []:
        stage_no = _to_int(value)
        if stage_no in stage_no_to_idx:
            out.append(stage_no_to_idx[stage_no])
    return out


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
