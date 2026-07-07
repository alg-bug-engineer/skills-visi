#!/usr/bin/env python3
"""需求 1 本地调试运行器：以剧本脚本形式完整执行智能体后端并沉淀日志。

模拟前端用户在输入框提问（默认：转山西路与经十路交叉口），逐步记录
每个技能的输入、输出及对应剧本幕次，写入 logs/run_1/。

用法（项目根目录）：
    .venv/bin/python modules/run_1.py
    .venv/bin/python modules/run_1.py --console
    .venv/bin/python modules/run_1.py --input "转山西路与经十路交叉口..."

要求：必须配置真实 Qwen API（LLM_MOCK=false）。
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api.response_builder import build_public_run_response
from app.config import Settings, get_settings
from app.llm.qwen import QwenClient
from app.logging_setup import setup_logging, set_trace_id
from app.runtime.pipeline_validation import DEFAULT_PIPELINE
from app.runtime.registry import get_registry
from app.runtime.skill_types import SkillContext, SkillResult
from app.services.case_library import CaseLibraryService

# ---------------------------------------------------------------------------
# 默认案例：转山西路与经十路交叉口（对应 PG 中「经十路与转山西路路口」）
# ---------------------------------------------------------------------------
DEFAULT_INPUT = (
    "转山西路与经十路交叉口，六点十分到六点半，"
    "东向西排队溢出到上游，优先避免下游继续外溢。"
)

LOG_DIR = PROJECT_ROOT / "logs" / "run_1"
SEP = "=" * 72
SUBSEP = "-" * 72

# 技能 → 剧本幕次 / 前端行为 / API 路径
SKILL_SCRIPT_MAP: dict[str, dict[str, Any]] = {
    "intent_understanding": {
        "acts": [
            "第一幕：接到问题，先整理成诊断工单",
            "第二幕：把一句话落到真实路网",
        ],
        "frontend": (
            "用户点击发送 → 输入框下沉为任务栏 → 底部显示「执行中：问题理解」；"
            "左侧浮现诊断工单；地图缩放到目标路口并高亮上下游"
        ),
        "api_phase": "phases.intent",
        "screen_highlights": [
            "对象 / 路口 / 时间 / 方向 / 转向 / 问题类型 / 约束 / 诊断范围 / 治理目标",
            "recognition_steps：路口匹配 → 进口方向 → 转向关系 → 上下游拓扑 → 干线路径",
        ],
        "api_fields": [
            "diagnosis_ticket.*",
            "phases.intent.spatial_scene.*",
            "phases.intent.user_experiences[]",
        ],
    },
    "data_analysis_diagnosis": {
        "acts": [
            "第三幕：先验证溢出是否成立",
            "第四幕：区分「本路口放不出去」还是「下游接不住」",
            "第五幕：把问题拉到干线，看上游来车是否需要干预",
        ],
        "frontend": (
            "渠化小窗 Slide-in；展示排队比/饱和度/绿灯利用率；"
            "地图切换下游诊断与干线溯源图层"
        ),
        "api_phase": "phases.diagnosis",
        "screen_highlights": [
            "排队比 ≥0.8 预警、≥1.0 溢出；overflow_verification.message 中央判定",
            "downstream_diagnosis.release_answer：本路口放不出去 / 下游接不住",
            "arterial_analysis：上游到达、剩余空间、need_upstream_metering",
            "flow_trace.entry_traces：来车溯源路径",
        ],
        "api_fields": [
            "phases.diagnosis.metrics.*",
            "phases.diagnosis.overflow_verification",
            "phases.diagnosis.downstream_diagnosis.*",
            "phases.diagnosis.arterial_analysis.*",
            "phases.diagnosis.flow_trace.*",
        ],
    },
    "cause_analysis": {
        "acts": ["第六幕：形成成因判断，并引入相似案例增强可信度"],
        "frontend": "推理证据栏展示主因/次因卡片与相似案例 A/B",
        "api_phase": "phases.cause",
        "screen_highlights": [
            "cause_analysis.primary_cause / secondary_causes",
            "cause_ranking 六维评分；case_cards 高度相似案例",
        ],
        "api_fields": [
            "phases.cause.cause_analysis.*",
            "phases.cause.cause_ranking",
            "phases.cause.case_cards.*",
        ],
    },
    "strategy_generation": {
        "acts": ["第七幕：生成治理策略，从「单点加绿」升级为「干线联控」"],
        "frontend": "策略摘要、控制范围地图、案例经验引用",
        "api_phase": "phases.strategy",
        "screen_highlights": [
            "strategy.principles / recommended / not_recommended",
            "strategy_package：downstream_protection / incremental_release / arterial_coordination",
            "control_scope_map：上游控流点、目标路口、下游保护节点",
        ],
        "api_fields": [
            "phases.strategy.strategy.*",
            "phases.strategy.strategy_package",
            "phases.strategy.control_scope_map",
        ],
    },
    "plan_generation": {
        "acts": ["第八幕：把策略转成可执行方案"],
        "frontend": "三候选方案卡片、推荐结论、护栏与回滚条件",
        "api_phase": "phases.plan / plan",
        "screen_highlights": [
            "candidates[]：下游保护 / 小步释放 / 干线联控",
            "recommendation.rationale；rollback_conditions",
        ],
        "api_fields": [
            "plan.candidates[]",
            "plan.recommended",
            "plan.recommendation.*",
            "plan.rollback_conditions",
        ],
    },
}

STEP_OUTPUT_KEYS: dict[str, dict[str, list[str]]] = {
    "intent_understanding": {
        "parse_intent": [
            "diagnosis_ticket.intersection_name",
            "diagnosis_ticket.time_range",
            "diagnosis_ticket.direction",
            "diagnosis_ticket.problem_type",
            "diagnosis_ticket.constraints",
        ],
        "extract_user_experiences": ["user_experiences"],
        "build_spatial_objects": ["spatial_objects"],
    },
    "data_analysis_diagnosis": {
        "verify_overflow": [
            "metrics.queue_ratio",
            "metrics.saturation",
            "overflow_verification",
            "downstream_diagnosis",
            "arterial_analysis",
            "flow_trace",
        ],
    },
    "cause_analysis": {
        "build_evidence": ["evidence_summary", "cause_scores"],
        "rank_causes": ["cause_analysis", "cause_ranking", "case_cards"],
    },
    "strategy_generation": {
        "select_package": ["strategy_package", "package_scores"],
        "summarize_strategy": ["strategy", "strategy_instruction", "control_scope_map"],
    },
    "plan_generation": {
        "build_candidates": ["candidates", "signal_source"],
        "recommend_plan": ["recommended", "recommendation", "rollback_conditions"],
    },
}


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


def _build_log_paths(trace_id: str) -> tuple[Path, Path, Path]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{stamp}_{trace_id}"
    return (
        LOG_DIR / f"{base}.log",
        LOG_DIR / f"{base}.json",
        LOG_DIR / f"{base}_steps.json",
    )


def _ensure_real_llm(settings: Settings) -> None:
    if settings.llm_mock:
        raise SystemExit(
            "本脚本禁止 mock 模式。请设置 LLM_MOCK=false 并配置 QWEN_API_KEY 后重试。"
        )
    if not settings.qwen_api_key:
        raise SystemExit("缺少 QWEN_API_KEY，无法调用真实大模型。")


def _nested_get(data: dict[str, Any], dotted: str) -> Any:
    current: Any = data
    for part in dotted.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _pick_output_fields(output: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    picked: dict[str, Any] = {}
    for key in keys:
        if "." in key:
            value = _nested_get(output, key)
            if value is not None:
                picked[key] = value
        elif key in output:
            picked[key] = output[key]
    return picked


def _skill_input_snapshot(skill_id: str, context: SkillContext) -> dict[str, Any]:
    """按技能整理执行前输入，便于对照剧本与 API 契约。"""
    base: dict[str, Any] = {"user_input": context.user_input}
    task = context.task
    artifacts = context.artifacts

    if skill_id == "intent_understanding":
        base["task_preset"] = {
            k: task.get(k)
            for k in ("diagnosis_ticket", "topology", "metrics")
            if task.get(k)
        }
    elif skill_id == "data_analysis_diagnosis":
        base["diagnosis_ticket"] = task.get("diagnosis_ticket")
        base["spatial_objects"] = task.get("spatial_objects")
        base["upstream_intent"] = artifacts.get("intent_understanding", {})
    elif skill_id == "cause_analysis":
        base["diagnosis_ticket"] = task.get("diagnosis_ticket")
        base["upstream_diagnosis"] = {
            k: artifacts.get("data_analysis_diagnosis", {}).get(k)
            for k in (
                "metrics",
                "overflow_verification",
                "downstream_diagnosis",
                "arterial_analysis",
                "bottleneck_analysis",
            )
            if artifacts.get("data_analysis_diagnosis", {}).get(k) is not None
        }
    elif skill_id == "strategy_generation":
        base["upstream_cause"] = artifacts.get("cause_analysis", {})
        base["upstream_diagnosis_summary"] = {
            "release_answer": artifacts.get("data_analysis_diagnosis", {})
            .get("downstream_diagnosis", {})
            .get("release_answer"),
            "arterial_summary": artifacts.get("data_analysis_diagnosis", {})
            .get("arterial_analysis", {})
            .get("summary"),
        }
        base["constraints"] = task.get("diagnosis_ticket", {}).get("constraints")
    elif skill_id == "plan_generation":
        base["upstream_strategy"] = {
            k: artifacts.get("strategy_generation", {}).get(k)
            for k in ("strategy_package", "strategy", "strategy_instruction")
            if artifacts.get("strategy_generation", {}).get(k) is not None
        }
        base["diagnosis_ticket"] = task.get("diagnosis_ticket")
    return base


class TracingQwenClient(QwenClient):
    """包装 Qwen 调用，记录 LLM 请求与响应。"""

    def __init__(self, settings: Settings, output: RunOutput) -> None:
        super().__init__(settings)
        self._output = output
        self.call_index = 0

    async def chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_json: bool = True,
        trace_id: str | None = None,
    ) -> dict[str, Any] | str:
        self.call_index += 1
        self._output.subtitle(
            f"LLM 调用 #{self.call_index} trace_id={trace_id or '-'} model={self.settings.qwen_model}"
        )
        self._output.json_block(
            "LLM 请求",
            {
                "model": self.settings.qwen_model,
                "response_json": response_json,
                "system_prompt_preview": system_prompt[:400] + ("…" if len(system_prompt) > 400 else ""),
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
    script_info = SKILL_SCRIPT_MAP.get(meta.skill_id, {})
    return {
        "skill_id": meta.skill_id,
        "display_name": meta.display_name,
        "phase": meta.phase,
        "version": meta.version,
        "description": meta.description,
        "skill_dir": skill.skill_dir.name,
        "script_acts": script_info.get("acts", []),
        "frontend_behavior": script_info.get("frontend", ""),
        "api_phase": script_info.get("api_phase", ""),
        "script_files": meta.script_files,
        "reference_files": meta.reference_files,
        "resource_files": meta.resource_files,
        "execution_steps": meta.execution_steps,
    }


def _log_execution_steps(
    output: RunOutput,
    skill_id: str,
    skill,
    context: SkillContext,
    result: SkillResult,
    step_records: list[dict[str, Any]],
) -> None:
    script_info = SKILL_SCRIPT_MAP.get(skill_id, {})
    output.subtitle("剧本幕次对照")
    for act in script_info.get("acts", []):
        output.write(f"  · {act}")
    if script_info.get("frontend"):
        output.write(f"\n前端行为: {script_info['frontend']}")
    if script_info.get("screen_highlights"):
        output.write("\n屏幕重点:")
        for item in script_info["screen_highlights"]:
            output.write(f"  - {item}")
    if script_info.get("api_fields"):
        output.write("\nAPI 字段:")
        for field in script_info["api_fields"]:
            output.write(f"  - {field}")

    step_output_map = STEP_OUTPUT_KEYS.get(skill_id, {})
    for step_index, step in enumerate(skill.meta.execution_steps, start=1):
        step_id = step.get("step_id", f"step_{step_index}")
        output.subtitle(
            f"子步骤 {step_index}/{len(skill.meta.execution_steps)}: "
            f"{step.get('title', step_id)}"
        )
        output.write(f"step_id: {step_id}")
        if step.get("instruction"):
            output.write(f"说明: {step['instruction']}")
        if step.get("script"):
            output.write(f"脚本: {step['script']}" + (f" → {step['function']}()" if step.get("function") else ""))

        step_input = _skill_input_snapshot(skill_id, context)
        output.json_block("本子步骤输入（技能级上下文）", step_input)

        picked = _pick_output_fields(result.output, step_output_map.get(step_id, list(result.output.keys())[:8]))
        output.json_block("本子步骤输出（关键字段）", picked or result.output)

        step_records.append(
            {
                "skill_id": skill_id,
                "step_id": step_id,
                "title": step.get("title"),
                "instruction": step.get("instruction"),
                "script": step.get("script"),
                "function": step.get("function"),
                "script_acts": script_info.get("acts", []),
                "input": step_input,
                "output": picked or result.output,
                "success": result.success,
            }
        )


def _log_frontend_simulation(output: RunOutput, user_input: str, trace_id: str) -> None:
    output.title("【场景 0】模拟前端用户提问")
    output.write("用户在济南地图首页的自然语言输入框键入问题并点击「发送」。")
    output.json_block(
        "等价 HTTP 请求 POST /api/v1/agent/run",
        {
            "user_input": user_input,
            "trace_id": trace_id,
            "task": {},
        },
    )
    output.write(
        "\n后端建立 SSE 连接后，理解过程栏逐步打字渲染旁白，"
        "证据卡进入缓冲区，步骤完成后揭示到左侧推理证据栏，地图同步运镜。"
    )


def _log_pipeline_overview(output: RunOutput) -> None:
    output.title("【执行总览】五技能流水线 ↔ 剧本八幕")
    rows = [
        ("1", "intent_understanding", "意图理解", "第一幕 + 第二幕"),
        ("2", "data_analysis_diagnosis", "数据分析与诊断", "第三幕 + 第四幕 + 第五幕"),
        ("3", "cause_analysis", "成因分析", "第六幕"),
        ("4", "strategy_generation", "策略生成", "第七幕"),
        ("5", "plan_generation", "方案生成", "第八幕"),
    ]
    for index, skill_id, name, acts in rows:
        output.write(f"  [{index}] {skill_id}（{name}）→ {acts}")
    output.write(f"\n默认流水线: {DEFAULT_PIPELINE}")


async def run_verbose(
    user_input: str,
    *,
    trace_id: str | None = None,
    task: dict[str, Any] | None = None,
    settings: Settings | None = None,
    output: RunOutput,
) -> dict[str, Any]:
    settings = settings or get_settings()
    _ensure_real_llm(settings)
    tid = set_trace_id(trace_id)

    registry = get_registry()
    llm = TracingQwenClient(settings, output)
    case_service = CaseLibraryService(settings.case_library_abs_path)
    step_records: list[dict[str, Any]] = []

    output.title(f"交通智能体 · 需求1 剧本脚本执行 trace_id={tid}")
    output.json_block(
        "运行配置",
        {
            "trace_id": tid,
            "llm_mode": "real",
            "qwen_model": settings.qwen_model,
            "qwen_base_url": settings.qwen_base_url,
            "pg_dsn_configured": bool(settings.pg_dsn),
            "allow_demo_fallback": settings.allow_demo_fallback,
            "case_library": str(settings.case_library_abs_path),
            "pipeline": DEFAULT_PIPELINE,
            "log_file": str(output.log_path),
        },
    )

    _log_frontend_simulation(output, user_input, tid)
    _log_pipeline_overview(output)

    output.subtitle("已注册技能")
    for item in registry.list_skills():
        output.write(f"  - {item['skill_id']}: {item['display_name']} ({item['skill_dir']})")

    context = SkillContext(trace_id=tid, user_input=user_input, task=task or {})
    results: list[SkillResult] = []

    for index, skill_id in enumerate(DEFAULT_PIPELINE, start=1):
        skill = registry.get(skill_id)
        script_info = SKILL_SCRIPT_MAP.get(skill_id, {})
        acts_label = " / ".join(script_info.get("acts", [])) or "—"

        output.title(
            f"[{index}/{len(DEFAULT_PIPELINE)}] 技能: {skill_id}（{skill.meta.display_name}）"
        )
        output.write(f"剧本幕次: {acts_label}")

        output.json_block("技能元数据", _skill_meta_dict(skill))
        input_snapshot = _skill_input_snapshot(skill_id, context)
        output.json_block("执行前 · 技能输入", input_snapshot)

        llm_calls_before = llm.call_index
        start = time.perf_counter()
        try:
            result = await skill.run(
                context,
                llm=llm,
                case_service=case_service,
                settings=settings,
            )
        except Exception as exc:
            result = SkillResult(
                skill_id=skill_id,
                phase=skill.meta.phase,
                success=False,
                errors=[str(exc)],
            )
            output.write(f"\n!!! 技能异常: {exc}")
        result.duration_ms = round((time.perf_counter() - start) * 1000, 2)
        llm_calls_in_skill = llm.call_index - llm_calls_before

        output.json_block(
            "执行后 · 技能输出",
            {
                "skill_id": result.skill_id,
                "phase": result.phase,
                "success": result.success,
                "duration_ms": result.duration_ms,
                "llm_calls_in_skill": llm_calls_in_skill,
                "errors": result.errors,
                "output": result.output,
            },
        )

        _log_execution_steps(output, skill_id, skill, context, result, step_records)

        results.append(result)
        context.artifacts[skill_id] = result.output
        context.task.update(result.output)

        if not result.success:
            output.write(f"\n!!! 流水线在技能 {skill_id} 处中止")
            break

    raw_final = {
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
    public_response = build_public_run_response(raw_final)

    output.title("【前端契约】build_public_run_response 整形结果")
    output.json_block("公开 API 响应（供前端三栏渲染）", public_response)

    output.title("执行汇总")
    output.json_block("内部流水线结果", raw_final)
    output.write(
        f"\n完成状态: {'成功' if raw_final['completed'] else '失败'} | "
        f"trace_id={tid} | LLM 总调用次数={llm.call_index}"
    )

    raw_final["public_response"] = public_response
    raw_final["step_records"] = step_records
    raw_final["llm_call_count"] = llm.call_index
    raw_final["user_input"] = user_input
    return raw_final


def main() -> None:
    parser = argparse.ArgumentParser(
        description="需求1 智能体剧本脚本执行器（真实大模型，禁止 mock）"
    )
    parser.add_argument("--input", "-i", default=DEFAULT_INPUT, help="模拟前端用户自然语言输入")
    parser.add_argument("--trace-id", default=None, help="指定 trace_id")
    parser.add_argument(
        "--task-json",
        default=None,
        help='预置 task JSON，例如 \'{"metrics": {...}, "topology": {...}}\'',
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
    _ensure_real_llm(settings)
    setup_logging(args.log_level)

    tid = set_trace_id(args.trace_id)
    log_path, json_path, steps_path = _build_log_paths(tid)
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
        steps_payload = {
            "trace_id": tid,
            "user_input": args.input,
            "completed": final.get("completed"),
            "llm_call_count": final.get("llm_call_count"),
            "steps": final.get("step_records", []),
            "public_response": final.get("public_response"),
        }
        steps_path.write_text(
            json.dumps(steps_payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    finally:
        output.close()

    if final is not None:
        print(
            f"执行{'成功' if final.get('completed') else '失败'} | trace_id={tid}\n"
            f"  剧本日志: {log_path}\n"
            f"  完整 JSON: {json_path}\n"
            f"  分步 JSON: {steps_path}\n"
            f"  运行日志: {PROJECT_ROOT / 'logs' / 'agent.log'}"
        )


if __name__ == "__main__":
    main()
