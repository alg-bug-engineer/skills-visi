#!/usr/bin/env python3
"""需求 1 本地调试运行器：完整执行智能体后端并记录调用详情。

用法（项目根目录）：
    python modules/run_1.py
    python modules/run_1.py --input "文化西路与舜华路交叉口..."
    python modules/run_1.py --console          # 同时输出到终端
    LLM_MOCK=true python modules/run_1.py

默认将完整执行过程写入 logs/run_1/ 目录，便于后续日志分析。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

# 保证从项目根目录可直接运行
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Settings, get_settings
from app.llm.qwen import QwenClient
from app.logging_setup import setup_logging, set_trace_id
from app.runtime.executor import DEFAULT_PIPELINE
from app.runtime.registry import get_registry
from app.runtime.skill_types import SkillContext, SkillResult
from app.services.case_library import CaseLibraryService

DEFAULT_INPUT = (
    "文化西路与舜华路交叉口，六点十分到六点半，"
    "东向西排队溢出到上游，优先避免下游继续外溢。"
)

LOG_DIR = PROJECT_ROOT / "logs" / "run_1"
SEP = "=" * 72
SUBSEP = "-" * 72


class RunOutput:
    """将运行详情写入日志文件，可选同步输出到控制台。"""

    def __init__(self, log_path: Path, *, console: bool = False) -> None:
        self.log_path = log_path
        self.console = console
        self._file: TextIO = log_path.open("w", encoding="utf-8")

    def close(self) -> None:
        self._file.close()

    def write(self, text: str = "") -> None:
        self._file.write(text + "\n")
        if self.console:
            print(text)

    def title(self, text: str) -> None:
        self.write("")
        self.write(SEP)
        self.write(text)
        self.write(SEP)

    def subtitle(self, text: str) -> None:
        self.write("")
        self.write(SUBSEP)
        self.write(text)
        self.write(SUBSEP)

    def json_block(self, label: str, data: Any) -> None:
        self.write(f"\n>>> {label}")
        if data is None:
            self.write("(null)")
            return
        try:
            text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        except TypeError:
            text = str(data)
        self.write(text)


def _build_log_paths(trace_id: str) -> tuple[Path, Path]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{stamp}_{trace_id}"
    return LOG_DIR / f"{base}.log", LOG_DIR / f"{base}.json"


class TracingQwenClient(QwenClient):
    """包装 Qwen 调用，记录 LLM 请求与响应。"""

    def __init__(self, settings: Settings, output: RunOutput) -> None:
        super().__init__(settings)
        self._output = output

    async def chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_json: bool = True,
        trace_id: str | None = None,
    ) -> dict[str, Any] | str:
        self._output.subtitle(f"LLM 调用 trace_id={trace_id or '-'}")
        self._output.json_block(
            "LLM 请求",
            {
                "model": self.settings.qwen_model,
                "llm_mock": self.settings.llm_mock,
                "response_json": response_json,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            },
        )

        start = time.perf_counter()
        result = await super().chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_json=response_json,
            trace_id=trace_id,
        )
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        self._output.json_block("LLM 响应", result)
        self._output.write(f"\n>>> LLM 耗时: {elapsed_ms} ms")
        return result


def _skill_meta_dict(skill) -> dict[str, Any]:
    meta = skill.meta
    return {
        "skill_id": meta.skill_id,
        "display_name": meta.display_name,
        "phase": meta.phase,
        "version": meta.version,
        "description": meta.description,
        "skill_dir": skill.skill_dir.name,
        "script_files": meta.script_files,
        "reference_files": meta.reference_files,
        "resource_files": meta.resource_files,
        "execution_steps": meta.execution_steps,
    }


async def run_verbose(
    user_input: str,
    *,
    trace_id: str | None = None,
    task: dict[str, Any] | None = None,
    settings: Settings | None = None,
    output: RunOutput,
) -> dict[str, Any]:
    settings = settings or get_settings()
    tid = set_trace_id(trace_id)

    registry = get_registry()
    llm = TracingQwenClient(settings, output)
    case_service = CaseLibraryService(settings.case_library_abs_path)

    output.title(f"交通智能体 · 需求1 完整执行 trace_id={tid}")
    output.json_block(
        "运行配置",
        {
            "trace_id": tid,
            "llm_mock": settings.llm_mock,
            "qwen_model": settings.qwen_model,
            "qwen_base_url": settings.qwen_base_url,
            "case_library": str(settings.case_library_abs_path),
            "pipeline": DEFAULT_PIPELINE,
            "log_file": str(output.log_path),
        },
    )

    output.subtitle("已注册技能")
    for item in registry.list_skills():
        output.write(f"  - {item['skill_id']}: {item['display_name']} ({item['skill_dir']})")

    output.json_block("用户输入", {"user_input": user_input})
    if task:
        output.json_block("预置任务上下文 task", task)

    context = SkillContext(trace_id=tid, user_input=user_input, task=task or {})
    results: list[SkillResult] = []

    for index, skill_id in enumerate(DEFAULT_PIPELINE, start=1):
        skill = registry.get(skill_id)
        output.title(f"[{index}/{len(DEFAULT_PIPELINE)}] 技能执行: {skill_id}")

        output.json_block("技能元数据", _skill_meta_dict(skill))
        output.json_block(
            "执行前 · 输入上下文",
            {
                "user_input": context.user_input,
                "task": context.task,
                "upstream_artifacts": context.artifacts,
            },
        )

        start = time.perf_counter()
        try:
            result = await skill.run(context, llm=llm, case_service=case_service)
        except Exception as exc:
            result = SkillResult(
                skill_id=skill_id,
                phase=skill.meta.phase,
                success=False,
                errors=[str(exc)],
            )
            output.write(f"\n!!! 技能异常: {exc}")
        result.duration_ms = round((time.perf_counter() - start) * 1000, 2)

        output.json_block(
            "执行后 · 技能结果",
            {
                "skill_id": result.skill_id,
                "phase": result.phase,
                "success": result.success,
                "duration_ms": result.duration_ms,
                "errors": result.errors,
                "output": result.output,
            },
        )

        results.append(result)
        context.artifacts[skill_id] = result.output
        context.task.update(result.output)

        if not result.success:
            output.write(f"\n!!! 流水线在技能 {skill_id} 处中止")
            break

    final = {
        "trace_id": tid,
        "pipeline": DEFAULT_PIPELINE,
        "completed": all(r.success for r in results),
        "diagnosis_ticket": context.artifacts.get("intent_understanding", {}).get(
            "diagnosis_ticket"
        ),
        "artifacts": context.artifacts,
        "results": [
            {
                "skill_id": r.skill_id,
                "phase": r.phase,
                "success": r.success,
                "duration_ms": r.duration_ms,
                "errors": r.errors,
                "output": r.output,
            }
            for r in results
        ],
    }

    output.title("执行汇总")
    output.json_block("最终结果", final)
    output.write(
        f"\n完成状态: {'成功' if final['completed'] else '失败'} | trace_id={tid}"
    )
    return final


def main() -> None:
    parser = argparse.ArgumentParser(description="需求1 智能体完整执行调试器")
    parser.add_argument("--input", "-i", default=DEFAULT_INPUT, help="用户自然语言输入")
    parser.add_argument("--trace-id", default=None, help="指定 trace_id")
    parser.add_argument(
        "--task-json",
        default=None,
        help='预置 task JSON 字符串，例如 \'{"metrics": {...}}\'',
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="同时将详情输出到终端（默认仅写入 logs/run_1/）",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        help="agent.log 日志级别，默认 WARNING",
    )
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(args.log_level)

    tid = set_trace_id(args.trace_id)
    log_path, json_path = _build_log_paths(tid)
    output = RunOutput(log_path, console=args.console)

    final: dict[str, Any] | None = None
    try:
        task = json.loads(args.task_json) if args.task_json else None
        final = asyncio.run(
            run_verbose(
                args.input,
                trace_id=tid,
                task=task,
                settings=settings,
                output=output,
            )
        )
        json_path.write_text(
            json.dumps(final, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    finally:
        output.close()

    if final is not None:
        print(
            f"执行{'成功' if final.get('completed') else '失败'} | trace_id={tid}\n"
            f"  详情日志: {log_path}\n"
            f"  结果 JSON: {json_path}\n"
            f"  运行日志: {PROJECT_ROOT / 'logs' / 'agent.log'}"
        )


if __name__ == "__main__":
    main()
