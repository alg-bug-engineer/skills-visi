"""上游治理溯源：递归找可信控治理落点（≤2 跳）。"""
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
    day_labels_for_filter,
    one_hop_for_approach,
    period_type_from_label,
    turn_split_for_upstream,
)
from intersection_agent.services.map_presentation_service import build_upstream_storyboard
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
    feeding_dir8: int,
    hop: int,
    window: Any,
    get_profiles: Callable[[str, Any], list[dict[str, Any]]],
    get_upstream: Callable[[str, int, Any], dict[str, Any] | None],
    get_other_approaches: Callable[[str, int], list[int]],
    full_sat: float,
    green_util: float,
    max_hops: int,
    inter_name: str | None = None,
) -> dict[str, Any]:
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
    node["decision"] = "继续上溯"
    for ap in get_other_approaches(inter_id, feeding_dir8):
        up = get_upstream(inter_id, ap, window)
        if not up:
            continue
        child = build_tree(
            up["cor_inter_id"],
            feeding_dir8=up["feeding_dir8"],
            hop=hop + 1,
            window=window,
            get_profiles=get_profiles,
            get_upstream=get_upstream,
            get_other_approaches=get_other_approaches,
            full_sat=full_sat,
            green_util=green_util,
            max_hops=max_hops,
            inter_name=up.get("cor_inter_name"),
        )
        node["children"].append(child)
    return node


def _mock_upstream_rows(inter_id: str, dir8: int) -> list[dict[str, Any]]:
    """MOCK_DB：构造确定性上游拓扑。target→hub(全饱和)→{南向可治理,其余全饱和}。"""
    if not inter_id.startswith("mock_"):
        cor_id, name = "mock_hub", "上游枢纽路口"
    elif dir8 == 4:
        cor_id, name = f"mock_gov_{dir8}", "可治理上游路口"
    else:
        cor_id, name = f"mock_full_{dir8}", "上游路口(全饱和)"
    lng = 117.1 + dir8 * 0.01
    lat = 36.65 + dir8 * 0.01
    base = {
        "f_dir8_no": dir8, "turn_dir_no": 2,
        "cor_inter_id": cor_id, "cor_f_dir8_no": dir8,
        "cor_inter_name": name, "cor_lng": lng, "cor_lat": lat,
    }
    # 上一路口流量按转向拆分：直行为主，左右转辅（供地图标注演示）
    return [
        {**base, "cor_turn_dir_no": 2, "flow_share_ratio": 67.0},
        {**base, "cor_turn_dir_no": 1, "flow_share_ratio": 22.0},
        {**base, "cor_turn_dir_no": 3, "flow_share_ratio": 11.0},
    ]


def _collect_points(
    node: dict[str, Any], tree_id: str, approach: str
) -> list[dict[str, Any]]:
    """收集树内治理落点，标注所属树/进口道，供侧卡使用。"""
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


class UpstreamGovernanceTraceService:
    """对过饱和进口道递归溯源上游、定位可信控治理落点，并产出 storyboard。"""

    def __init__(
        self,
        fetcher: DataFetcher | None = None,
        flow_trace: FlowTraceService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._fetcher = fetcher or DataFetcher(settings=self._settings)
        self._flow_trace = flow_trace or FlowTraceService(settings=self._settings)
        self._full_sat = threshold_value("upstream_trace", "full_saturation", default=0.85)
        self._green_util = threshold_value(
            "upstream_trace", "governable_green_util", default=0.50
        )
        self._max_hops = int(threshold_value("upstream_trace", "max_hops", default=5))
        self._period_label: str | None = None

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
        """对一个或多个过饱和进口道溯源，返回 {trees, governance_points, storyboard}。"""
        labels = approaches if approaches is not None else ([approach] if approach else [])
        empty = {"trees": [], "governance_points": [], "storyboard": {"trees": [], "frames": []}}
        if not labels or nlu is None or nlu.time_period is None:
            return empty
        self._period_label = nlu.time_period.label
        window = build_data_window(nlu.time_period, reference_date=reference_date)

        try:
            results = await asyncio.gather(
                *[self._build_one(inter_id, ap, window, cognition) for ap in labels]
            )
        except Exception as exc:  # noqa: BLE001 - 溯源失败不应阻断主诊断
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
    ) -> dict[str, Any] | None:
        dir8 = _APPROACH_TO_DIR8.get(approach)
        if dir8 is None:
            return None
        hop1 = await self._get_upstream(inter_id, dir8, window)
        if not hop1:
            return None
        root_id = hop1["cor_inter_id"]

        profiles_cache: dict[str, list[dict[str, Any]]] = {}
        upstream_cache: dict[tuple[str, int], dict[str, Any] | None] = {}
        await self._prefetch(
            root_id, hop1["feeding_dir8"], 1, window, profiles_cache, upstream_cache
        )

        root = build_tree(
            root_id,
            feeding_dir8=hop1["feeding_dir8"],
            hop=1,
            window=window,
            get_profiles=lambda i, _w: profiles_cache.get(i, []),
            get_upstream=lambda i, d, _w: upstream_cache.get((i, d)),
            get_other_approaches=lambda i, ex: _other_approaches(
                profiles_cache.get(i, []), ex
            ),
            full_sat=self._full_sat,
            green_util=self._green_util,
            max_hops=self._max_hops,
            inter_name=hop1.get("cor_inter_name"),
        )
        # 一跳节点经纬度/转向拆分回填（build_tree 不持有 hop1 这些字段）
        root.setdefault("lng", hop1.get("lng"))
        root.setdefault("lat", hop1.get("lat"))
        root["turn_split"] = hop1.get("turn_split") or []
        root["coverage"] = hop1.get("coverage")
        _backfill_coords(root, upstream_cache)

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
        feeding_dir8: int,
        hop: int,
        window: DataWindow,
        profiles_cache: dict[str, list[dict[str, Any]]],
        upstream_cache: dict[tuple[str, int], dict[str, Any] | None],
    ) -> None:
        """镜像 build_tree 的遍历，提前异步取齐 profiles / upstream，供同步构树。"""
        if inter_id in profiles_cache:
            profiles = profiles_cache[inter_id]
        else:
            profiles = await self._get_profiles(inter_id, window)
            profiles_cache[inter_id] = profiles
        if is_governable(profiles, full_sat=self._full_sat, green_util=self._green_util):
            return
        if hop >= self._max_hops:
            return
        for ap in _other_approaches(profiles, feeding_dir8):
            up = await self._get_upstream(inter_id, ap, window)
            upstream_cache[(inter_id, ap)] = up
            if up:
                await self._prefetch(
                    up["cor_inter_id"],
                    up["feeding_dir8"],
                    hop + 1,
                    window,
                    profiles_cache,
                    upstream_cache,
                )

    async def _get_profiles(
        self, inter_id: str, window: DataWindow
    ) -> list[dict[str, Any]]:
        return await self._fetcher.approach_profiles(inter_id, window=window)

    async def _get_upstream(
        self, inter_id: str, dir8: int, window: DataWindow
    ) -> dict[str, Any] | None:
        if self._settings.mock_db:
            rows = _mock_upstream_rows(inter_id, dir8)
        else:
            period_type = period_type_from_label(self._period_label)
            day_labels = day_labels_for_filter(window.dow_filter)
            rows = await self._flow_trace._fetch_upstream(inter_id, period_type, day_labels)
        hop = one_hop_for_approach(rows, dir8)
        if hop:
            hop["turn_split"] = turn_split_for_upstream(rows, dir8, hop["cor_inter_id"])
        return hop


def _other_approaches(profiles: list[dict[str, Any]], exclude: int) -> list[int]:
    """该路口实际存在的其余进口道（非固定 4，排除来流方向）。"""
    return [int(p["dir8_code"]) for p in profiles if int(p["dir8_code"]) != exclude]


def _backfill_coords(
    node: dict[str, Any],
    upstream_cache: dict[tuple[str, int], dict[str, Any] | None],
) -> None:
    """从 upstream_cache 回填子节点经纬度（构树时仅有 cor_inter_id）。"""
    for child in node.get("children") or []:
        for (_pid, _ap), up in upstream_cache.items():
            if up and up.get("cor_inter_id") == child.get("inter_id"):
                child.setdefault("lng", up.get("lng"))
                child.setdefault("lat", up.get("lat"))
                child.setdefault("turn_split", up.get("turn_split") or [])
                child.setdefault("coverage", up.get("coverage"))
                break
        _backfill_coords(child, upstream_cache)
