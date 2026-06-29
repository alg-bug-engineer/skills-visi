"""命令行入口：``python -m region_scan.cli scan`` 一条命令完成全区域扫描。"""

from __future__ import annotations

import argparse
import asyncio
import sys

from intersection_agent.db.postgres import PostgresPool

from region_scan.config import get_scan_settings
from region_scan.scan_engine import run_region_scan
from region_scan.snapshot import save_run


async def _scan(args: argparse.Namespace) -> int:
    settings = get_scan_settings()
    pool = PostgresPool(settings.base)
    periods = args.periods.split(",") if args.periods else None

    def _progress(done: int, total: int) -> None:
        if total and (done % 20 == 0 or done == total):
            print(f"  进度 {done}/{total}", file=sys.stderr)

    print("开始区域扫描…", file=sys.stderr)
    run = await run_region_scan(
        pool,
        settings,
        periods=periods,
        concurrency=args.concurrency,
        region=args.region,
        progress=_progress,
    )
    await pool.close()

    path = save_run(run, settings.snapshot_dir)
    bands: dict[str, int] = {}
    for r in run.records:
        bands[r.get("problem_band", "?")] = bands.get(r.get("problem_band", "?"), 0) + 1
    pilots = sum(1 for r in run.records if r.get("pilot_score"))
    print(f"扫描完成：run_id={run.run_id}")
    print(f"  路口 {run.intersection_total} 个（覆盖 {run.covered}），记录 {len(run.records)} 条")
    print(f"  分层分布：{bands}")
    print(f"  试点候选（配时可解，有分）：{pilots} 条")
    print(f"  快照：{path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="region-scan", description="区域路口扫描与试点选择")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="对全部信号路口跑完整诊断并产出快照")
    scan.add_argument("--periods", default="", help="逗号分隔时段，默认用配置（早高峰,白平峰,晚高峰）")
    scan.add_argument("--concurrency", type=int, default=None, help="并发度，默认用配置")
    scan.add_argument("--region", default="全域", help="区域标签")
    scan.set_defaults(func=_scan)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
