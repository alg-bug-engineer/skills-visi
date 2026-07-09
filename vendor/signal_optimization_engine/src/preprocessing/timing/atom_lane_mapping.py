"""Signal-atom to lane-group mapping.

The mapper is intentionally conservative: it only upgrades to lane-group flows
when channelization and source evidence are strong enough, and otherwise returns
a low-confidence mapping that callers can fall back from.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from preprocessing.timing.dir8_encoding import DIR8_NO_TO_CN, DIR_CN_TO_DIR8_NO
from preprocessing.timing.lane_cluster import lane_group_key
TURN_TO_TURN_DIR_NO = {"掉": 0, "左": 1, "直": 2, "右": 3}
ELEMENT_TURNS = frozenset("直左右掉")
VENDOR_TAG_SUFFIXES = ("直左掉", "左直右掉", "直左右掉", "左右掉", "左掉", "直掉", "直左")


@dataclass(frozen=True)
class SignalAtom:
    signalAtom: str
    direction: str
    turnSet: list[str]
    vendorTag: str
    sourceType: str
    sourceKey: str
    dir8No: int | None
    turnDirNo: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AtomLaneMapping:
    signalAtom: str
    sourceKey: str
    movementKey: str
    laneGroupIds: list[str]  # stores laneGroupKey values (link-scoped unique ids)
    laneNos: list[int]
    confidence: str
    score: int
    method: str
    evidence: list[str]
    fallbackTurnDirNo: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_signal_atom(
    atom: str,
    *,
    source_key: str = "",
    dir8_no: int | None = None,
    turn_dir_no: int | None = None,
) -> SignalAtom:
    direction, suffix = split_atom(atom)
    turn_set = [turn for turn in "直左右掉" if turn in suffix]
    vendor_tag = suffix if is_vendor_lane_tag(atom) else ""
    inferred_dir = dir8_no if dir8_no is not None else DIR_CN_TO_DIR8_NO.get(direction)
    inferred_turn = turn_dir_no if turn_dir_no is not None else _primary_turn_dir_no(turn_set)
    source_type = "overlap" if source_key.startswith("OP") else "phase" if source_key.startswith("P") else ""
    return SignalAtom(
        signalAtom=atom,
        direction=direction,
        turnSet=turn_set,
        vendorTag=vendor_tag,
        sourceType=source_type,
        sourceKey=source_key,
        dir8No=inferred_dir,
        turnDirNo=inferred_turn,
    )


def split_atom(atom: str) -> tuple[str, str]:
    for candidate in sorted(DIR_CN_TO_DIR8_NO, key=len, reverse=True):
        if atom.startswith(candidate):
            return candidate, atom[len(candidate) :]
    i = 0
    while i < len(atom) and atom[i] in "东南西北":
        i += 1
    return atom[:i], atom[i:]


def is_vendor_lane_tag(atom: str) -> bool:
    direction, suffix = split_atom(atom)
    if not direction or not suffix or any(ch not in ELEMENT_TURNS for ch in suffix):
        return False
    return suffix == "掉" or suffix.endswith(VENDOR_TAG_SUFFIXES)


def movement_key_for_atom(atom: str, source_key: str = "") -> str:
    safe_source = source_key or "NA"
    return f"atom:{atom}:{safe_source}"


def collect_fallback_lane_nos(atom: dict[str, Any], lane_groups: list[dict[str, Any]]) -> list[int]:
    """当严格车道簇匹配失败时，按进口方向 + 转向能力交集回退收集 lane_no。"""
    parsed = parse_signal_atom(
        str(atom.get("signalAtom") or atom.get("signal_atom") or ""),
        source_key=str(atom.get("sourceKey") or atom.get("source_key") or ""),
        dir8_no=_to_int(atom.get("dir8No") if "dir8No" in atom else atom.get("dir8_no")),
        turn_dir_no=_to_int(atom.get("turnDirNo") if "turnDirNo" in atom else atom.get("turn_dir_no")),
    )
    if parsed.dir8No is None or not parsed.turnSet:
        return []
    turn_set = set(parsed.turnSet)
    lane_nos: list[int] = []
    for group in lane_groups:
        if _to_int(group.get("dir8No")) != parsed.dir8No:
            continue
        caps = {str(cap) for cap in group.get("capabilities") or []}
        if turn_set & caps:
            for raw_lane_no in group.get("laneNos") or []:
                lane_no = _to_int(raw_lane_no)
                if lane_no is not None:
                    lane_nos.append(lane_no)
    return sorted(set(lane_nos))


def map_signal_atoms_to_lane_groups(
    atoms: list[dict[str, Any]],
    lane_groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    parsed_atoms = [
        parse_signal_atom(
            str(atom.get("signalAtom") or atom.get("atom") or ""),
            source_key=str(atom.get("sourceKey") or ""),
            dir8_no=_to_int(atom.get("dir8No")),
            turn_dir_no=_to_int(atom.get("turnDirNo")),
        )
        for atom in atoms
        if atom.get("signalAtom") or atom.get("atom")
    ]
    return [
        resolve_atom_lane_mapping(atom.to_dict(), lane_groups).to_dict()
        for atom in parsed_atoms
    ]


def resolve_atom_lane_mapping(
    atom: dict[str, Any],
    lane_groups: list[dict[str, Any]],
) -> AtomLaneMapping:
    signal_atom = str(atom.get("signalAtom") or "")
    source_key = str(atom.get("sourceKey") or "")
    parsed = parse_signal_atom(
        signal_atom,
        source_key=source_key,
        dir8_no=_to_int(atom.get("dir8No")),
        turn_dir_no=_to_int(atom.get("turnDirNo")),
    )
    candidates = [
        group
        for group in lane_groups
        if _to_int(group.get("dir8No")) == parsed.dir8No
        and _capabilities_cover(parsed.turnSet, group.get("capabilities") or [])
    ]
    movement_key = movement_key_for_atom(signal_atom, source_key)
    if not candidates:
        return AtomLaneMapping(
            signalAtom=signal_atom,
            sourceKey=source_key,
            movementKey=movement_key,
            laneGroupIds=[],
            laneNos=[],
            confidence="low",
            score=0,
            method="fallback_turn_bucket",
            evidence=["no_lane_group_candidate"],
            fallbackTurnDirNo=parsed.turnDirNo,
        )

    scored = sorted(
        ((_score_candidate(parsed, group), group) for group in candidates),
        key=lambda item: (
            item[0],
            _to_int(item[1].get("linkLaneTotal")) or 0,
            lane_group_key(item[1]),
        ),
    )
    score, best = scored[-1]
    evidence = _candidate_evidence(parsed, best)
    confidence = "high" if score >= 70 and len(candidates) == 1 else "medium" if score >= 40 else "low"
    return AtomLaneMapping(
        signalAtom=signal_atom,
        sourceKey=source_key,
        movementKey=movement_key,
        laneGroupIds=[lane_group_key(best)],
        laneNos=[int(x) for x in best.get("laneNos") or [] if _to_int(x) is not None],
        confidence=confidence,
        score=score,
        method="lane_group_candidate",
        evidence=evidence,
        fallbackTurnDirNo=parsed.turnDirNo,
    )


def mapping_summary(mappings: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"high": 0, "medium": 0, "low": 0, "blocked": 0}
    low_atoms: list[str] = []
    movement_keys: list[str] = []
    for mapping in mappings:
        confidence = str(mapping.get("confidence") or "low")
        counts[confidence] = counts.get(confidence, 0) + 1
        if confidence in {"low", "blocked"}:
            low_atoms.append(str(mapping.get("signalAtom") or ""))
        if mapping.get("movementKey"):
            movement_keys.append(str(mapping["movementKey"]))
    return {
        "schemaVersion": "atom_lane_mapping_v1",
        "summary": counts,
        "lowConfidenceAtoms": low_atoms,
        "movementKeys": movement_keys,
    }


def _score_candidate(atom: SignalAtom, group: dict[str, Any]) -> int:
    score = 0
    caps = [str(x) for x in group.get("capabilities") or []]
    cap_set = set(caps)
    turn_set = set(atom.turnSet)
    family = _group_family(group)
    if turn_set == cap_set:
        score += 40
    elif turn_set <= cap_set:
        score += 25
    elif _turns_match_left_family(turn_set, family, cap_set):
        score += 22
    if atom.sourceKey.startswith("OP"):
        score += 10
    if group.get("separated"):
        score += 20
    link_lane_total = _to_int(group.get("linkLaneTotal")) or 0
    if link_lane_total:
        score += min(20, link_lane_total * 2)
    if atom.vendorTag and _vendor_matches_group(atom.vendorTag, group):
        score += 25
    return score


def _candidate_evidence(atom: SignalAtom, group: dict[str, Any]) -> list[str]:
    evidence = ["capability_match"]
    if atom.sourceKey:
        evidence.append("source_key")
    if atom.sourceKey.startswith("OP"):
        evidence.append("overlap_source")
    if group.get("separated"):
        evidence.append("separated_cluster")
    if atom.vendorTag:
        evidence.append("vendor_tag")
    return evidence


def _vendor_matches_group(vendor_tag: str, group: dict[str, Any]) -> bool:
    kind = str(group.get("clusterKind") or "")
    caps = set(str(x) for x in group.get("capabilities") or [])
    family = _group_family(group)
    if vendor_tag == "掉":
        return "掉" in caps or family == "left"
    if vendor_tag.endswith("左掉"):
        return "掉" in caps or kind == "mixed_left_uturn" or family == "left"
    if vendor_tag.endswith("直左"):
        return "直" in caps
    if vendor_tag.endswith("直掉"):
        return "掉" in caps or "直" in caps
    return True


def _capabilities_cover(turn_set: list[str], caps: list[Any]) -> bool:
    if not turn_set:
        return False
    cap_set = {str(cap) for cap in caps}
    turns = set(turn_set)
    if turns <= cap_set:
        return True
    # 厂商组合如 “直左” 可用于标记一股直行物理流，允许候选族匹配。
    if "直" in turns and "直" in cap_set:
        return True
    if "掉" in turns and ("掉" in cap_set or "左" in cap_set):
        return True
    if "左" in turns and "掉" in cap_set:
        return True
    return False


def _group_family(group: dict[str, Any]) -> str:
    family = str(group.get("primaryFamily") or "")
    if family:
        return "left" if family == "uturn" else family
    caps = {str(cap) for cap in group.get("capabilities") or []}
    if "左" in caps or "掉" in caps:
        return "left"
    if "直" in caps:
        return "through"
    if "右" in caps:
        return "right"
    return "other"


def _turns_match_left_family(turns: set[str], family: str, caps: set[str]) -> bool:
    return family == "left" and bool(turns & {"左", "掉"}) and bool(caps & {"左", "掉"})


def _primary_turn_dir_no(turn_set: list[str]) -> int | None:
    if "掉" in turn_set:
        return 0
    for turn in ("左", "直", "右"):
        if turn in turn_set:
            return TURN_TO_TURN_DIR_NO[turn]
    return None


def _to_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
