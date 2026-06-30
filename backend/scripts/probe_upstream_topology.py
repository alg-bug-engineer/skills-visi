#!/usr/bin/env python3
"""拓扑溯源数据嗅探：对照 link 邻接 / 干线 seq / flow_correlate / 方位角。

运行（需 backend/.env 且 MOCK_DB=0）：
  cd backend && .venv/bin/python scripts/probe_upstream_topology.py
  cd backend && .venv/bin/python scripts/probe_upstream_topology.py \\
      --inter 011wwe28ctu00001 --dir8 6 --turn 1
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from intersection_agent.config import get_settings
from intersection_agent.db.postgres import PostgresPool
from intersection_agent.services.flow_trace_service import (
    day_labels_for_filter,
    lock_one_hop,
    one_hop_for_approach,
    period_type_from_label,
)
from intersection_agent.services.upstream_topology_service import (
    UpstreamTopologyService,
    _bearing_deg,
    _DIR8_UPSTREAM_BEARING,
    _angle_diff,
)
from intersection_agent.utils.traffic_labels import DIR8_LABELS

ARTIFACTS = ROOT.parent / "artifacts" / "upstream-probe"
DEFAULT_INTER = "011wwe28ctu00001"


async def probe(
    inter_id: str,
    dir8: int,
    turn: int | None,
) -> dict:
    settings = get_settings()
    pool = PostgresPool(settings)
    await pool.connect()
    topo = UpstreamTopologyService(settings=settings, pool=pool)
    fs, rs, vid = settings.pg_flow_schema, settings.pgschema, settings.pg_version_id

    center = await topo.inter_center(inter_id)
    link = await topo.resolve_approach_link(inter_id, dir8)
    line_prevs = await topo.resolve_line_prev_candidates(inter_id)

    period_type = period_type_from_label("晚高峰")
    day_labels = day_labels_for_filter((1, 2, 3, 4, 5))
    rows = await pool.fetch(
        f"""
        SELECT fc.f_dir8_no, fc.turn_dir_no, fc.cor_inter_id, fc.cor_f_dir8_no,
               fc.cor_turn_dir_no, fc.flow_share_ratio,
               cor.inter_name AS cor_inter_name,
               ST_X(ST_GeomFromText(cor.geom_center)) AS cor_lng,
               ST_Y(ST_GeomFromText(cor.geom_center)) AS cor_lat
        FROM {fs}.dws_tfc_inter_turn_flow_correlate_m fc
        LEFT JOIN {rs}.dim_inter_info cor
          ON cor.inter_id = fc.cor_inter_id AND cor.version_id = $3
        WHERE fc.inter_id = $1 AND fc.trace_type = 'UPSTREAM' AND fc.is_deleted = 0
          AND fc.period_type = $2 AND fc.day_of_week = ANY($4::text[])
          AND fc.f_dir8_no = $5
          AND ($6::int IS NULL OR fc.turn_dir_no = $6)
          AND fc.month = (
              SELECT MAX(m.month) FROM {fs}.dws_tfc_inter_turn_flow_correlate_m m
              WHERE m.inter_id = $1 AND m.is_deleted = 0
          )
        ORDER BY fc.flow_share_ratio DESC
        LIMIT 8
        """,
        inter_id,
        period_type,
        vid,
        day_labels,
        dir8,
        turn,
    )
    correlate_top = [dict(r) for r in rows]
    correlate_hop = one_hop_for_approach(
        [
            {
                **r,
                "f_dir8_no": r["f_dir8_no"],
                "turn_dir_no": r["turn_dir_no"],
            }
            for r in await pool.fetch(
                f"""
                SELECT f_dir8_no, turn_dir_no, cor_inter_id, cor_f_dir8_no, cor_turn_dir_no,
                       flow_share_ratio, cor.inter_name AS cor_inter_name,
                       ST_X(ST_GeomFromText(cor.geom_center)) AS cor_lng,
                       ST_Y(ST_GeomFromText(cor.geom_center)) AS cor_lat
                FROM {fs}.dws_tfc_inter_turn_flow_correlate_m fc
                LEFT JOIN {rs}.dim_inter_info cor
                  ON cor.inter_id = fc.cor_inter_id AND cor.version_id = $3
                WHERE fc.inter_id = $1 AND fc.trace_type = 'UPSTREAM' AND fc.is_deleted = 0
                  AND fc.period_type = $2 AND fc.day_of_week = ANY($4::text[])
                  AND fc.month = (
                      SELECT MAX(m.month) FROM {fs}.dws_tfc_inter_turn_flow_correlate_m m
                      WHERE m.inter_id = $1 AND m.is_deleted = 0
                  )
                """,
                inter_id,
                period_type,
                vid,
                day_labels,
            )
        ],
        dir8,
    )

    topo_hop = await topo.pick_upstream_hop(
        inter_id,
        dir8,
        turn=turn,
        correlate_rows=[dict(r) for r in rows] if rows else [],
        target_lon=center[0] if center else None,
        target_lat=center[1] if center else None,
    )

    mismatch = False
    if correlate_hop and topo_hop:
        mismatch = str(correlate_hop.get("cor_inter_id")) != str(topo_hop.get("cor_inter_id"))

    bearings = []
    if center:
        for r in correlate_top[:5]:
            if r.get("cor_lng") is None:
                continue
            b = _bearing_deg(center[0], center[1], float(r["cor_lng"]), float(r["cor_lat"]))
            expected = _DIR8_UPSTREAM_BEARING.get(dir8, 0)
            bearings.append(
                {
                    "name": r.get("cor_inter_name"),
                    "cor_inter_id": r.get("cor_inter_id"),
                    "coverage": float(r.get("flow_share_ratio") or 0),
                    "bearing_deg": round(b, 1),
                    "bearing_ok": _angle_diff(b, expected) <= 45,
                }
            )

    report = {
        "inter_id": inter_id,
        "dir8": dir8,
        "dir8_label": DIR8_LABELS.get(dir8),
        "turn": turn,
        "topo_link": link,
        "line_prev": line_prevs,
        "topo_hop": topo_hop,
        "correlate_hop_legacy": correlate_hop,
        "correlate_top": correlate_top,
        "bearing_analysis": bearings,
        "mismatch_topo_vs_correlate_legacy": mismatch,
    }
    await pool.close()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="上游拓扑嗅探")
    parser.add_argument("--inter", default=DEFAULT_INTER)
    parser.add_argument("--dir8", type=int, default=6, help="0北 2东 4南 6西")
    parser.add_argument("--turn", type=int, default=1, help="1左 2直 3右")
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()

    report = asyncio.run(probe(args.inter, args.dir8, args.turn))
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out = ARTIFACTS / f"{args.inter}_d{args.dir8}_t{args.turn or 0}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json_only:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    th = report.get("topo_hop") or {}
    ch = report.get("correlate_hop_legacy") or {}
    print(f"路口 {args.inter} {DIR8_LABELS.get(args.dir8)} turn={args.turn}")
    print(f"  拓扑一跳: {th.get('cor_inter_name')} ({th.get('cor_inter_id')})")
    print(f"  旧算法一跳: {ch.get('cor_inter_name')} ({ch.get('cor_inter_id')})")
    print(f"  MISMATCH: {report.get('mismatch_topo_vs_correlate_legacy')}")
    print(f"  path_points: {len(th.get('path') or [])} source={th.get('path_source')}")
    print(f"  报告: {out}")


if __name__ == "__main__":
    main()
