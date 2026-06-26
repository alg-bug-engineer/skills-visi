#!/usr/bin/env python3
"""CLI probe for problem-validation evidence and constraint quantization."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from intersection_agent.models.domain import NluResult, TimePeriod
from intersection_agent.services.constraint_resolver_service import ConstraintResolverService
from intersection_agent.services.data_fetcher import DataFetcher
from intersection_agent.services.intersection_cognition_service import IntersectionCognitionService
from intersection_agent.services.intersection_resolver import IntersectionResolver
from intersection_agent.services.problem_evidence_service import ProblemEvidenceService
from intersection_agent.utils.terminal_report import format_evidence_report


DEFAULT_INTER = "奥体西路与经十路交叉口"
DEFAULT_PERIOD = TimePeriod(start="16:00", end="18:00", label="晚高峰")
DEFAULT_CONTEXT = "奥体西路与经十路交叉口，下午四点南北向经常拥堵，要考虑垂直方向不能溢出"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Probe problem evidence for an intersection.")
    parser.add_argument("--intersection", default=DEFAULT_INTER, help="路口口语名称")
    parser.add_argument("--start", default="16:00", help="时段开始 HH:MM")
    parser.add_argument("--end", default="18:00", help="时段结束 HH:MM")
    parser.add_argument("--label", default="晚高峰", help="时段标签")
    parser.add_argument("--directions", default="南北向", help="关注方向，逗号分隔")
    parser.add_argument("--context", default=DEFAULT_CONTEXT, help="用户完整描述（含约束/星期）")
    parser.add_argument("--reference-date", default="", help="参考日 YYYY-MM-DD")
    parser.add_argument("--user-suggestion", default="", help="用户约束/建议")
    args = parser.parse_args()

    ref = date.fromisoformat(args.reference_date) if args.reference_date else None
    tp = TimePeriod(start=args.start, end=args.end, label=args.label)
    directions = [d.strip() for d in args.directions.split(",") if d.strip()]
    user_suggestion = args.user_suggestion or None
    if not user_suggestion and "溢出" in args.context:
        user_suggestion = "要考虑垂直方向不能溢出"

    resolver = IntersectionResolver()
    resolution = await resolver.resolve(args.intersection)
    if not resolution.inter_id:
        print(f"路口未解析: {args.intersection}", file=sys.stderr)
        if resolution.candidates:
            print("候选:", resolution.candidates[:5], file=sys.stderr)
        sys.exit(1)

    nlu = NluResult(
        intersection=args.intersection,
        time_period=tp,
        problem_type="congestion",
        directions=directions,
        user_suggestion=user_suggestion,
    )

    fetcher = DataFetcher()
    cognition_svc = IntersectionCognitionService()
    evidence_svc = ProblemEvidenceService()
    constraint_svc = ConstraintResolverService()

    data = await fetcher.fetch(resolution.inter_id, resolution.inter_name, nlu, reference_date=ref)
    cognition = await cognition_svc.fetch(resolution.inter_id, resolution.inter_name, nlu)
    payload = {**data, "cognition": cognition}

    evidence = await evidence_svc.build(
        resolution.inter_id,
        resolution.inter_name,
        nlu,
        data_payload=payload,
        user_context=args.context,
        reference_date=ref,
    )
    constraints = None
    if user_suggestion:
        constraints = constraint_svc.resolve(
            user_suggestion,
            nlu_directions=directions,
            problem_evidence=evidence,
        )

    print(
        format_evidence_report(evidence, constraints),
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
