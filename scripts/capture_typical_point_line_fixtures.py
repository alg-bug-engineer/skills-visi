#!/usr/bin/env python3
"""批量采集 docs/典型输入案例-点线优化.md 三类 Case（A/B/D）的前端 mock fixture。

用法：
  # 采集全部（需 LLM_MOCK=false、PG、QWEN 可用，每例数十秒）
  PYTHONPATH=. .venv/bin/python scripts/capture_typical_point_line_fixtures.py --live

  # 仅采集指定 Case
  PYTHONPATH=. .venv/bin/python scripts/capture_typical_point_line_fixtures.py --live --case case_a

  # 跳过方案证据校验（仅诊断/成因联调，plan 不完整时）
  PYTHONPATH=. .venv/bin/python scripts/capture_typical_point_line_fixtures.py --live --relax-evidence

产物：frontend/src/mock/cases/<fixture>（清单见 manifest.json）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.capture_frontend_mock import _validate_public_evidence, _write

MANIFEST = PROJECT_ROOT / "frontend/src/mock/cases/manifest.json"
CASES_DIR = PROJECT_ROOT / "frontend/src/mock/cases"


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def write_if_valid(public: dict, out_path: Path, *, relax: bool) -> int:
    if not relax:
        errors = _validate_public_evidence(public)
        if errors:
            print(f"✗ 证据字段不完整，拒绝写入 {out_path.name}:")
            for e in errors:
                print(f"  - {e}")
            return 3
    _write(public, out_path)
    return 0


async def capture_one(case: dict, *, relax: bool) -> int:
    from app.config import get_settings
    from app.services.agent_service import AgentService
    from app.api.response_builder import build_public_run_response

    settings = get_settings()
    if getattr(settings, "llm_mock", False):
        print("✗ LLM_MOCK=true：请设 false 后重跑。")
        return 3

    query = case["query"]
    out_path = CASES_DIR / case["fixture"]
    print(f"\n▶ [{case['code']}] {case['label']} → {out_path.name}")
    print(f"  inter_id={case['inter_id']}")
    print(f"  输入：{query[:80]}…")

    agent = AgentService(settings)
    result = await agent.run(query)
    public = build_public_run_response(result)
    if not public.get("completed"):
        print("⚠️  流水线未完整完成；仍写入供部分幕联调（可加 --relax-evidence）。")
    return write_if_valid(public, out_path, relax=relax)


async def main_async(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    cases = manifest.get("cases") or []
    if args.case:
        cases = [c for c in cases if c.get("id") == args.case or c.get("code", "").lower() == args.case.lower()]
        if not cases:
            print(f"✗ 未找到 case: {args.case}")
            return 1

    CASES_DIR.mkdir(parents=True, exist_ok=True)
    rc = 0
    for case in cases:
        code = await capture_one(case, relax=args.relax_evidence)
        if code != 0:
            rc = code
    print(f"\n完成。清单：{MANIFEST.relative_to(PROJECT_ROOT)}")
    print("前端联调：VITE_MOCK=1，在主页点 Case 芯片；display_name 可在 manifest.json 手改。")
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description="批量采集点/线优化典型 Case 前端 fixture")
    parser.add_argument("--live", action="store_true", help="发起真实 agent/run 请求")
    parser.add_argument("--case", help="仅采集 case_a / A 等")
    parser.add_argument(
        "--relax-evidence",
        action="store_true",
        help="跳过 plan 证据字段校验（诊断/成因幕联调）",
    )
    args = parser.parse_args()
    if not args.live:
        parser.print_help()
        print("\n请使用 --live 发起采集。")
        return 1
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
