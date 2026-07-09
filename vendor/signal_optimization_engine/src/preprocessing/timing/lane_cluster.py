"""Lane-group extraction for atom-level signal-flow mapping.

The optimization chain needs a physical unit finer than ``dir8No + turnDirNo``.
This module turns channelization payloads from MySQL/PG readers into stable lane
groups that can be matched with signal atoms.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from preprocessing.timing.dir8_encoding import normalize_dir8_no


TURN_CN_TO_EN = {"直": "through", "左": "left", "右": "right", "掉": "uturn"}
TURN_EN_TO_CN = {value: key for key, value in TURN_CN_TO_EN.items()}


@dataclass(frozen=True)
class LaneGroup:
    laneGroupId: str
    laneGroupKey: str
    dir8No: int
    dir8Code: int
    linkId: str
    approachIndex: int
    laneNos: list[int]
    capabilities: list[str]
    clusterKind: str
    primaryFamily: str
    separated: bool
    linkLaneTotal: int
    sourceLaneGroupKeys: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def lane_group_key(group: dict[str, Any] | None) -> str:
    """Stable unique key for a lane group (link-scoped when available)."""
    if not group:
        return ""
    return str(group.get("laneGroupKey") or group.get("laneGroupId") or "")


def build_lane_groups(channelization: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Build contiguous same-capability lane groups from channelization payload."""
    groups: list[LaneGroup] = []
    for approach_index, approach in enumerate((channelization or {}).get("approaches") or [], start=1):
        if str(approach.get("linkRole") or "entrance") != "entrance":
            continue
        dir8_no = normalize_dir8_no(approach.get("dir8Code"))
        if dir8_no is None:
            continue
        approach_groups = _groups_for_approach(dir8_no, approach.get("lanes") or [])
        separated_by_family = _separated_families(approach_groups)
        family_counts: dict[str, int] = {}
        link_id = str(approach.get("linkId") or "")
        link_lane_total = _to_int(approach.get("laneTotal")) or len(approach.get("lanes") or [])
        source_key = _safe_key(link_id) or f"a{approach_index}"
        for group in approach_groups:
            family = _primary_family(group.capabilities)
            family_counts[family] = family_counts.get(family, 0) + 1
            group_id = f"d{dir8_no}_{family}_g{family_counts[family]}"
            group_key = f"{group_id}@{source_key}"
            groups.append(
                LaneGroup(
                    laneGroupId=group_id,
                    laneGroupKey=group_key,
                    dir8No=dir8_no,
                    dir8Code=dir8_no,
                    linkId=link_id,
                    approachIndex=approach_index,
                    laneNos=group.laneNos,
                    capabilities=group.capabilities,
                    clusterKind=group.clusterKind,
                    primaryFamily=family,
                    separated=separated_by_family.get(family, False),
                    linkLaneTotal=link_lane_total,
                    sourceLaneGroupKeys=[group_key],
                )
            )
    return [group.to_dict() for group in groups]


def summarize_lane_groups(lane_groups: list[dict[str, Any]]) -> dict[str, Any]:
    """Return compact separated-cluster flags by direction and family."""
    by_dir: dict[int, dict[str, int]] = {}
    for group in lane_groups:
        dir8_no = _to_int(group.get("dir8No"))
        if dir8_no is None:
            continue
        family = _primary_family([str(x) for x in group.get("capabilities") or []])
        bucket = by_dir.setdefault(dir8_no, {})
        bucket[family] = bucket.get(family, 0) + 1
    return {
        str(dir8_no): {
            "separatedThroughClusters": counts.get("through", 0) >= 2,
            "separatedLeftClusters": counts.get("left", 0) >= 2,
            "separatedUturnClusters": counts.get("uturn", 0) >= 2,
            "separatedRightClusters": counts.get("right", 0) >= 2,
        }
        for dir8_no, counts in sorted(by_dir.items())
    }


@dataclass
class _RawGroup:
    laneNos: list[int]
    capabilities: list[str]
    clusterKind: str


def _groups_for_approach(dir8_code: int, lanes: list[dict[str, Any]]) -> list[_RawGroup]:
    normalized = []
    for idx, lane in enumerate(lanes, start=1):
        lane_type = _to_int(lane.get("laneType"))
        if lane_type not in (None, 0):
            continue
        lane_no = _to_int(lane.get("laneNo")) or idx
        caps = _lane_capabilities(lane)
        if not caps:
            continue
        normalized.append((lane_no, caps))
    normalized.sort(key=lambda item: item[0])

    groups: list[_RawGroup] = []
    for lane_no, caps in normalized:
        if (
            groups
            and groups[-1].capabilities == caps
            and lane_no == groups[-1].laneNos[-1] + 1
        ):
            groups[-1].laneNos.append(lane_no)
        else:
            groups.append(_RawGroup([lane_no], caps, _cluster_kind(caps)))
    _ = dir8_code
    return groups


def _lane_capabilities(lane: dict[str, Any]) -> list[str]:
    drive_dir = _to_int(lane.get("driveDir"))
    caps: list[str] = []
    if drive_dir is not None:
        if drive_dir & 1:
            caps.append("直")
        if drive_dir & 2:
            caps.append("左")
        if drive_dir & 4:
            caps.append("右")
        if drive_dir & 8:
            caps.append("掉")
        return caps

    gb_code = str(lane.get("gbCode") or "")
    if gb_code in {"11", "21", "22", "24", "33"}:
        caps.append("直")
    if gb_code in {"12", "21", "23", "24", "32"}:
        caps.append("左")
    if gb_code in {"13", "22", "23", "24", "34"}:
        caps.append("右")
    if gb_code in {"31", "32", "33", "34"}:
        caps.append("掉")
    if caps:
        return caps

    turns = lane.get("turns") or []
    for turn in ("through", "left", "right", "uturn"):
        if turn in turns:
            caps.append(TURN_EN_TO_CN[turn])
    return caps


def _cluster_kind(caps: list[str]) -> str:
    cap_set = set(caps)
    if cap_set == {"直"}:
        return "through_only"
    if cap_set == {"左"}:
        return "left_only"
    if cap_set == {"右"}:
        return "right_only"
    if cap_set == {"掉"}:
        return "uturn_only"
    if cap_set == {"左", "掉"}:
        return "mixed_left_uturn"
    if "直" in cap_set and "左" in cap_set:
        return "mixed_through_left"
    return "mixed_" + "_".join(TURN_CN_TO_EN[c] for c in caps)


def _primary_family(caps: list[str]) -> str:
    cap_set = set(caps)
    if "掉" in cap_set:
        return "uturn"
    if "左" in cap_set:
        return "left"
    if "直" in cap_set:
        return "through"
    if "右" in cap_set:
        return "right"
    return "other"


def _separated_families(groups: list[_RawGroup]) -> dict[str, bool]:
    counts: dict[str, int] = {}
    for group in groups:
        family = _primary_family(group.capabilities)
        counts[family] = counts.get(family, 0) + 1
    return {family: count >= 2 for family, count in counts.items()}


def _safe_key(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_")


def _to_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
