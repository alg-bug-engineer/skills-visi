"""按路段覆盖的流量溯源（对齐 references/sequence_restore_custom_h0610）。

禁止 import references；逻辑拷贝自参考 TrafficService 的聚合/离群清洗口径。
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT, get_settings
from app.data.ticket_nlu_schema import resolve_period_label
from app.trace.topology import DIR8_ENTRY, TURN_LABEL, resolve_dir8_turn

logger = logging.getLogger(__name__)

APPROACH_LABELS = {
    "N_IN": "北进口",
    "NE_IN": "东北进口",
    "E_IN": "东进口",
    "SE_IN": "东南进口",
    "S_IN": "南进口",
    "SW_IN": "西南进口",
    "W_IN": "西进口",
    "NW_IN": "西北进口",
}

DIR8_TO_APPROACH_LEG = {
    0: "N_IN",
    1: "NE_IN",
    2: "E_IN",
    3: "SE_IN",
    4: "S_IN",
    5: "SW_IN",
    6: "W_IN",
    7: "NW_IN",
}

PERIOD_WINDOWS = {
    "早高峰": (time(7, 0), time(9, 0)),
    "白平峰": (time(10, 0), time(16, 0)),
    "平峰": (time(10, 0), time(16, 0)),
    "晚高峰": (time(16, 0), time(19, 0)),
}

PERIOD_CODE_TO_LABEL = {
    "MORNING_PEAK": "早高峰",
    "EVENING_PEAK": "晚高峰",
    "OFF_PEAK": "平峰",
}

MIN_DISPLAY_RATIO = 0.05
LOW_SAMPLE_TARGET_FLOW = 10
POINT_RE = re.compile(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)", re.I)
LINE_RE = re.compile(r"LINESTRING\s*\((.*)\)", re.I | re.S)


def dir8_to_approach_leg(dir8: Any) -> str | None:
    try:
        code = int(dir8)
    except (TypeError, ValueError):
        return None
    return DIR8_TO_APPROACH_LEG.get(code)


def parse_point(wkt: str | None) -> list[float] | None:
    if not wkt:
        return None
    match = POINT_RE.search(str(wkt))
    if not match:
        return None
    return [float(match.group(1)), float(match.group(2))]


def parse_linestring(wkt: str | None) -> list[list[float]]:
    if not wkt:
        return []
    match = LINE_RE.search(str(wkt))
    if not match:
        return []
    coords: list[list[float]] = []
    for part in match.group(1).split(","):
        xy = part.strip().split()
        if len(xy) >= 2:
            coords.append([float(xy[0]), float(xy[1])])
    return coords


def haversine_m(a: list[float], b: list[float]) -> float:
    lng1, lat1 = math.radians(a[0]), math.radians(a[1])
    lng2, lat2 = math.radians(b[0]), math.radians(b[1])
    d_lng = lng2 - lng1
    d_lat = lat2 - lat1
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lng / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(h))


def feature_distance_m(a: list[list[float]], b: list[list[float]]) -> float:
    return min(haversine_m(pa, pb) for pa in a for pb in b)


def _resolve_abs_path(raw: str) -> Path | None:
    text = str(raw or "").strip()
    if not text:
        return None
    path = Path(text)
    return path if path.is_absolute() else PROJECT_ROOT / path


def resolve_coverage_time_window(
    *,
    period: Any,
    parquet_min: datetime | None,
    parquet_max: datetime | None,
) -> tuple[datetime, datetime, str | None] | None:
    """将诊断时段落到 parquet 实际日期上的起止时间。

    返回 (start, end, fallback_reason)。若时段窗与 parquet 无交集，回退到 parquet
    全窗（同日真实样本，不跨日虚增），并标注 fallback_reason。
    """
    if parquet_min is None or parquet_max is None:
        return None
    label = resolve_period_label(period) or PERIOD_CODE_TO_LABEL.get(str(period or "").strip().upper())
    if not label:
        return parquet_min, parquet_max, "no_period_use_parquet_full"

    window = PERIOD_WINDOWS.get(label)
    if not window:
        return parquet_min, parquet_max, "unknown_period_use_parquet_full"

    day = parquet_max.date()
    start_t, end_t = window
    start = datetime.combine(day, start_t)
    end = datetime.combine(day, end_t)
    if start < parquet_min:
        day = parquet_min.date()
        start = datetime.combine(day, start_t)
        end = datetime.combine(day, end_t)
    if end <= start:
        end = start + timedelta(hours=1)

    # 与 parquet 真实覆盖求交；无交集则回退全窗（本批恢复轨迹仅早高峰样本）
    overlap_start = max(start, parquet_min)
    overlap_end = min(end, parquet_max)
    if overlap_start < overlap_end:
        # arrive_time < end：右开区间，末端 +1s 避免漏掉 max 时刻事件
        return overlap_start, overlap_end + timedelta(seconds=1), None
    return parquet_min, parquet_max + timedelta(seconds=1), f"period_{label}_outside_parquet_use_full"


@dataclass
class IntersectionMeta:
    inter_id: str
    name: str
    coord: list[float] | None


@dataclass
class LinkMeta:
    link_id: str
    road_name: str
    coords: list[list[float]]
    f_inter_id: str | None
    t_inter_id: str | None
    direction: str | None
    length_m: float | None


@dataclass
class CoverageRequest:
    inter_id: str
    approach_leg: str
    turn_dir_no: int
    start_time: datetime
    end_time: datetime
    direction: str = "upstream"
    include_intersections: bool = True
    include_links: bool = True
    exclude_incomplete_trips: bool = True
    filter_spatial_outliers: bool = True
    outlier_radius_m: int = 900
    limit: int = 100


class SegmentCoverageService:
    """DuckDB + PG 路段覆盖溯源服务（懒加载）。"""

    def __init__(
        self,
        *,
        inter_parquet: Path,
        trips_parquet: Path,
        pg_dsn: str,
        pg_schema: str = "road6",
        pg_connect_timeout_s: int = 8,
        pg_statement_timeout_ms: int = 30_000,
    ) -> None:
        self.inter_parquet = inter_parquet
        self.trips_parquet = trips_parquet
        self.pg_dsn = pg_dsn
        self.pg_schema = pg_schema
        self.pg_connect_timeout_s = pg_connect_timeout_s
        self.pg_statement_timeout_ms = pg_statement_timeout_ms
        self._con = None
        self.intersections: dict[str, IntersectionMeta] = {}
        self.links: dict[str, LinkMeta] = {}
        self.time_range: dict[str, str] | None = None
        self._meta_loaded = False

    @property
    def ready(self) -> bool:
        return (
            self.inter_parquet.is_file()
            and self.trips_parquet.is_file()
            and bool(self.pg_dsn)
        )

    def ensure_loaded(self) -> str | None:
        """返回错误 reason；成功返回 None。"""
        if not self.inter_parquet.is_file() or not self.trips_parquet.is_file():
            return "missing_parquet"
        if not self.pg_dsn:
            return "missing_pg_dsn"
        if self._meta_loaded:
            return None
        try:
            import duckdb
        except ImportError:
            return "missing_duckdb"
        self._con = duckdb.connect(database=":memory:", read_only=False)
        row = self._con.execute(
            f"""
            select min(arrive_time), max(arrive_time)
            from read_parquet('{self.inter_parquet.as_posix()}')
            """
        ).fetchone()
        self.time_range = {
            "min": row[0].isoformat(sep=" ") if row and row[0] else "",
            "max": row[1].isoformat(sep=" ") if row and row[1] else "",
        }
        self._parquet_min = row[0] if row else None
        self._parquet_max = row[1] if row else None
        err = self._load_metadata()
        if err:
            return err
        self._meta_loaded = True
        return None

    def parquet_bounds(self) -> tuple[datetime | None, datetime | None]:
        self.ensure_loaded()
        return getattr(self, "_parquet_min", None), getattr(self, "_parquet_max", None)

    def _load_metadata(self) -> str | None:
        try:
            import psycopg
        except ImportError:
            return "missing_psycopg"
        schema = self.pg_schema
        try:
            with psycopg.connect(
                self.pg_dsn,
                connect_timeout=max(1, int(self.pg_connect_timeout_s)),
                options=f"-c statement_timeout={max(1, int(self.pg_statement_timeout_ms))}",
            ) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        select inter_id, inter_name, geom_center
                        from {schema}.dim_inter_info
                        where inter_id is not null
                        """
                    )
                    for inter_id, name, geom in cur.fetchall():
                        self.intersections[str(inter_id)] = IntersectionMeta(
                            inter_id=str(inter_id),
                            name=name or str(inter_id),
                            coord=parse_point(geom),
                        )
        except Exception as exc:  # noqa: BLE001
            logger.exception("segment coverage PG metadata failed: %s", exc)
            return "pg_metadata_failed"
        if not self.intersections:
            return "no_pg_geometry"
        return None

    def _load_link_metadata(self, link_ids: list[str]) -> None:
        """Load geometry only for links used by the current trace.

        The old eager query fetched every geometry in ``dim_rid_trace_info``.
        On the live database that result is large enough to spend minutes in
        ``ClientWrite`` before the diagnosis snapshot can be produced.
        """
        missing = list(dict.fromkeys(link_id for link_id in link_ids if link_id not in self.links))
        if not missing:
            return
        try:
            import psycopg
        except ImportError:
            return

        schema = self.pg_schema
        try:
            # autocommit keeps a missing fallback table from aborting the next
            # table lookup in the same connection.
            with psycopg.connect(
                self.pg_dsn,
                autocommit=True,
                connect_timeout=max(1, int(self.pg_connect_timeout_s)),
                options=f"-c statement_timeout={max(1, int(self.pg_statement_timeout_ms))}",
            ) as conn:
                with conn.cursor() as cur:
                    for table_name in ("dim_rid_trace_info", "dim_rid_info"):
                        remaining = [link_id for link_id in missing if link_id not in self.links]
                        if not remaining:
                            break
                        try:
                            cur.execute(
                                f"""
                                select rid_id, road_name, geom, f_inter_id, t_inter_id, dir, length_m
                                from {schema}.{table_name}
                                where rid_id = any(%s) and geom is not null
                                """,
                                (remaining,),
                            )
                        except Exception:  # noqa: BLE001
                            logger.warning("skip unavailable table %s.%s", schema, table_name)
                            continue
                        for row in cur.fetchall():
                            rid_id, road_name, geom, f_inter_id, t_inter_id, direction, length_m = row
                            rid = str(rid_id)
                            coords = parse_linestring(geom)
                            if len(coords) < 2:
                                continue
                            self.links[rid] = LinkMeta(
                                link_id=rid,
                                road_name=road_name or rid,
                                coords=coords,
                                f_inter_id=str(f_inter_id) if f_inter_id else None,
                                t_inter_id=str(t_inter_id) if t_inter_id else None,
                                direction=str(direction) if direction else None,
                                length_m=float(length_m) if length_m is not None else None,
                            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("segment coverage link metadata degraded: %s", exc)

    def trace(self, req: CoverageRequest) -> dict[str, Any]:
        err = self.ensure_loaded()
        if err:
            raise RuntimeError(err)
        assert self._con is not None
        if req.inter_id not in self.intersections:
            raise RuntimeError("unknown_inter_id")
        if req.end_time <= req.start_time:
            raise RuntimeError("invalid_time_window")

        target_events = self._target_events(req)
        if target_events.empty:
            return self._empty_trace(req)
        restored_by_trip = self._load_restored_trips(
            target_events, req.exclude_incomplete_trips
        )
        # Completion filtering is applied from the single restored-trip read
        # below.  This avoids joining/scanning the 221 MB trips parquet once in
        # _target_events and then scanning it twice more for intersections and
        # links.
        if req.exclude_incomplete_trips:
            target_events = target_events[
                target_events["trip_id"].astype(str).isin(restored_by_trip)
            ]
        target_flow = len(target_events)
        if target_flow == 0:
            return self._empty_trace(req)

        target = self.intersections[req.inter_id]
        result: dict[str, Any] = {
            "target": {
                **self._intersection_payload(target),
                "approach_leg": req.approach_leg,
                "approach_label": APPROACH_LABELS.get(req.approach_leg, req.approach_leg),
                "turn_dir_no": req.turn_dir_no,
                "turn_label": TURN_LABEL.get(req.turn_dir_no, f"转向{req.turn_dir_no}"),
                "start_time": req.start_time.isoformat(sep=" "),
                "end_time": req.end_time.isoformat(sep=" "),
                "direction": req.direction,
                "target_flow": target_flow,
            },
            "intersections": [],
            "links": [],
            "quality_filters": {
                "min_display_ratio": MIN_DISPLAY_RATIO,
                "low_sample_target_flow": LOW_SAMPLE_TARGET_FLOW,
                "low_sample": target_flow < LOW_SAMPLE_TARGET_FLOW,
                "exclude_incomplete_trips": req.exclude_incomplete_trips,
                "filter_spatial_outliers": req.filter_spatial_outliers,
                "outlier_radius_m": req.outlier_radius_m,
                "removed_intersections": 0,
                "removed_links": 0,
            },
        }
        if req.include_intersections:
            result["intersections"] = self._trace_intersections(
                req, target_events, target_flow, restored_by_trip=restored_by_trip
            )
        if req.include_links:
            result["links"] = self._trace_links(
                req, target_events, target_flow, restored_by_trip=restored_by_trip
            )
        if req.filter_spatial_outliers:
            self._filter_spatial_outliers(result, req.outlier_radius_m)
        return result

    def _target_events(self, req: CoverageRequest):
        assert self._con is not None
        return self._con.execute(
            f"""
            select
              e.trip_id,
              e.arrive_time as target_time,
              e.trip_id || '|' || cast(e.arrive_time as varchar) as event_key
            from read_parquet('{self.inter_parquet.as_posix()}') e
            where e.inter_id = ?
              and e.approach_leg = ?
              and e.turn_dir_no = ?
              and e.arrive_time >= ?
              and e.arrive_time < ?
            """,
            [req.inter_id, req.approach_leg, req.turn_dir_no, req.start_time, req.end_time],
        ).fetchdf()

    def _load_restored_trips(self, target_events, exclude_incomplete: bool) -> dict[str, tuple[list[Any], list[Any]]]:
        assert self._con is not None
        unique_trips = target_events[["trip_id"]].drop_duplicates()
        self._con.register("target_trip_ids", unique_trips)
        try:
            complete_filter = ""
            if exclude_incomplete:
                complete_filter = "where coalesce(r.effective_restore_complete, false) = true"
            rows = self._con.execute(
                f"""
                select r.trip_id, r.inter_sequence_json, r.link_sequence_json
                from read_parquet('{self.trips_parquet.as_posix()}') r
                join target_trip_ids t on r.trip_id = t.trip_id
                {complete_filter}
                """
            ).fetchall()
        finally:
            self._con.unregister("target_trip_ids")

        return {
            str(trip_id): (json.loads(inter_json or "[]"), json.loads(link_json or "[]"))
            for trip_id, inter_json, link_json in rows
        }

    def _path_inter_ids(self, req: CoverageRequest, inters: list[Any]) -> list[str]:
        try:
            target_idx = list(inters).index(req.inter_id)
        except ValueError:
            return []
        if req.direction == "upstream":
            segment = inters[:target_idx]
        else:
            segment = inters[target_idx + 1 :]
        return [str(inter_id) for inter_id in segment if str(inter_id) != req.inter_id]

    def _trace_intersections(
        self,
        req: CoverageRequest,
        target_events,
        target_flow: int,
        *,
        restored_by_trip: dict[str, tuple[list[Any], list[Any]]] | None = None,
    ) -> list[dict[str, Any]]:
        """仅统计恢复轨迹走廊上的上游/下游路口，避免把行程中无关历史访问算入占比。"""
        if restored_by_trip is None:
            restored_by_trip = self._load_restored_trips(
                target_events, req.exclude_incomplete_trips
            )
        inter_event_keys: dict[str, set[str]] = defaultdict(set)

        for _, row in target_events.iterrows():
            trip_id = str(row["trip_id"])
            event_key = str(row["event_key"])
            restored = restored_by_trip.get(trip_id)
            if not restored:
                continue
            inters, _links = restored
            for inter_id in self._path_inter_ids(req, inters):
                inter_event_keys[inter_id].add(event_key)

        ranked = sorted(inter_event_keys.items(), key=lambda item: len(item[1]), reverse=True)
        payload: list[dict[str, Any]] = []
        for inter_id, keys in ranked[: req.limit]:
            meta = self.intersections.get(inter_id)
            if not meta or not meta.coord:
                continue
            flow = len(keys)
            ratio = flow / target_flow
            if ratio < MIN_DISPLAY_RATIO:
                continue
            payload.append(
                {
                    **self._intersection_payload(meta),
                    "rank": len(payload) + 1,
                    "flow": flow,
                    "ratio": round(ratio, 6),
                }
            )
        return payload

    def _trace_links(
        self,
        req: CoverageRequest,
        target_events,
        target_flow: int,
        *,
        restored_by_trip: dict[str, tuple[list[Any], list[Any]]] | None = None,
    ) -> list[dict[str, Any]]:
        if restored_by_trip is None:
            restored_by_trip = self._load_restored_trips(
                target_events, req.exclude_incomplete_trips
            )
        link_event_keys: dict[str, set[str]] = defaultdict(set)

        for _, row in target_events.iterrows():
            trip_id = str(row["trip_id"])
            event_key = str(row["event_key"])
            restored = restored_by_trip.get(trip_id)
            if not restored:
                continue
            inters, links = restored
            try:
                target_idx = list(inters).index(req.inter_id)
            except ValueError:
                continue
            selected = links[:target_idx] if req.direction == "upstream" else links[target_idx:]
            for link_id in set(str(link_id) for link_id in selected):
                link_event_keys[link_id].add(event_key)

        ranked = sorted(link_event_keys.items(), key=lambda item: len(item[1]), reverse=True)
        self._load_link_metadata([link_id for link_id, _keys in ranked[: req.limit]])
        payload: list[dict[str, Any]] = []
        for link_id, keys in ranked[: req.limit]:
            meta = self.links.get(link_id)
            if not meta or len(meta.coords) < 2:
                continue
            flow = len(keys)
            ratio = flow / target_flow
            if ratio < MIN_DISPLAY_RATIO:
                continue
            payload.append(
                {
                    "id": meta.link_id,
                    "name": meta.road_name,
                    "coords": meta.coords,
                    "from_inter_id": meta.f_inter_id,
                    "to_inter_id": meta.t_inter_id,
                    "direction": meta.direction,
                    "length_m": meta.length_m,
                    "rank": len(payload) + 1,
                    "flow": flow,
                    "ratio": round(ratio, 6),
                }
            )
        return payload

    def _filter_spatial_outliers(self, result: dict[str, Any], radius_m: int) -> None:
        target = result.get("target", {})
        if target.get("lng") is None or target.get("lat") is None:
            return

        features: list[dict[str, Any]] = [
            {
                "kind": "target",
                "index": -1,
                "coords": [[target["lng"], target["lat"]]],
                "ratio": 1.0,
            }
        ]
        for index, item in enumerate(result.get("intersections", [])):
            if item.get("lng") is None or item.get("lat") is None:
                continue
            features.append(
                {
                    "kind": "intersection",
                    "index": index,
                    "coords": [[item["lng"], item["lat"]]],
                    "ratio": item.get("ratio", 0),
                }
            )
        for index, item in enumerate(result.get("links", [])):
            coords = item.get("coords") or []
            if len(coords) < 2:
                continue
            step = max(1, len(coords) // 16)
            sampled = coords[::step]
            if sampled[-1] != coords[-1]:
                sampled.append(coords[-1])
            features.append(
                {
                    "kind": "link",
                    "index": index,
                    "coords": sampled,
                    "ratio": item.get("ratio", 0),
                }
            )

        if len(features) <= 3:
            return

        adjacency = [set() for _ in features]
        for i in range(len(features)):
            for j in range(i + 1, len(features)):
                if feature_distance_m(features[i]["coords"], features[j]["coords"]) <= radius_m:
                    adjacency[i].add(j)
                    adjacency[j].add(i)

        components: list[list[int]] = []
        seen: set[int] = set()
        for start in range(len(features)):
            if start in seen:
                continue
            stack = [start]
            seen.add(start)
            comp: list[int] = []
            while stack:
                current = stack.pop()
                comp.append(current)
                for nxt in adjacency[current]:
                    if nxt not in seen:
                        seen.add(nxt)
                        stack.append(nxt)
            components.append(comp)

        target_component = next((i for i, comp in enumerate(components) if 0 in comp), 0)
        keep_components = {target_component}
        for comp_index, comp in enumerate(components):
            if comp_index == target_component:
                continue
            members = [features[i] for i in comp]
            feature_count = len(members)
            max_ratio = max((item["ratio"] for item in members), default=0)
            ratio_sum = sum(item["ratio"] for item in members)
            if feature_count >= 3 or max_ratio >= 0.2 or ratio_sum >= 0.35:
                keep_components.add(comp_index)

        keep_feature_indexes = {idx for comp_index in keep_components for idx in components[comp_index]}
        keep_intersections = {
            features[idx]["index"]
            for idx in keep_feature_indexes
            if features[idx]["kind"] == "intersection"
        }
        keep_links = {
            features[idx]["index"] for idx in keep_feature_indexes if features[idx]["kind"] == "link"
        }

        before_intersections = len(result.get("intersections", []))
        before_links = len(result.get("links", []))
        result["intersections"] = [
            item for index, item in enumerate(result.get("intersections", [])) if index in keep_intersections
        ]
        result["links"] = [
            item for index, item in enumerate(result.get("links", [])) if index in keep_links
        ]

        for rank, item in enumerate(result["intersections"], start=1):
            item["rank"] = rank
        for rank, item in enumerate(result["links"], start=1):
            item["rank"] = rank

        result["quality_filters"]["removed_intersections"] = before_intersections - len(
            result["intersections"]
        )
        result["quality_filters"]["removed_links"] = before_links - len(result["links"])

    def _empty_trace(self, req: CoverageRequest) -> dict[str, Any]:
        target = self.intersections[req.inter_id]
        return {
            "target": {
                **self._intersection_payload(target),
                "approach_leg": req.approach_leg,
                "approach_label": APPROACH_LABELS.get(req.approach_leg, req.approach_leg),
                "turn_dir_no": req.turn_dir_no,
                "turn_label": TURN_LABEL.get(req.turn_dir_no, f"转向{req.turn_dir_no}"),
                "start_time": req.start_time.isoformat(sep=" "),
                "end_time": req.end_time.isoformat(sep=" "),
                "direction": req.direction,
                "target_flow": 0,
            },
            "intersections": [],
            "links": [],
            "quality_filters": {
                "min_display_ratio": MIN_DISPLAY_RATIO,
                "low_sample_target_flow": LOW_SAMPLE_TARGET_FLOW,
                "low_sample": False,
                "exclude_incomplete_trips": req.exclude_incomplete_trips,
                "filter_spatial_outliers": req.filter_spatial_outliers,
                "outlier_radius_m": req.outlier_radius_m,
                "removed_intersections": 0,
                "removed_links": 0,
            },
        }

    def _intersection_payload(self, meta: IntersectionMeta) -> dict[str, Any]:
        return {
            "id": meta.inter_id,
            "name": meta.name,
            "lng": meta.coord[0] if meta.coord else None,
            "lat": meta.coord[1] if meta.coord else None,
        }


_service: SegmentCoverageService | None = None


def reset_segment_coverage_service() -> None:
    global _service
    _service = None


def get_segment_coverage_service() -> SegmentCoverageService | None:
    global _service
    if _service is not None:
        return _service
    settings = get_settings()
    inter = _resolve_abs_path(settings.flow_trace_inter_parquet)
    trips = _resolve_abs_path(settings.flow_trace_trips_parquet)
    if inter is None or trips is None:
        return None
    _service = SegmentCoverageService(
        inter_parquet=inter,
        trips_parquet=trips,
        pg_dsn=settings.pg_dsn,
        pg_schema=settings.pg_schema,
        pg_connect_timeout_s=settings.pg_connect_timeout_s,
        pg_statement_timeout_ms=settings.pg_statement_timeout_ms,
    )
    return _service


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "action": "map_scene",
        "phase": "flow_trace_segment_coverage_map",
        "available": False,
        "reason": reason,
        "intersections": [],
        "links": [],
    }


def build_flow_trace_segment_coverage_map_scene(
    *,
    topology: dict[str, Any] | None,
    target_profile: dict[str, Any],
    direction: str,
    movement: str,
    trace_direction: str = "upstream",
) -> dict[str, Any]:
    """诊断管线：产出路段覆盖 map_scene。"""
    topo = topology or {}
    service = get_segment_coverage_service()
    if service is None:
        return _unavailable("missing_parquet")

    load_err = service.ensure_loaded()
    if load_err:
        return _unavailable(load_err)

    inter_id = str(
        target_profile.get("inter_id")
        or topo.get("target_inter_id")
        or target_profile.get("target_inter_id")
        or ""
    )
    if not inter_id:
        return _unavailable("no_target_inter_id")

    dir8_code = topo.get("dir8_code")
    turn_dir_no = topo.get("turn_dir_no")
    if dir8_code is None or turn_dir_no is None:
        resolved_dir8, resolved_turn = resolve_dir8_turn(direction, movement)
        dir8_code = dir8_code if dir8_code is not None else resolved_dir8
        turn_dir_no = turn_dir_no if turn_dir_no is not None else resolved_turn

    approach_leg = dir8_to_approach_leg(dir8_code)
    if not approach_leg:
        return _unavailable("approach_unmap")

    try:
        turn_i = int(turn_dir_no)
    except (TypeError, ValueError):
        return _unavailable("invalid_turn")

    pmin, pmax = service.parquet_bounds()
    period = topo.get("period_type") or topo.get("period") or target_profile.get("period")
    window = resolve_coverage_time_window(period=period, parquet_min=pmin, parquet_max=pmax)
    if not window:
        return _unavailable("no_parquet_time_range")
    start_time, end_time, period_fallback = window

    trace_dir = "downstream" if trace_direction == "downstream" else "upstream"
    req = CoverageRequest(
        inter_id=inter_id,
        approach_leg=approach_leg,
        turn_dir_no=turn_i,
        start_time=start_time,
        end_time=end_time,
        direction=trace_dir,
    )

    try:
        raw = service.trace(req)
    except RuntimeError as exc:
        return _unavailable(str(exc) or "trace_failed")
    except Exception as exc:  # noqa: BLE001
        logger.exception("segment coverage trace failed: %s", exc)
        return _unavailable("trace_failed")

    target_flow = int((raw.get("target") or {}).get("target_flow") or 0)
    if target_flow <= 0 and not raw.get("links") and not raw.get("intersections"):
        return {
            **_unavailable("no_target_events"),
            "target": raw.get("target"),
            "quality_filters": raw.get("quality_filters"),
            "stats": {
                "intersection_count": 0,
                "link_count": 0,
                "parquet_date": start_time.date().isoformat(),
                "approach_leg": approach_leg,
                "turn_dir_no": turn_i,
            },
        }

    center = None
    t = raw.get("target") or {}
    if t.get("lng") is not None and t.get("lat") is not None:
        center = [float(t["lng"]), float(t["lat"])]
    elif target_profile.get("lng") is not None and target_profile.get("lat") is not None:
        center = [float(target_profile["lng"]), float(target_profile["lat"])]

    return {
        "action": "map_scene",
        "phase": "flow_trace_segment_coverage_map",
        "available": True,
        "center": center,
        "trace_direction": trace_dir,
        "business_direction": "outgoing" if trace_dir == "downstream" else "incoming",
        "target": raw.get("target"),
        "intersections": raw.get("intersections") or [],
        "links": raw.get("links") or [],
        "quality_filters": raw.get("quality_filters") or {},
        "stats": {
            "intersection_count": len(raw.get("intersections") or []),
            "link_count": len(raw.get("links") or []),
            "parquet_date": start_time.date().isoformat(),
            "approach_leg": approach_leg,
            "approach_label": APPROACH_LABELS.get(approach_leg, approach_leg),
            "turn_dir_no": turn_i,
            "dir8_label": DIR8_ENTRY.get(int(dir8_code) if dir8_code is not None else -1),
            "target_flow": target_flow,
            "low_sample": target_flow < LOW_SAMPLE_TARGET_FLOW,
            "period_fallback": period_fallback,
            "window_start": start_time.isoformat(sep=" "),
            "window_end": end_time.isoformat(sep=" "),
        },
    }
