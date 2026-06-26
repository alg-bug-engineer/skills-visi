"""End-to-end rehearsal for TOP3 demo intersections (requires real DB)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
os.environ["DEMO_MODE"] = "1"

from intersection_agent.config import get_settings
from intersection_agent.models.domain import NluResult, TimePeriod
from intersection_agent.services.context_tags_service import ContextTagsService
from intersection_agent.services.data_fetcher import DataFetcher
from intersection_agent.services.flow_timing_governance_service import FlowTimingGovernanceService
from intersection_agent.services.rule_engine import RuleEngine
from intersection_agent.services.sustained_metrics_service import SustainedMetricsService
from intersection_agent.utils.demo_config import load_demo_config


async def rehearse_one(
    fetcher: DataFetcher,
    sustained: SustainedMetricsService,
    context_tags: ContextTagsService,
    entry: dict,
) -> dict:
    inter_id = entry["inter_id"]
    name = entry["inter_name"]
    nlu = NluResult(
        intersection=name,
        time_period=TimePeriod(label="晚高峰", start="17:00", end="19:00"),
        problem_type="congestion",
        directions=[],
    )
    data = await fetcher.fetch(inter_id, name, nlu)
    external = await context_tags.build(inter_id, name)
    data["external_evidence"] = external
    data["meta"] = {**(data.get("meta") or {}), "demo_mode": True}
    sustained_metrics = await sustained.build(inter_id, nlu, data_payload=data)
    data["sustained_metrics"] = sustained_metrics

    rules = RuleEngine()
    diagnosis = rules.diagnose_comprehensive(data)
    governance = FlowTimingGovernanceService(rules=rules).build(data)

    detected = [p["category"] for p in governance.get("problems", []) if p.get("detected")]
    rule_ids = [r.get("id") for r in diagnosis.matched_rules]
    return {
        "inter_id": inter_id,
        "inter_name": name,
        "role": entry.get("role"),
        "missing_dws": data.get("meta", {}).get("missing_dws_coverage"),
        "saturation": data.get("traffic_flow", {}).get("saturation_rate"),
        "diagnosed": diagnosis.diagnosed,
        "matched_rules": rule_ids[:5],
        "all_rule_ids": rule_ids,
        "complaint_total": external.get("complaint_total", 0),
        "match_verdict": governance.get("match_verdict"),
        "detected_dims": detected,
        "summary": governance.get("summary"),
    }


async def main() -> None:
    settings = get_settings()
    if settings.mock_db:
        print("MOCK_DB=1，跳过真实库彩排")
        return

    cfg = load_demo_config()
    intersections = cfg.get("intersections") or []
    fetcher = DataFetcher()
    sustained = SustainedMetricsService()
    context_tags = ContextTagsService()

    print(f"Demo reference_date={cfg.get('reference_date')} DEMO_MODE=1\n")
    results = []
    for entry in intersections:
        result = await rehearse_one(fetcher, sustained, context_tags, entry)
        results.append(result)
        print(f"[{result['role']}] {result['inter_name']}")
        print(f"  inter_id={result['inter_id']}")
        print(f"  missing_dws={result['missing_dws']} sat={result['saturation']}")
        print(f"  complaints={result['complaint_total']}")
        print(f"  diagnosed={result['diagnosed']} rules={result['matched_rules']}")
        print(f"  flow_timing={result['match_verdict']} dims={result['detected_dims']}")
        print(f"  summary={result['summary']}\n")

    failed = [r for r in results if r["missing_dws"] or not r["diagnosed"]]
    secondary = next((r for r in results if r["role"] == "secondary"), None)
    if secondary and "rule_public_complaint_demo" not in secondary.get("all_rule_ids", []):
        if secondary.get("complaint_total", 0) > 0:
            print("⚠️  辅秀路口有投诉数据但未命中 rule_public_complaint_demo")
            failed.append(secondary)
        else:
            print("ℹ️  辅秀路口暂无投诉台账，跳过 complaint_demo 规则断言")
    if failed:
        print(f"⚠️  {len(failed)} 个路口未达彩排标准")
        sys.exit(1)
    print("✅ TOP3 彩排通过")


if __name__ == "__main__":
    asyncio.run(main())
