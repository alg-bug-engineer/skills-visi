"""Command line entry for deterministic signal optimization workflows."""

from __future__ import annotations

import argparse
from pathlib import Path

from data import export_intersection_data, read_json, write_json
from optimization import (
    optimize_corridor,
    optimize_intersection,
    optimize_region,
)
from preprocessing import (
    build_cycle_stage_exec_history,
    build_period_plan_exec_history,
    build_standard_timing_tables,
    convert_stage_csv_to_ring_table,
    convert_timing_csv_to_stage_table,
)
from env import load_project_env
from visualization import write_plan_html


def main() -> None:
    load_project_env()
    parser = argparse.ArgumentParser(description="不用大模型的信号智能优化工程 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    _add_json_plan_command(sub, "intersection", "生成路口优化方案")
    _add_json_plan_command(sub, "corridor", "生成干线协调方案")
    _add_json_plan_command(sub, "region", "生成区域优化方案")

    stage = sub.add_parser("stage-csv", help="配时 CSV 转阶段描述 CSV")
    stage.add_argument("--input", required=True, type=Path)
    stage.add_argument("--output", required=True, type=Path)

    ring = sub.add_parser("stage-to-ring-csv", help="阶段描述 CSV 还原为可回放环结构 CSV")
    ring.add_argument("--input", required=True, type=Path)
    ring.add_argument("--output", required=True, type=Path)
    ring.add_argument("--yellow-sec", type=int, default=0, help="每阶段拆出的黄灯秒数")
    ring.add_argument("--all-red-sec", type=int, default=0, help="每阶段拆出的全红秒数")

    standard = sub.add_parser("standard-tables", help="生成信控标准表 CSV")
    standard.add_argument("--timing-csv", required=True, type=Path)
    standard.add_argument("--schedule-csv", required=True, type=Path)
    standard.add_argument("--output-dir", required=True, type=Path)
    standard.add_argument("--batch-id")

    cycle = sub.add_parser("cycle-history", help="生成周期阶段执行历史 CSV")
    cycle.add_argument("--input-csv", required=True, type=Path)
    cycle.add_argument("--output-csv", required=True, type=Path)
    cycle.add_argument("--batch-id")

    period = sub.add_parser("period-history", help="生成时段方案执行历史 CSV")
    period.add_argument("--input-csv", required=True, type=Path)
    period.add_argument("--output-csv", required=True, type=Path)
    period.add_argument("--batch-id")

    export_db = sub.add_parser("export-db", help="从 MySQL 导出路口列表与相位相序方案 JSON")
    export_db.add_argument("--output-dir", required=True, type=Path, help="导出目录")
    export_db.add_argument("--inter-id", action="append", help="可选，指定路口 ID（可重复）")
    export_db.add_argument("--plan-no", type=int, help="可选，仅导出指定方案号")
    export_db.add_argument(
        "--with-flows",
        action="store_true",
        help="按方案执行时段从 PG 车道流量表统计小时流量并填充 turnFlowTotal",
    )
    export_db.add_argument("--flow-date", help="可选，流量日期 YYYYMMDD（缺省取库内最新一天）")
    export_db.add_argument(
        "--prefer-precomputed",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="优先读取 dws_stage_green_bounds_5min_mm / dws_turn_flow_5min_mm（默认开启）",
    )
    export_db.add_argument(
        "--recompute-green-bounds",
        action="store_true",
        help="导出时跳过绿界预计算表，按当前算法重算阶段绿界",
    )
    export_db.add_argument(
        "--recompute-flows",
        action="store_true",
        help="导出流量时跳过 dws_turn_flow_5min_mm，从 PG 原始流量重算",
    )

    viz = sub.add_parser("visualize", help="优化结果 JSON 转 HTML 报告")
    viz.add_argument("--input", required=True, type=Path)
    viz.add_argument("--output", required=True, type=Path)

    segment = sub.add_parser("segment-periods", help="基于 5 分钟车道转向流量自动划分配时时段")
    segment.add_argument("--input-json", type=Path, help="可选，已导出的 5 分钟流量时序 JSON")
    segment.add_argument("--inter-id", help="可选，从 PostgreSQL 读取指定路口全天流量")
    segment.add_argument("--flow-date", help="可选，流量日期 YYYYMMDD；与 day-plan-no 二选一")
    segment.add_argument(
        "--day-plan-no",
        type=int,
        help="可选，日计划号；按 timing-optimizer 相同逻辑解析星期类型并优先读取历史均值 profile",
    )
    segment.add_argument("--output-json", required=True, type=Path, help="输出划分结果 JSON")
    segment.add_argument("--output-html", type=Path, help="可选，输出 HTML 测试报告")
    segment.add_argument("--min-period-minutes", type=int, default=15, help="最小时段长度，默认 15")
    segment.add_argument("--min-periods", type=int, default=3, help="每天最少时段数，默认 3")
    segment.add_argument("--max-periods", type=int, default=15, help="每天最多时段数，默认 15")

    segment_llm = sub.add_parser(
        "segment-periods-llm",
        help="调用大模型，基于二次平滑流量划分配时时段",
    )
    segment_llm.add_argument("--input-json", type=Path, help="可选，已导出的 5 分钟流量时序 JSON")
    segment_llm.add_argument("--inter-id", help="可选，从数据库读取指定路口全天流量")
    segment_llm.add_argument("--flow-date", help="可选，流量日期 YYYYMMDD")
    segment_llm.add_argument("--day-plan-no", type=int, help="可选，日计划号")
    segment_llm.add_argument("--output-json", required=True, type=Path, help="输出划分结果 JSON")
    segment_llm.add_argument("--output-html", type=Path, help="可选，输出 HTML 测试报告")
    segment_llm.add_argument("--min-period-minutes", type=int, default=15)
    segment_llm.add_argument("--min-periods", type=int, default=3)
    segment_llm.add_argument("--max-periods", type=int, default=15)
    segment_llm.add_argument(
        "--dump-llm-input",
        type=Path,
        help="可选，另存大模型输入 JSON（二次平滑流量包）",
    )

    serve = sub.add_parser("serve", help="启动可视化 Web 服务")
    serve.add_argument("--host", default="127.0.0.1", help="监听地址")
    serve.add_argument("--port", default=8020, type=int, help="监听端口")
    serve.add_argument("--reload", action="store_true", help="开发模式自动重载")

    manual_import = sub.add_parser("manual-survey-import", help="人工调查 HTML → MySQL ODS")
    manual_import.add_argument(
        "--html",
        type=Path,
        default=Path("docs/济南信控路口问题点位地图.html"),
    )
    manual_import.add_argument("--survey-batch", default="jinan_2025")
    manual_import.add_argument(
        "--output-json",
        type=Path,
        default=Path("data/manual_survey_issue_raw_jinan_2025.json"),
    )

    manual_dwd = sub.add_parser("manual-survey-dwd", help="人工调查 ODS → DWD（路网融合）")
    manual_dwd.add_argument("--survey-batch", default="jinan_2025")
    manual_dwd.add_argument(
        "--match-report",
        type=Path,
        default=Path("data/manual_survey_inter_match_report_jinan_2025.csv"),
    )

    field_import = sub.add_parser("field-survey-import", help="交通组织调研 PDF → MySQL ODS")
    field_import.add_argument(
        "--pdf",
        type=Path,
        default=Path("docs/济南市重点路口交通组织调研报告20260609.pdf"),
    )
    field_import.add_argument("--report-batch", default="jinan_20260609")
    field_import.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/field_survey/jinan_20260609"),
    )

    field_dwd = sub.add_parser("field-survey-dwd", help="交通组织调研 ODS → DWD（路网融合）")
    field_dwd.add_argument("--report-batch", default="jinan_20260609")
    field_dwd.add_argument(
        "--match-report",
        type=Path,
        default=Path("data/field_survey/jinan_20260609/match_report.csv"),
    )

    corridor_dws = sub.add_parser("corridor-coord-dws", help="生成干线协调 DWS 表并写入 MySQL")
    corridor_dws.add_argument("--min-size", type=int, default=2, help="协调组最少路口数")
    corridor_dws.add_argument(
        "--require-ctrl-mode",
        default=None,
        help="可选，仅保留指定控制方式（如 31=协调配时）",
    )
    corridor_dws.add_argument("--skip-db", action="store_true", help="仅统计，不写入 MySQL")

    corridor_stop_dws = sub.add_parser(
        "corridor-coord-stop-dws",
        help="生成干线协调停车指标 DWS 表并写入 PostgreSQL",
    )
    corridor_stop_dws.add_argument("--truncate", action="store_true", help="写入前清空目标表")
    corridor_stop_dws.add_argument("--skip-db", action="store_true", help="仅计算，不写入数据库")

    atom_lane = sub.add_parser(
        "atom-lane-enrich",
        help="完善 dwd_ctl_inter_signal_atom_lane_mapping 的信号原子与车道号映射",
    )
    atom_lane.add_argument("--inter-id", help="可选，仅处理指定路口")
    atom_lane.add_argument(
        "--target-table",
        default="dwd_ctl_inter_signal_atom_lane_mapping",
        help="目标映射表名",
    )
    atom_lane.add_argument(
        "--skip-sync",
        action="store_true",
        help="跳过从 plan_cfg.signal_atom_json 同步信号原子字段",
    )

    lane_phase = sub.add_parser(
        "lane-phase-mapping",
        help="生成 dwd_ctl_inter_plan_lane_phase_mapping 车道簇-相位-阶段统一映射表",
    )
    lane_phase.add_argument("--inter-id", help="可选，仅处理指定路口")
    lane_phase.add_argument("--plan-no", type=int, help="可选，仅处理指定方案号")
    lane_phase.add_argument(
        "--atom-table",
        default="dwd_ctl_inter_signal_atom_lane_mapping",
        help="输入 atom-lane 映射表名",
    )
    lane_phase.add_argument(
        "--target-table",
        default="dwd_ctl_inter_plan_lane_phase_mapping",
        help="目标统一映射表名",
    )
    lane_phase.add_argument("--skip-db", action="store_true", help="仅统计，不写入 MySQL")
    lane_phase.add_argument("--no-cleanup", action="store_true", help="写入前不软删除目标范围旧行")
    lane_phase.add_argument("--truncate", action="store_true", help="写入前清空目标表")

    movement_green = sub.add_parser(
        "movement-effective-green-dws",
        help="生成 dws_movement_effective_green_5min_mm movementKey 级有效绿表",
    )
    movement_green.add_argument("--inter-id", help="可选，仅处理指定路口")
    movement_green.add_argument(
        "--green-source",
        choices=["plan", "lane_phase_mapping", "exec_history"],
        default="plan",
        help="有效绿来源标记；plan 默认优先统一映射表",
    )
    movement_green.add_argument(
        "--target-table",
        default="dws_movement_effective_green_5min_mm",
        help="目标 DWS 表名",
    )
    movement_green.add_argument("--skip-db", action="store_true", help="仅统计，不写入 MySQL")

    stage_green = sub.add_parser(
        "stage-green-bounds-dws",
        help="生成 dws_stage_green_bounds_5min_mm 阶段绿界表",
    )
    stage_green.add_argument("--inter-id", help="可选，仅处理指定路口")
    stage_green.add_argument(
        "--target-table",
        default="dws_stage_green_bounds_5min_mm",
        help="目标 DWS 表名",
    )
    stage_green.add_argument("--skip-db", action="store_true", help="仅统计，不写入 MySQL")

    args = parser.parse_args()
    if args.command == "intersection":
        _run_plan(args, optimize_intersection)
    elif args.command == "corridor":
        _run_plan(args, optimize_corridor)
    elif args.command == "region":
        _run_plan(args, optimize_region)
    elif args.command == "stage-csv":
        convert_timing_csv_to_stage_table(args.input, args.output)
        print(f"已写入: {args.output}")
    elif args.command == "stage-to-ring-csv":
        convert_stage_csv_to_ring_table(
            args.input,
            args.output,
            yellow_sec=args.yellow_sec,
            all_red_sec=args.all_red_sec,
        )
        print(f"已写入: {args.output}")
    elif args.command == "standard-tables":
        counts = build_standard_timing_tables(
            args.timing_csv,
            args.schedule_csv,
            args.output_dir,
            batch_id=args.batch_id,
        )
        _print_counts(counts)
    elif args.command == "cycle-history":
        counts = build_cycle_stage_exec_history(args.input_csv, args.output_csv, batch_id=args.batch_id)
        _print_counts(counts)
    elif args.command == "period-history":
        counts = build_period_plan_exec_history(args.input_csv, args.output_csv, batch_id=args.batch_id)
        _print_counts(counts)
    elif args.command == "export-db":
        counts = export_intersection_data(
            args.output_dir,
            inter_ids=args.inter_id,
            plan_no=args.plan_no,
            with_flows=args.with_flows,
            flow_date=args.flow_date,
            prefer_precomputed=args.prefer_precomputed,
            recompute_green_bounds=args.recompute_green_bounds,
            recompute_flows=args.recompute_flows,
        )
        _print_counts(counts)
        print(f"已写入: {args.output_dir}/intersections.json 与 phase_plans/")
    elif args.command == "visualize":
        write_plan_html(read_json(args.input), args.output)
        print(f"已写入: {args.output}")
    elif args.command == "segment-periods":
        _run_segment_periods(args)
    elif args.command == "segment-periods-llm":
        _run_segment_periods_llm(args)
    elif args.command == "serve":
        _run_serve(args)
    elif args.command == "manual-survey-import":
        from preprocessing.manual_survey.import_ods import import_ods

        stats = import_ods(
            html_path=args.html,
            survey_batch=args.survey_batch,
            output_json=args.output_json,
        )
        print(
            f"ODS 导入完成: rows={stats['ods_rows']} warnings={stats['warning_count']}"
        )
    elif args.command == "manual-survey-dwd":
        from preprocessing.manual_survey.build_manual_survey_dwd import run_build

        stats = run_build(
            survey_batch=args.survey_batch,
            report_path=args.match_report,
        )
        print(
            f"DWD 生成完成: dwd_rows={stats['dwd_rows']} ods_rows={stats['ods_rows']} "
            f"survey_points={stats['survey_points']} matched={stats['matched_points']} "
            f"issue_records={stats['total_issue_records']}"
        )
    elif args.command == "field-survey-import":
        from preprocessing.field_survey.import_ods import import_ods

        stats = import_ods(
            pdf_path=args.pdf,
            report_batch=args.report_batch,
            output_dir=args.output_dir,
        )
        print(
            f"ODS 导入完成: issues={stats['issue_rows']} images={stats['image_rows']} "
            f"recommendations={stats['recommendation_rows']} matrix={stats['matrix_rows']} "
            f"warnings={stats['warning_count']}"
        )
        print(f"输出目录: {stats['output_dir']}")
    elif args.command == "field-survey-dwd":
        from preprocessing.field_survey.build_field_survey_dwd import run_build

        stats = run_build(
            report_batch=args.report_batch,
            report_path=args.match_report,
        )
        print(
            f"DWD 生成完成: dwd_rows={stats['dwd_rows']} issue_rows={stats['issue_rows']} "
            f"intersections={stats['intersections']} matched={stats['matched_intersections']}"
        )
    elif args.command == "corridor-coord-dws":
        from preprocessing.index_cal.dws_corridor_coord_info import run_build

        counts = run_build(
            min_size=args.min_size,
            require_ctrl_mode=args.require_ctrl_mode,
            skip_db=args.skip_db,
        )
        _print_counts(counts)
    elif args.command == "corridor-coord-stop-dws":
        from preprocessing.index_cal.dws_corridor_coord_stop_mm import run_build

        stats = run_build(truncate=args.truncate, skip_db=args.skip_db)
        _print_counts(stats)
    elif args.command == "atom-lane-enrich":
        from preprocessing.index_cal.dwd_signal_atom_lane_mapping_enrich import run_enrich

        counts = run_enrich(
            inter_id=args.inter_id,
            target_table=args.target_table,
            skip_sync=args.skip_sync,
        )
        _print_counts(counts)
    elif args.command == "lane-phase-mapping":
        from preprocessing.index_cal.dwd_ctl_inter_plan_lane_phase_mapping import run_build

        counts = run_build(
            inter_id=args.inter_id,
            plan_no=args.plan_no,
            atom_table=args.atom_table,
            target_table=args.target_table,
            skip_db=args.skip_db,
            cleanup=not args.no_cleanup,
            truncate=args.truncate,
        )
        _print_counts(counts)
    elif args.command == "movement-effective-green-dws":
        from preprocessing.index_cal.dws_movement_effective_green_5min_mm import build_rows, upsert_rows
        from preprocessing.timing.timing_csv_to_stage_table import _get_mysql_connection

        conn = _get_mysql_connection(streaming=False)
        try:
            rows = build_rows(conn, inter_id=args.inter_id, green_source=args.green_source)
            count = 0 if args.skip_db else upsert_rows(conn, rows, target_table=args.target_table)
        finally:
            conn.close()
        _print_counts({"target_rows": len(rows), "upsert_rows": count})
    elif args.command == "stage-green-bounds-dws":
        from preprocessing.index_cal.dws_stage_green_bounds_5min_mm import build_rows, upsert_rows
        from preprocessing.timing.timing_csv_to_stage_table import _get_mysql_connection

        conn = _get_mysql_connection(streaming=False)
        try:
            rows = build_rows(conn, inter_id=args.inter_id)
            count = 0 if args.skip_db else upsert_rows(conn, rows, target_table=args.target_table)
        finally:
            conn.close()
        _print_counts({"target_rows": len(rows), "upsert_rows": count})


def _add_json_plan_command(sub: argparse._SubParsersAction, name: str, help_text: str) -> None:
    cmd = sub.add_parser(name, help=help_text)
    cmd.add_argument("--input", required=True, type=Path, help="请求 JSON 文件")
    cmd.add_argument("--output", required=True, type=Path, help="输出方案 JSON 文件")
    cmd.add_argument("--html", type=Path, help="可选，同时输出 HTML 报告")


def _run_plan(args: argparse.Namespace, optimizer) -> None:
    plan = optimizer(read_json(args.input))
    write_json(args.output, plan)
    print(f"已写入: {args.output}")
    if args.html:
        write_plan_html(plan, args.html)
        print(f"已写入: {args.html}")


def _print_counts(counts: dict[str, int]) -> None:
    for name, count in counts.items():
        print(f"{name}: {count}")


def _run_segment_periods(args: argparse.Namespace) -> None:
    from data.flow_series_resolver import fetch_turn_flow_series_resolved
    from preprocessing.timing.period_segmentation import (
        SegmentationConfig,
        segment_timing_periods,
    )
    from visualization.period_segmentation_report import write_period_segmentation_html

    if args.input_json:
        flow_series = read_json(args.input_json)
    else:
        if not args.inter_id:
            raise SystemExit("请提供 --input-json 或 --inter-id")
        flow_series = fetch_turn_flow_series_resolved(
            args.inter_id,
            date=args.flow_date,
            day_plan_no=args.day_plan_no,
            interval_min=5,
        )
        if not (flow_series.get("series") or flow_series.get("laneGroupSeries")):
            raise SystemExit("流量库内无可用 5 分钟流量时序")

    config = SegmentationConfig(
        min_period_minutes=args.min_period_minutes,
        min_periods=args.min_periods,
        max_periods=args.max_periods,
    )
    result = segment_timing_periods(flow_series, config=config)
    write_json(args.output_json, result)
    print(f"已写入: {args.output_json}")
    if args.output_html:
        write_period_segmentation_html(result, args.output_html)
        print(f"已写入: {args.output_html}")


def _run_segment_periods_llm(args: argparse.Namespace) -> None:
    from data.flow_series_resolver import fetch_turn_flow_series_resolved
    from preprocessing.timing.period_segmentation import SegmentationConfig
    from preprocessing.timing.period_segmentation_llm import (
        build_period_segmentation_llm_input,
        segment_timing_periods_via_llm,
    )
    from visualization.period_segmentation_report import write_period_segmentation_html

    if args.input_json:
        flow_series = read_json(args.input_json)
    else:
        if not args.inter_id:
            raise SystemExit("请提供 --input-json 或 --inter-id")
        flow_series = fetch_turn_flow_series_resolved(
            args.inter_id,
            date=args.flow_date,
            day_plan_no=args.day_plan_no,
            interval_min=5,
        )
        if not (flow_series.get("series") or flow_series.get("laneGroupSeries")):
            raise SystemExit("流量库内无可用 5 分钟流量时序")

    config = SegmentationConfig(
        min_period_minutes=args.min_period_minutes,
        min_periods=args.min_periods,
        max_periods=args.max_periods,
    )
    if args.dump_llm_input:
        llm_input = build_period_segmentation_llm_input(flow_series, config=config)
        write_json(args.dump_llm_input, llm_input)
        print(f"已写入 LLM 输入: {args.dump_llm_input}")
    result = segment_timing_periods_via_llm(flow_series, config=config)
    write_json(args.output_json, result)
    print(f"已写入: {args.output_json}")
    if args.output_html:
        write_period_segmentation_html(result, args.output_html)
        print(f"已写入: {args.output_html}")


def _run_serve(args: argparse.Namespace) -> None:
    import uvicorn

    print(f"可视化服务: http://{args.host}:{args.port}/debug/")
    print(f"单路口优化: http://{args.host}:{args.port}/debug/timing-optimizer.html")
    print(f"时段划分工具: http://{args.host}:{args.port}/debug/period-segmentation-viewer.html")
    print(f"干线协调: http://{args.host}:{args.port}/debug/corridor-coordination.html")
    print(f"指标 GIS 地图: http://{args.host}:{args.port}/debug/metric-map-viewer.html")
    uvicorn.run(
        "visualization.web_app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
