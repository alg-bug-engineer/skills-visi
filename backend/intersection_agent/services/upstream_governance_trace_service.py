"""上游治理溯源：沿进口道拓扑 geom 单链上溯，定位治理落点（≤5 跳）。"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from intersection_agent.config import Settings, get_settings
from intersection_agent.models.domain import NluResult
from intersection_agent.services.data_fetcher import DataFetcher
from intersection_agent.services.flow_trace_service import (
    FlowTraceService,
    period_type_from_label,
    turn_split_for_upstream,
)
from intersection_agent.services.map_presentation_service import build_upstream_storyboard
from intersection_agent.services.upstream_topology_service import UpstreamTopologyService
from intersection_agent.utils.data_window import DataWindow, build_data_window
from intersection_agent.utils.thresholds_loader import threshold_value
from intersection_agent.utils.traffic_labels import DIR8_LABELS

logger = logging.getLogger(__name__)

_DIR8_TREE_CODE = {0: "N", 1: "NE", 2: "E", 3: "SE", 4: "S", 5: "SW", 6: "W", 7: "NW"}
_APPROACH_TO_DIR8 = {f"{label}进口": code for code, label in DIR8_LABELS.items()}


def is_governable(
    profiles: list[dict[str, Any]], *, full_sat: float, green_util: float
) -> bool:
    """有信控空间 = 非四向全饱和，或任一进口道绿灯利用率有空槽。"""
    if not profiles:
        return False
    has_slack_dir = any((p.get("turn_saturation_max") or 0.0) < full_sat for p in profiles)
    has_empty_green = any(
        p.get("green_util_min") is not None and p["green_util_min"] < green_util
        for p in profiles
    )
    return has_slack_dir or has_empty_green


def build_tree(
    inter_id: str,
    *,
    corridor_dir8: int,
    feeding_dir8: int,
    hop: int,
    window: Any,
    get_profiles: Callable[[str, Any], list[dict[str, Any]]],
    get_upstream: Callable[[str, int, int | None], dict[str, Any] | None],
    full_sat: float,
    green_util: float,
    max_hops: int,
    inter_name: str | None = None,
    turn_no: int | None = None,
) -> dict[str, Any]:
    """沿同一走廊 dir8 单链递归上溯（不再多 arm 分叉）。"""
    profiles = get_profiles(inter_id, window)
    governable = is_governable(profiles, full_sat=full_sat, green_util=green_util)
    node: dict[str, Any] = {
        "inter_id": inter_id,
        "inter_name": inter_name,
        "feeding_dir8": feeding_dir8,
        "hop": hop,
        "approach_profiles": profiles,
        "governable": governable,
        "children": [],
    }
    if governable:
        node["decision"] = "治理落点"
        return node
    if hop >= max_hops:
        node["decision"] = "二跳截止"
        return node

    up = get_upstream(inter_id, corridor_dir8, turn_no if hop == 1 else None)
    if not up:
        node["decision"] = "干线端点"
        return node

    node["decision"] = "继续上溯"
    child = build_tree(
        up["cor_inter_id"],
        corridor_dir8=corridor_dir8,
        feeding_dir8=up["feeding_dir8"],
        hop=hop + 1,
        window=window,
        get_profiles=get_profiles,
        get_upstream=get_upstream,
        full_sat=full_sat,
        green_util=green_util,
        max_hops=max_hops,
        inter_name=up.get("cor_inter_name"),
        turn_no=turn_no,
    )
    node["children"] = [child]
    return node


def _mock_upstream_rows(inter_id: str, dir8: int) -> list[dict[str, Any]]:
    if not inter_id.startswith("mock_"):
        cor_id, name = "mock_hub", "上游枢纽路口"
    elif dir8 == 4:
        cor_id, name = f"mock_gov_{dir8}", "可治理上游路口"
    else:
        cor_id, name = f"mock_up_{dir8}", "经十路与转山西路路口"
    lng = 117.1 + dir8 * 0.01
    lat = 36.65 + dir8 * 0.01
    base = {
        "f_dir8_no": dir8, "turn_dir_no": 2,
        "cor_inter_id": cor_id, "cor_f_dir8_no": dir8,
        "cor_inter_name": name, "cor_lng": lng, "cor_lat": lat,
    }
    return [
        {**base, "cor_turn_dir_no": 2, "flow_share_ratio": 67.0},
        {**base, "cor_turn_dir_no": 1, "flow_share_ratio": 22.0},
        {**base, "cor_turn_dir_no": 3, "flow_share_ratio": 11.0},
    ]


def _collect_points(
    node: dict[str, Any], tree_id: str, approach: str
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if node.get("decision") == "治理落点":
        out.append(
            {
                "tree_id": tree_id,
                "approach": approach,
                "inter_id": node.get("inter_id"),
                "inter_name": node.get("inter_name"),
                "hop": node.get("hop"),
                "feeding_dir8": node.get("feeding_dir8"),
                "decision": node.get("decision"),
                "approach_profiles": node.get("approach_profiles") or [],
            }
        )
    for child in node.get("children") or []:
        out.extend(_collect_points(child, tree_id, approach))
    return out


def _turn_no_for_approach(approach: str, nlu: NluResult | None) -> int | None:
    """从 NLU directions 解析转向号（西左转→1）。"""
    if not nlu or not nlu.directions:
        return None
    code = _APPROACH_TO_DIR8.get(approach)
    if code is None:
        return None
    label = DIR8_LABELS.get(code, "")
    for raw in nlu.directions:
        token = str(raw).strip()
        if not token.startswith(label):
            continue
        if "左" in token:
            return 1
        if "直" in token:
            return 2
        if "右" in token:
            return 3
        if "调" in token:
            return 4
    return None


class UpstreamGovernanceTraceService:
    """对过饱和进口道沿拓扑 geom 单链溯源，定位治理落点，并产出 storyboard。"""

    def __init__(
        self,
        fetcher: DataFetcher | None = None,
        flow_trace: FlowTraceService | None = None,
        topology: UpstreamTopologyService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._fetcher = fetcher or DataFetcher(settings=self._settings)
        self._flow_trace = flow_trace or FlowTraceService(settings=self._settings)
        self._topology = topology or UpstreamTopologyService(settings=self._settings)
        self._full_sat = threshold_value("upstream_trace", "full_saturation", default=0.85)
        self._green_util = threshold_value(
            "upstream_trace", "governable_green_util", default=0.50
        )
        self._max_hops = int(threshold_value("upstream_trace", "max_hops", default=5))
        self._period_label: str | None = None
        self._cognition: dict[str, Any] | None = None
        self._correlate_cache: dict[str, list[dict[str, Any]]] = {}

    async def build(
        self,
        inter_id: str,
        *,
        approach: str | None = None,
        approaches: list[str] | None = None,
        nlu: NluResult | None = None,
        cognition: dict[str, Any] | None = None,
        reference_date: Any = None,
    ) -> dict[str, Any]:
        labels = approaches if approaches is not None else ([approach] if approach else [])
        empty = {"trees": [], "governance_points": [], "storyboard": {"trees": [], "frames": []}}
        if not labels or nlu is None or nlu.time_period is None:
            return empty
        self._period_label = nlu.time_period.label
        self._cognition = cognition
        self._correlate_cache = {}
        window = build_data_window(nlu.time_period, reference_date=reference_date)

        try:
            results = await asyncio.gather(
                *[self._build_one(inter_id, ap, window, cognition, nlu) for ap in labels]
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("upstream_trace build failed: %s", exc)
            return empty

        trees = [t for t in results if t]
        if not trees:
            return empty
        storyboard = build_upstream_storyboard(trees, cognition or {})
        governance_points: list[dict[str, Any]] = []
        for t in trees:
            governance_points.extend(_collect_points(t["root"], t["tree_id"], t["approach"]))
        return {
            "trees": trees,
            "governance_points": governance_points,
            "storyboard": storyboard,
        }

    async def _build_one(
        self,
        inter_id: str,
        approach: str,
        window: DataWindow,
        cognition: dict[str, Any] | None,
        nlu: NluResult | None,
    ) -> dict[str, Any] | None:
        dir8 = _APPROACH_TO_DIR8.get(approach)
        if dir8 is None:
            return None
        turn_no = _turn_no_for_approach(approach, nlu)
        hop1 = await self._get_upstream(inter_id, dir8, window, turn_no=turn_no)
        if not hop1:
            return None
        root_id = hop1["cor_inter_id"]

        profiles_cache: dict[str, list[dict[str, Any]]] = {}
        upstream_cache: dict[tuple[str, int], dict[str, Any] | None] = {}
        await self._prefetch(
            root_id, dir8, hop1["feeding_dir8"], 1, window, profiles_cache, upstream_cache, turn_no
        )

        root = build_tree(
            root_id,
            corridor_dir8=dir8,
            feeding_dir8=hop1["feeding_dir8"],
            hop=1,
            window=window,
            get_profiles=lambda i, _w: profiles_cache.get(i, []),
            get_upstream=lambda i, d, t: upstream_cache.get((i, d)),
            full_sat=self._full_sat,
            green_util=self._green_util,
            max_hops=self._max_hops,
            inter_name=hop1.get("cor_inter_name"),
            turn_no=turn_no,
        )
        root.setdefault("lng", hop1.get("lng"))
        root.setdefault("lat", hop1.get("lat"))
        root["turn_split"] = hop1.get("turn_split") or []
        root["coverage"] = hop1.get("coverage")
        root["hop_path"] = hop1.get("path") or []
        root["path_source"] = hop1.get("path_source")
        _backfill_hop_meta(root, upstream_cache, dir8)

        intersection = (cognition or {}).get("intersection") or {}
        return {
            "tree_id": _DIR8_TREE_CODE.get(dir8, f"T{dir8}"),
            "approach": approach,
            "root": root,
            "target": {
                "inter_id": inter_id,
                "name": intersection.get("name"),
                "approach": approach,
                "dir8_code": dir8,
                "lon": intersection.get("lng") or intersection.get("lon"),
                "lat": intersection.get("lat"),
            },
        }

    async def _prefetch(
        self,
        inter_id: str,
        corridor_dir8: int,
        feeding_dir8: int,
        hop: int,
        window: DataWindow,
        profiles_cache: dict[str, list[dict[str, Any]]],
        upstream_cache: dict[tuple[str, int], dict[str, Any] | None],
        turn_no: int | None,
    ) -> None:
        if inter_id in profiles_cache:
            profiles = profiles_cache[inter_id]
        else:
            profiles = await self._get_profiles(inter_id, window)
            profiles_cache[inter_id] = profiles
        if is_governable(profiles, full_sat=self._full_sat, green_util=self._green_util):
            return
        if hop >= self._max_hops:
            return
        up = await self._get_upstream(inter_id, corridor_dir8, window, turn_no=None)
        upstream_cache[(inter_id, corridor_dir8)] = up
        if up and str(up.get("cor_inter_id")) != str(inter_id):
            await self._prefetch(
                up["cor_inter_id"],
                corridor_dir8,
                up["feeding_dir8"],
                hop + 1,
                window,
                profiles_cache,
                upstream_cache,
                turn_no,
            )

    async def _get_profiles(
        self, inter_id: str, window: DataWindow
    ) -> list[dict[str, Any]]:
        return await self._fetcher.approach_profiles(inter_id, window=window)

    async def _correlate_rows(self, inter_id: str, window: DataWindow) -> list[dict[str, Any]]:
        if inter_id in self._correlate_cache:
            return self._correlate_cache[inter_id]
        if self._settings.mock_db:
            rows = _mock_upstream_rows(inter_id, 6)
        else:
            from intersection_agent.services.flow_trace_service import day_labels_for_filter

            period_type = period_type_from_label(self._period_label)
            day_labels = day_labels_for_filter(window.dow_filter)
            rows = await self._flow_trace._fetch_upstream(inter_id, period_type, day_labels)
        self._correlate_cache[inter_id] = rows
        return rows

    async def _get_upstream(
        self,
        inter_id: str,
        dir8: int,
        window: DataWindow,
        *,
        turn_no: int | None = None,
    ) -> dict[str, Any] | None:
        rows = await self._correlate_rows(inter_id, window)
        tgt = (self._cognition or {}).get("intersection") or {}
        tgt_lon = tgt.get("lng") or tgt.get("lon")
        tgt_lat = tgt.get("lat")
        if inter_id != tgt.get("inter_id"):
            center = await self._topology.inter_center(inter_id)
            if center:
                tgt_lon, tgt_lat = center

        hop = await self._topology.pick_upstream_hop(
            inter_id,
            dir8,
            turn=turn_no,
            correlate_rows=rows,
            cognition=self._cognition,
            target_lon=float(tgt_lon) if tgt_lon is not None else None,
            target_lat=float(tgt_lat) if tgt_lat is not None else None,
        )
        if hop:
            self._topology.enrich_hop_turn_split(hop, rows, dir8)
        return hop


def _backfill_hop_meta(
    node: dict[str, Any],
    upstream_cache: dict[tuple[str, int], dict[str, Any] | None],
    corridor_dir8: int,
) -> None:
    for child in node.get("children") or []:
        up = upstream_cache.get((node.get("inter_id"), corridor_dir8))
        for (_pid, _d), cached in upstream_cache.items():
            if cached and cached.get("cor_inter_id") == child.get("inter_id"):
                up = cached
                break
        if up:
            child.setdefault("lng", up.get("lng"))
            child.setdefault("lat", up.get("lat"))
            child.setdefault("turn_split", up.get("turn_split") or [])
            child.setdefault("coverage", up.get("coverage"))
            child["hop_path"] = up.get("path") or []
            child["path_source"] = up.get("path_source")
        _backfill_hop_meta(child, upstream_cache, corridor_dir8)
