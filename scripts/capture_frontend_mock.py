"""采集一次完整的真实请求，沉淀为前端 mock fixture。

用途：把真实后端（Qwen + PG）跑出的一次完整九幕数据，固化成前端离线回放的
mock 文件，便于反复调试页面 UI/布局，避免每次重复真实请求。

产物结构与 `POST /api/v1/agent/run` 返回、`build_public_run_response` 完全一致：
  {trace_id, completed, pipeline_complete, diagnosis_ticket, phases, plan, phase_results}
前端 `endpoints.ts` 的单次回放与「模拟流式」都消费此文件。

两种采集方式：

1) 实时（发起一次真实请求，直连 Qwen/PG，耗时数十秒且依赖模型时延）：
     .venv/bin/python scripts/capture_frontend_mock.py --live ["自定义问题"] [输出路径]
   需 .env 中 LLM_MOCK=false 且 PG 可达。

2) 从运行日志提取（推荐·稳定，日志里已存真实完整 public_response，不再打模型）：
     # 默认取 logs/run_1 下最新一条 completed=true 的运行
     .venv/bin/python scripts/capture_frontend_mock.py
     # 或指定日志文件
     .venv/bin/python scripts/capture_frontend_mock.py --from-log logs/run_1/xxxx.json [输出路径]
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from app.api.response_builder import build_public_run_response

DEFAULT_INPUT = (
    "转山西路与经十路交叉口，六点十分到六点半，"
    "东向西排队溢出到上游，优先避免下游继续外溢。"
)
DEFAULT_OUT = Path("frontend/src/mock/run_1_fixture.json")
RUN_LOG_DIR = Path("logs/run_1")


def _write(public: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    phases = list((public.get("phases") or {}).keys())
    print(f"✓ 已写入 {out_path}")
    print(
        f"  trace_id={public.get('trace_id')} completed={public.get('completed')} "
        f"phases={phases} plan={public.get('plan') is not None} "
        f"phase_results={len(public.get('phase_results') or [])}"
    )


def _public_from_log(log: dict) -> dict:
    """优先复用日志内已存的 public_response；否则用 artifacts 重建。"""
    public = log.get("public_response")
    if public:
        return public
    return build_public_run_response(log)


def _find_latest_complete_log() -> Path | None:
    candidates = sorted(RUN_LOG_DIR.glob("*.json"), reverse=True)
    for path in candidates:
        if path.name.endswith("_steps.json"):
            continue
        try:
            log = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(log, dict) and log.get("completed"):
            return path
    return None


def capture_from_log(log_path: Path, out_path: Path) -> int:
    if not log_path.exists():
        print(f"✗ 日志不存在：{log_path}")
        return 1
    log = json.loads(log_path.read_text(encoding="utf-8"))
    if not log.get("completed"):
        print(f"⚠️  该运行 completed != true（可能有 phase 失败），不建议作为 mock：{log_path}")
    public = _public_from_log(log)
    print(f"▶ 从运行日志提取：{log_path}")
    _write(public, out_path)
    return 0 if public.get("completed") else 2


async def capture_live(user_input: str, out_path: Path) -> int:
    from app.config import get_settings
    from app.services.agent_service import AgentService

    settings = get_settings()
    if getattr(settings, "llm_mock", False):
        print("⚠️  LLM_MOCK=true：采集到的是 mock 数据而非真实请求（.env 设 false 后重跑）。")

    print(f"▶ 正在发起真实请求（可能数十秒）…\n  输入：{user_input}")
    agent = AgentService(settings)
    result = await agent.run(user_input)
    public = build_public_run_response(result)
    if not public.get("completed"):
        print("⚠️  流水线未完整完成（个别 phase 失败/超时）；不覆盖建议重试。")
        return 2
    _write(public, out_path)
    return 0


def main() -> int:
    args = sys.argv[1:]

    if args and args[0] == "--from-log":
        log_path = Path(args[1]) if len(args) > 1 else Path()
        out_path = Path(args[2]) if len(args) > 2 else DEFAULT_OUT
        return capture_from_log(log_path, out_path)

    if args and args[0] == "--live":
        user_input = args[1] if len(args) > 1 else DEFAULT_INPUT
        out_path = Path(args[2]) if len(args) > 2 else DEFAULT_OUT
        return asyncio.run(capture_live(user_input, out_path))

    # 默认：从最新一条 completed 的运行日志提取（稳定、不打模型）
    latest = _find_latest_complete_log()
    if latest is None:
        print(f"✗ 在 {RUN_LOG_DIR} 未找到 completed=true 的运行日志；")
        print("  可先跑一次真实请求（modules/run_1.py 或后端 /agent/run），或用 --live 现采。")
        return 1
    out_path = Path(args[0]) if args else DEFAULT_OUT
    return capture_from_log(latest, out_path)


if __name__ == "__main__":
    raise SystemExit(main())
