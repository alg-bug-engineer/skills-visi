#!/usr/bin/env python3
"""生成道路 line 维表 dim_line_info / dim_line_link_rltn / dim_line_inter_rltn。

依据 skillpackages/linegenerate.md：
  - 同主路名 link 链 + 信号灯路口链（相邻信控路口沿路间距 < 1.2km）
  - line_id = start_geohash_7 + end_geohash_7 + seq_no(2)
  - 范围：dim_tfcunit_info；link：dim_link_info；路口：dim_inter_info

用法:
    python -m preprocessing.line.dim_line_info
    python -m preprocessing.line.dim_line_info --truncate
    python -m preprocessing.line.dim_line_info --road-name 舜华路
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from data.pg_reader import connect_pg
from env import load_project_env

CALC_VERSION = "line_generate_v3"
MAX_INTER_GAP_M = 1200.0
ORDER_RULE = "lon_asc_lat_desc"
UNNAMED_ROAD_NAMES = frozenset({"无名道路", "未命名"})

TABLE_LINE = "dim_line_info"
TABLE_LINE_LINK = "dim_line_link_rltn"
TABLE_LINE_INTER = "dim_line_inter_rltn"
TABLE_SCOPE = "dim_tfcunit_info"

LINE_COLUMNS = [
    "line_id",
    "line_name",
    "road_name",
    "start_cross_road_name",
    "end_cross_road_name",
    "start_geohash_7",
    "end_geohash_7",
    "seq_no",
    "start_inter_id",
    "end_inter_id",
    "start_inter_name",
    "end_inter_name",
    "link_count",
    "inter_count",
    "line_length_m",
    "max_inter_gap_m",
    "min_inter_gap_m",
    "order_rule",
    "link_ids_ordered_json",
    "inter_ids_ordered_json",
    "inter_names_json",
    "scope_version_id",
    "calc_version",
    "is_deleted",
]

LINK_RLTN_COLUMNS = [
    "line_id",
    "seq_no",
    "link_id",
    "road_name",
    "length_m",
    "f_inter_id",
    "t_inter_id",
    "cum_length_m",
    "is_deleted",
]

INTER_RLTN_COLUMNS = [
    "line_id",
    "seq_no",
    "inter_id",
    "inter_name",
    "cross_road_name",
    "lon",
    "lat",
    "geohash_7",
    "cum_length_m",
    "gap_to_prev_m",
    "is_deleted",
]


@dataclass
class LinkRow:
    link_id: str
    road_name: str
    primary_road: str
    length_m: float
    f_inter_id: str
    t_inter_id: str
    lon: float
    lat: float
    version_id: str = ""

    @property
    def sort_key(self) -> tuple[float, float]:
        return (self.lon, -self.lat)


# 兼容旧测试命名
RidRow = LinkRow


@dataclass
class InterRow:
    inter_id: str
    inter_name: str
    is_signalized: bool
    lon: float
    lat: float

    @property
    def geohash_7(self) -> str:
        return geohash_from_inter_id(self.inter_id)


@dataclass
class OrientedLink:
    link: LinkRow
    f_inter_id: str
    t_inter_id: str

    @property
    def length_m(self) -> float:
        return self.link.length_m


OrientedRid = OrientedLink


@dataclass
class LineSegment:
    road_name: str
    oriented_links: list[OrientedLink]
    signal_inters: list[tuple[InterRow, float, float | None]]
    scope_version_id: str = ""


def _qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _qualified(schema: str, table: str) -> str:
    return f"{_qident(schema)}.{_qident(table)}"


def parse_point(text: str | None) -> tuple[float, float] | None:
    if not text:
        return None
    m = re.search(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)", str(text), re.I)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def extract_primary_road(road_name: str, fallback: str = "") -> str:
    text = (road_name or "").strip()
    if not text:
        return fallback.strip()
    for sep in (":", "："):
        if sep in text:
            return text.split(sep, 1)[0].strip()
    return text


def is_named_road(road_name: str) -> bool:
    primary = extract_primary_road(road_name)
    return bool(primary) and primary not in UNNAMED_ROAD_NAMES


def parse_cross_roads(road_name: str) -> tuple[str, str]:
    text = (road_name or "").strip()
    suffix = ""
    for sep in (":", "："):
        if sep in text:
            suffix = text.split(sep, 1)[1].strip()
            break
    if not suffix:
        return "", ""
    for dash in ("-", "－", "—"):
        if dash in suffix:
            left, right = suffix.split(dash, 1)
            return left.strip(), right.strip()
    return suffix, suffix


def cross_road_from_inter_name(inter_name: str, primary_road: str) -> str:
    text = (inter_name or "").strip()
    if not text:
        return ""
    parts = re.split(r"与|和", text.replace("路口", "").replace("交叉口", ""))
    for part in parts:
        name = part.strip()
        if not name:
            continue
        if name == primary_road:
            continue
        if primary_road and name.endswith(primary_road) and name != primary_road:
            trimmed = name[: -len(primary_road)].strip()
            if trimmed:
                return trimmed
        if primary_road not in name or name != primary_road:
            return name
    return text


def geohash_from_inter_id(inter_id: str) -> str:
    text = (inter_id or "").strip()
    if len(text) >= 10:
        return text[3:10]
    return text[:7].ljust(7, "0")[:7]


def make_line_id(start_inter_id: str, end_inter_id: str, seq_no: int) -> str:
    start_gh = geohash_from_inter_id(start_inter_id)
    end_gh = geohash_from_inter_id(end_inter_id)
    return f"{start_gh}{end_gh}{seq_no:02d}"


def _link_at_inter(link: LinkRow, inter_id: str) -> OrientedLink | None:
    if link.f_inter_id == inter_id:
        return OrientedLink(link=link, f_inter_id=link.f_inter_id, t_inter_id=link.t_inter_id)
    if link.t_inter_id == inter_id:
        return OrientedLink(link=link, f_inter_id=link.t_inter_id, t_inter_id=link.f_inter_id)
    return None


def build_paths(links: list[LinkRow]) -> list[list[OrientedLink]]:
    unused = {link.link_id: link for link in links}
    by_inter: dict[str, list[LinkRow]] = defaultdict(list)
    for link in links:
        if link.f_inter_id:
            by_inter[link.f_inter_id].append(link)
        if link.t_inter_id:
            by_inter[link.t_inter_id].append(link)

    paths: list[list[OrientedLink]] = []
    while unused:
        seed = min(unused.values(), key=lambda link: link.sort_key)
        forward = OrientedLink(
            link=seed,
            f_inter_id=seed.f_inter_id,
            t_inter_id=seed.t_inter_id,
        )
        path = [forward]
        del unused[seed.link_id]

        cur = seed.t_inter_id
        while cur:
            nxt_link: LinkRow | None = None
            for cand in by_inter.get(cur, []):
                if cand.link_id in unused:
                    nxt_link = cand
                    break
            if not nxt_link:
                break
            oriented = _link_at_inter(nxt_link, cur)
            if not oriented:
                break
            path.append(oriented)
            del unused[nxt_link.link_id]
            cur = oriented.t_inter_id

        prefix: list[OrientedLink] = []
        cur = seed.f_inter_id
        while cur:
            nxt_link = None
            for cand in by_inter.get(cur, []):
                if cand.link_id in unused:
                    nxt_link = cand
                    break
            if not nxt_link:
                break
            oriented = _link_at_inter(nxt_link, cur)
            if not oriented:
                break
            prefix.insert(0, oriented)
            del unused[nxt_link.link_id]
            cur = oriented.f_inter_id

        paths.append(prefix + path)
    return paths


def cross_road_at_inter(
    inter_id: str,
    *,
    primary_road: str,
    inter_map: dict[str, InterRow],
    prev_link: OrientedLink | None,
    next_link: OrientedLink | None,
) -> str:
    if prev_link and prev_link.t_inter_id == inter_id:
        _, cross_t = parse_cross_roads(prev_link.link.road_name)
        if cross_t:
            return cross_t
    if prev_link and prev_link.f_inter_id == inter_id:
        cross_f, _ = parse_cross_roads(prev_link.link.road_name)
        if cross_f:
            return cross_f
    if next_link and next_link.f_inter_id == inter_id:
        cross_f, _ = parse_cross_roads(next_link.link.road_name)
        if cross_f:
            return cross_f
    if next_link and next_link.t_inter_id == inter_id:
        _, cross_t = parse_cross_roads(next_link.link.road_name)
        if cross_t:
            return cross_t
    inter = inter_map.get(inter_id)
    if inter:
        return cross_road_from_inter_name(inter.inter_name, primary_road)
    return ""


def collect_signal_inters(
    path: list[OrientedLink],
    inter_map: dict[str, InterRow],
) -> list[tuple[InterRow, float, float | None]]:
    if not path:
        return []

    ordered: list[tuple[InterRow, float, float | None]] = []
    seen: set[str] = set()
    cum = 0.0

    def add_inter(
        inter_id: str,
        prev_link: OrientedLink | None,
        next_link: OrientedLink | None,
    ) -> None:
        nonlocal cum
        if not inter_id or inter_id in seen:
            return
        inter = inter_map.get(inter_id)
        if not inter or not inter.is_signalized:
            return
        gap = None if not ordered else cum - ordered[-1][1]
        ordered.append((inter, cum, gap))
        seen.add(inter_id)

    add_inter(path[0].f_inter_id, None, path[0])
    for idx, seg in enumerate(path):
        cum += seg.length_m
        prev_link = seg
        next_link = path[idx + 1] if idx + 1 < len(path) else None
        add_inter(seg.t_inter_id, prev_link, next_link)
    return ordered


def split_path_by_signal_gap(
    path: list[OrientedLink],
    signal_inters: list[tuple[InterRow, float, float | None]],
) -> list[tuple[list[OrientedLink], list[tuple[InterRow, float, float | None]]]]:
    if not signal_inters:
        return []
    if len(signal_inters) == 1:
        return [(path, signal_inters)]

    segments: list[tuple[list[OrientedLink], list[tuple[InterRow, float, float | None]]]] = []
    seg_start = 0
    for idx in range(1, len(signal_inters)):
        gap = signal_inters[idx][2]
        if gap is not None and gap >= MAX_INTER_GAP_M:
            seg_inters = signal_inters[seg_start:idx]
            start_dist = seg_inters[0][1]
            end_dist = seg_inters[-1][1]
            seg_path = trim_path_by_distance(path, start_dist, end_dist)
            if seg_path and seg_inters:
                segments.append((seg_path, seg_inters))
            seg_start = idx

    tail = signal_inters[seg_start:]
    if tail:
        start_dist = tail[0][1]
        end_dist = tail[-1][1]
        seg_path = trim_path_by_distance(path, start_dist, end_dist)
        if seg_path:
            segments.append((seg_path, tail))
    return segments


def trim_path_by_distance(
    path: list[OrientedLink],
    start_dist: float,
    end_dist: float,
) -> list[OrientedLink]:
    if not path:
        return []

    cum = 0.0
    start_idx = 0
    end_idx = len(path) - 1
    pos_before = 0.0

    for idx, seg in enumerate(path):
        pos_after = cum + seg.length_m
        if start_dist <= pos_after or idx == len(path) - 1:
            start_idx = idx if start_dist <= pos_before else idx
            break
        pos_before = pos_after
        cum = pos_after

    cum = 0.0
    pos_before = 0.0
    for idx, seg in enumerate(path):
        pos_after = cum + seg.length_m
        if end_dist <= pos_after or idx == len(path) - 1:
            end_idx = idx
            break
        pos_before = pos_after
        cum = pos_after

    return path[start_idx : end_idx + 1]


def build_line_segments(
    road_name: str,
    paths: list[list[OrientedLink]],
    inter_map: dict[str, InterRow],
    scope_version_id: str,
) -> list[LineSegment]:
    segments: list[LineSegment] = []
    for path in paths:
        signal_inters = collect_signal_inters(path, inter_map)
        if not signal_inters:
            continue
        for seg_path, seg_inters in split_path_by_signal_gap(path, signal_inters):
            if not seg_inters:
                continue
            segments.append(
                LineSegment(
                    road_name=road_name,
                    oriented_links=seg_path,
                    signal_inters=seg_inters,
                    scope_version_id=scope_version_id,
                )
            )
    return segments


def format_line_name(
    road_name: str,
    start_label: str,
    end_label: str,
    *,
    start_inter_name: str = "",
    end_inter_name: str = "",
) -> str:
    left = start_label or start_inter_name or "起点"
    right = end_label or end_inter_name or "终点"
    if left == right:
        return f"{road_name}（{left}）"
    return f"{road_name}（{left}--{right}）"


def line_rows_from_segment(
    segment: LineSegment,
    inter_map: dict[str, InterRow],
    seq_counter: dict[tuple[str, str], int],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    start_inter, _, _ = segment.signal_inters[0]
    end_inter, _, _ = segment.signal_inters[-1]
    start_gh = start_inter.geohash_7
    end_gh = end_inter.geohash_7
    key = (start_gh, end_gh)
    seq_counter[key] = seq_counter.get(key, 0) + 1
    seq_no = seq_counter[key]
    line_id = make_line_id(start_inter.inter_id, end_inter.inter_id, seq_no)

    line_length = round(sum(link.length_m for link in segment.oriented_links), 2)
    gaps = [g for _, _, g in segment.signal_inters[1:] if g is not None]
    inter_names = {i.inter_id: i.inter_name for i, _, _ in segment.signal_inters}

    start_cross = cross_road_at_inter(
        start_inter.inter_id,
        primary_road=segment.road_name,
        inter_map=inter_map,
        prev_link=segment.oriented_links[0] if segment.oriented_links else None,
        next_link=segment.oriented_links[1] if len(segment.oriented_links) > 1 else None,
    )
    end_cross = cross_road_at_inter(
        end_inter.inter_id,
        primary_road=segment.road_name,
        inter_map=inter_map,
        prev_link=segment.oriented_links[-2] if len(segment.oriented_links) > 1 else None,
        next_link=segment.oriented_links[-1] if segment.oriented_links else None,
    )

    line_row = {
        "line_id": line_id,
        "line_name": format_line_name(
            segment.road_name,
            start_cross,
            end_cross,
            start_inter_name=start_inter.inter_name,
            end_inter_name=end_inter.inter_name,
        ),
        "road_name": segment.road_name,
        "start_cross_road_name": start_cross or None,
        "end_cross_road_name": end_cross or None,
        "start_geohash_7": start_gh,
        "end_geohash_7": end_gh,
        "seq_no": seq_no,
        "start_inter_id": start_inter.inter_id,
        "end_inter_id": end_inter.inter_id,
        "start_inter_name": start_inter.inter_name,
        "end_inter_name": end_inter.inter_name,
        "link_count": len(segment.oriented_links),
        "inter_count": len(segment.signal_inters),
        "line_length_m": line_length,
        "max_inter_gap_m": round(max(gaps), 2) if gaps else None,
        "min_inter_gap_m": round(min(gaps), 2) if gaps else None,
        "order_rule": ORDER_RULE,
        "link_ids_ordered_json": json.dumps(
            [link.link.link_id for link in segment.oriented_links], ensure_ascii=False
        ),
        "inter_ids_ordered_json": json.dumps(
            [i.inter_id for i, _, _ in segment.signal_inters], ensure_ascii=False
        ),
        "inter_names_json": json.dumps(inter_names, ensure_ascii=False),
        "scope_version_id": segment.scope_version_id or None,
        "calc_version": CALC_VERSION,
        "is_deleted": 0,
    }

    link_rows: list[dict[str, Any]] = []
    cum = 0.0
    for seq, oriented in enumerate(segment.oriented_links, start=1):
        link_rows.append(
            {
                "line_id": line_id,
                "seq_no": seq,
                "link_id": oriented.link.link_id,
                "road_name": oriented.link.road_name,
                "length_m": round(oriented.length_m, 2),
                "f_inter_id": oriented.f_inter_id,
                "t_inter_id": oriented.t_inter_id,
                "cum_length_m": round(cum, 2),
                "is_deleted": 0,
            }
        )
        cum += oriented.length_m

    inter_rows: list[dict[str, Any]] = []
    for seq, (inter, cum_dist, gap) in enumerate(segment.signal_inters, start=1):
        cross = cross_road_at_inter(
            inter.inter_id,
            primary_road=segment.road_name,
            inter_map=inter_map,
            prev_link=next(
                (
                    segment.oriented_links[i]
                    for i in range(len(segment.oriented_links))
                    if segment.oriented_links[i].t_inter_id == inter.inter_id
                ),
                None,
            ),
            next_link=next(
                (
                    segment.oriented_links[i]
                    for i in range(len(segment.oriented_links))
                    if segment.oriented_links[i].f_inter_id == inter.inter_id
                ),
                None,
            ),
        )
        inter_rows.append(
            {
                "line_id": line_id,
                "seq_no": seq,
                "inter_id": inter.inter_id,
                "inter_name": inter.inter_name,
                "cross_road_name": cross or None,
                "lon": inter.lon,
                "lat": inter.lat,
                "geohash_7": inter.geohash_7,
                "cum_length_m": round(cum_dist, 2),
                "gap_to_prev_m": round(gap, 2) if gap is not None else None,
                "is_deleted": 0,
            }
        )

    return line_row, link_rows, inter_rows


def _resolve_link_table(conn: Any, schema: str) -> str:
    preferred = (os.getenv("PG_DIM_LINK_TABLE") or "dim_link_info").strip()
    candidates: list[str] = []
    for name in ("dim_link_info", preferred):
        if name and name not in candidates:
            candidates.append(name)
    with conn.cursor() as cur:
        for table in candidates:
            cur.execute(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
                LIMIT 1
                """,
                (schema, table),
            )
            if cur.fetchone():
                return table
    return "dim_link_info"


def fetch_scope_links(conn: Any, schema: str, road_name: str | None = None) -> list[LinkRow]:
    scope_q = _qualified(schema, TABLE_SCOPE)
    link_table = _resolve_link_table(conn, schema)
    link_q = _qualified(schema, link_table)
    channel_table = os.getenv("PG_CHANNEL_TABLE", "dwd_tfc_rltn_wide_inter_ft_link")
    channel_q = _qualified(schema, channel_table)
    filter_sql = ""
    params: list[Any] = []
    if road_name:
        filter_sql = " AND split_part(l.road_name, ':', 1) = %s"
        params.append(road_name)

    sql = f"""
SELECT
    l.link_id::text AS link_id,
    l.road_name,
    COALESCE(l.length_m, 0)::float8 AS length_m,
    l.f_inter_id::text AS f_inter_id,
    l.t_inter_id::text AS t_inter_id,
    (
        SELECT u.version_id::text
        FROM {scope_q} u
        WHERE COALESCE(u.is_deleted, 0) = 0
        ORDER BY u.version_id DESC NULLS LAST
        LIMIT 1
    ) AS version_id,
    ST_X(ST_Centroid(ST_GeomFromText(l.geom, 4326))) AS lon,
    ST_Y(ST_Centroid(ST_GeomFromText(l.geom, 4326))) AS lat
FROM {link_q} l
WHERE l.geom IS NOT NULL
  AND l.f_inter_id IS NOT NULL
  AND l.t_inter_id IS NOT NULL
  AND split_part(COALESCE(l.road_name, ''), ':', 1) NOT IN ('', '无名道路', '未命名')
  AND EXISTS (
        SELECT 1
        FROM {scope_q} u
        WHERE COALESCE(u.is_deleted, 0) = 0
          AND ST_Intersects(
                ST_GeomFromText(l.geom, 4326),
                u.geom_boundary::geometry
          )
  )
  AND EXISTS (
        SELECT 1
        FROM {channel_q} ch
        WHERE ch.link_id = l.link_id
  )
  {filter_sql}
"""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    out: list[LinkRow] = []
    for row in rows:
        road_name_text = str(row.get("road_name") or "")
        if not is_named_road(road_name_text):
            continue
        primary = extract_primary_road(road_name_text)
        if not primary:
            continue
        out.append(
            LinkRow(
                link_id=str(row["link_id"]),
                road_name=road_name_text,
                primary_road=primary,
                length_m=float(row.get("length_m") or 0.0),
                f_inter_id=str(row.get("f_inter_id") or ""),
                t_inter_id=str(row.get("t_inter_id") or ""),
                lon=float(row.get("lon") or 0.0),
                lat=float(row.get("lat") or 0.0),
                version_id=str(row.get("version_id") or ""),
            )
        )
    return out


def fetch_inter_map(conn: Any, schema: str, inter_ids: set[str]) -> dict[str, InterRow]:
    if not inter_ids:
        return {}
    inter_table = os.getenv("PG_DIM_INTER_TABLE", "dim_inter_info")
    inter_q = _qualified(schema, inter_table)
    sql = f"""
SELECT
    inter_id::text AS inter_id,
    inter_name,
    COALESCE(is_signalized, 0)::int AS is_signalized,
    ST_X(ST_GeomFromText(geom_center, 4326)) AS lon,
    ST_Y(ST_GeomFromText(geom_center, 4326)) AS lat
FROM {inter_q}
WHERE inter_id = ANY(%s)
"""
    with conn.cursor() as cur:
        cur.execute(sql, (list(inter_ids),))
        rows = cur.fetchall()

    out: dict[str, InterRow] = {}
    for row in rows:
        inter_id = str(row.get("inter_id") or "")
        if not inter_id:
            continue
        out[inter_id] = InterRow(
            inter_id=inter_id,
            inter_name=str(row.get("inter_name") or ""),
            is_signalized=int(row.get("is_signalized") or 0) == 1,
            lon=float(row.get("lon") or 0.0),
            lat=float(row.get("lat") or 0.0),
        )
    return out


def generate_lines(
    links: list[LinkRow],
    inter_map: dict[str, InterRow],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[LinkRow]] = defaultdict(list)
    version_by_group: dict[str, str] = {}
    for link in links:
        grouped[link.primary_road].append(link)
        prev = version_by_group.get(link.primary_road, "")
        if link.version_id and link.version_id > prev:
            version_by_group[link.primary_road] = link.version_id

    line_rows: list[dict[str, Any]] = []
    link_rows: list[dict[str, Any]] = []
    inter_rows: list[dict[str, Any]] = []
    seq_counter: dict[tuple[str, str], int] = {}

    for road_name in sorted(grouped):
        paths = build_paths(grouped[road_name])
        segments = build_line_segments(
            road_name,
            paths,
            inter_map,
            version_by_group.get(road_name, ""),
        )
        for segment in segments:
            line_row, seg_link_rows, seg_inter_rows = line_rows_from_segment(
                segment, inter_map, seq_counter
            )
            line_rows.append(line_row)
            link_rows.extend(seg_link_rows)
            inter_rows.extend(seg_inter_rows)

    return line_rows, link_rows, inter_rows


def _strip_sql_comments(text: str) -> str:
    lines = [line for line in text.splitlines() if not line.strip().startswith("--")]
    return "\n".join(lines)


def ensure_tables(conn: Any, schema: str) -> None:
    sql_path = Path(__file__).resolve().parents[3] / "tools" / "line_schema_pg.sql"
    ddl = _strip_sql_comments(sql_path.read_text(encoding="utf-8"))
    ddl = ddl.replace('"road6"', _qident(schema))
    statements = [s.strip() for s in ddl.split(";") if s.strip()]
    with conn.cursor() as cur:
        for stmt in statements:
            cur.execute(stmt)
    conn.commit()


def write_rows(
    conn: Any,
    schema: str,
    line_rows: list[dict[str, Any]],
    link_rows: list[dict[str, Any]],
    inter_rows: list[dict[str, Any]],
) -> dict[str, int]:
    ensure_tables(conn, schema)
    line_q = _qualified(schema, TABLE_LINE)
    link_q = _qualified(schema, TABLE_LINE_LINK)
    inter_q = _qualified(schema, TABLE_LINE_INTER)

    def _insert_rows(
        cur: Any,
        *,
        table_q: str,
        columns: list[str],
        rows: list[dict[str, Any]],
    ) -> int:
        if not rows:
            return 0
        col_sql = ", ".join(_qident(c) for c in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        sql = f"INSERT INTO {table_q} ({col_sql}) VALUES ({placeholders})"
        values = [tuple(row.get(col) for col in columns) for row in rows]
        for offset in range(0, len(values), 1000):
            cur.executemany(sql, values[offset : offset + 1000])
        return len(rows)

    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {inter_q}")
        cur.execute(f"DELETE FROM {link_q}")
        cur.execute(f"DELETE FROM {line_q}")
        line_count = _insert_rows(cur, table_q=line_q, columns=LINE_COLUMNS, rows=line_rows)
        link_count = _insert_rows(
            cur, table_q=link_q, columns=LINK_RLTN_COLUMNS, rows=link_rows
        )
        inter_count = _insert_rows(
            cur, table_q=inter_q, columns=INTER_RLTN_COLUMNS, rows=inter_rows
        )
    conn.commit()
    return {
        "line_rows": line_count,
        "link_rltn_rows": link_count,
        "inter_rltn_rows": inter_count,
    }


def run_build(
    *,
    truncate: bool = False,
    road_name: str | None = None,
    skip_db: bool = False,
) -> dict[str, Any]:
    schema = os.getenv("PGSCHEMA", "road6")
    conn = connect_pg()
    try:
        links = fetch_scope_links(conn, schema, road_name=road_name)
        inter_ids: set[str] = set()
        for link in links:
            inter_ids.add(link.f_inter_id)
            inter_ids.add(link.t_inter_id)
        inter_map = fetch_inter_map(conn, schema, inter_ids)
        line_rows, link_rows, inter_rows = generate_lines(links, inter_map)

        result: dict[str, Any] = {
            "schema": schema,
            "scope_link_count": len(links),
            "line_count": len(line_rows),
            "link_rltn_count": len(link_rows),
            "inter_rltn_count": len(inter_rows),
            "road_name_filter": road_name,
            "calc_version": CALC_VERSION,
        }

        if skip_db:
            result["sample_lines"] = [row["line_name"] for row in line_rows[:5]]
            return result

        if truncate:
            counts = write_rows(conn, schema, line_rows, link_rows, inter_rows)
        else:
            ensure_tables(conn, schema)
            counts = write_rows(conn, schema, line_rows, link_rows, inter_rows)
        result.update(counts)
        return result
    finally:
        conn.close()


def main() -> None:
    load_project_env()
    parser = argparse.ArgumentParser(description="生成道路 line 维表")
    parser.add_argument("--truncate", action="store_true", help="清空后全量写入")
    parser.add_argument("--road-name", help="仅生成指定主路名")
    parser.add_argument("--skip-db", action="store_true", help="仅计算不写库")
    args = parser.parse_args()

    started = time.perf_counter()
    result = run_build(
        truncate=args.truncate,
        road_name=args.road_name,
        skip_db=args.skip_db,
    )
    elapsed = time.perf_counter() - started
    print(json.dumps({**result, "elapsed_sec": round(elapsed, 2)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
