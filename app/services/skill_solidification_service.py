"""Solidify an accepted plan into a real, on-disk Agent-Skill package.

固化 = 真实落盘。给定本轮真实的 diagnosis_ticket / strategy / plan，派生并写出一个
标准 Agent-Skill 包（SKILL.md + reference.md + scripts/fetch_traffic_data.sql +
skill.meta.json），并返回可供前端「经验吸收 + 技能固化」可视化的结构化结果。

真实性约束（遵 docs/rule.md）：所有内容均来源于真实入参，缺失字段显式降级为
None / "—"，绝不虚构指标或结果行。派生逻辑（标签/签名/文件内容）与磁盘 IO 分离，
以便单元测试。
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT

DISPLAY_DASH = "—"
SKILL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-]+$")

# 经验吸收 6 阶段（呈现层动画节奏，数据来自真实派生字段）。
ABSORPTION_STAGE_DEFS: tuple[tuple[str, str], ...] = (
    ("recap", "回顾本轮约束"),
    ("decompose", "解构为可索引字段"),
    ("retrieve", "检索既有技能库"),
    ("compare", "比对 创建/更新"),
    ("value", "价值前后对照"),
    ("blueprint", "转化写入蓝图"),
)

# 技能固化 7 阶段 + 进度（progress 递增，末阶段 100）。
BUILD_STAGE_DEFS: tuple[tuple[str, str], ...] = (
    ("understanding", "理解本轮成果"),
    ("planning", "规划技能包结构"),
    ("writing_skill_md", "写入 SKILL.md"),
    ("writing_reference", "写入 reference.md"),
    ("writing_scripts", "写入取数脚本"),
    ("writing_meta", "写入技能元信息"),
    ("packaging", "打包与登记"),
)

STAGE_PROGRESS: dict[str, int] = {
    "understanding": 8,
    "planning": 20,
    "writing_skill_md": 45,
    "writing_reference": 62,
    "writing_scripts": 80,
    "writing_meta": 92,
    "packaging": 100,
}

_ACTION_ABSORPTION = {
    "created": "CREATE",
    "updated": "UPDATE",
    "unchanged": "UNCHANGED",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any) -> Any:
    """空串/空白归一为 None，其余原样返回（用于显式降级）。"""
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def _as_str_list(value: Any) -> list[str]:
    """把 list / dict / str 统一成非空字符串列表。"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, dict):
        rows: list[str] = []
        for key, val in value.items():
            if val in (None, "", []):
                continue
            rows.append(f"{key}: {val}")
        return rows
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    return [str(value)]


def _yaml_scalar(value: Any) -> str:
    """以 JSON 双引号形式输出，既是合法 YAML 标量，也安全转义中文/冒号。"""
    if value is None:
        return "null"
    return json.dumps(value, ensure_ascii=False)


def _yaml_list(values: list[str]) -> str:
    return "[" + ", ".join(_yaml_scalar(v) for v in values) + "]"


def slugify(name: str | None) -> str:
    """ASCII slug；中文名会被清空（调用方据此降级到 inter_id / unknown）。"""
    if not name:
        return ""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()
    return slug


def _extract_strategy(strategy: Any) -> dict[str, Any]:
    """策略可能位于 strategy 或 strategy.strategy 之下。"""
    if not isinstance(strategy, dict):
        return {}
    inner = strategy.get("strategy")
    if isinstance(inner, dict):
        return inner
    return strategy


def _extract_recommended_plan(plan_snapshot: Any) -> dict[str, Any]:
    """从多种可能的 plan 快照形态里取出推荐方案对象。"""
    if not isinstance(plan_snapshot, dict):
        return {}
    recommended = plan_snapshot.get("recommended")
    if isinstance(recommended, dict):
        return recommended
    # plan_snapshot 本身即推荐方案
    if plan_snapshot.get("timing") or plan_snapshot.get("plan_id") or plan_snapshot.get("name"):
        return plan_snapshot
    rec_id = plan_snapshot.get("recommended_plan_id")
    for candidate in plan_snapshot.get("candidates") or []:
        if isinstance(candidate, dict) and candidate.get("plan_id") == rec_id:
            return candidate
    return {}


def derive_context(
    *,
    diagnosis_ticket: Any = None,
    strategy: Any = None,
    plan_snapshot: Any = None,
    artifacts_summary: Any = None,
) -> dict[str, Any]:
    """把真实入参派生为可索引/可渲染字段字典；缺失显式降级为 None/[]。"""
    ticket = diagnosis_ticket if isinstance(diagnosis_ticket, dict) else {}
    inter_id = _clean(ticket.get("inter_id"))
    intersection_name = _clean(ticket.get("intersection_name"))
    period = _clean(ticket.get("period"))
    time_range = _clean(ticket.get("time_range"))
    direction = _clean(ticket.get("direction"))
    movement = _clean(ticket.get("movement"))
    problem_type = _clean(ticket.get("problem_type"))
    diagnosis_scope = _clean(ticket.get("diagnosis_scope"))
    governance_goal = _clean(ticket.get("governance_goal"))
    constraints = _as_str_list(ticket.get("constraints"))
    directions = [d for d in [direction] if d]

    user_experiences = ticket.get("user_experiences") or []
    spans: list[str] = []
    for exp in user_experiences:
        if isinstance(exp, dict):
            span = _clean(exp.get("source_span")) or _clean(exp.get("content"))
            if span:
                spans.append(str(span))
    source_utterance_summary = _clean("；".join(spans)) or governance_goal

    strat = _extract_strategy(strategy)
    principles = _as_str_list(strat.get("principles"))
    recommended = _as_str_list(strat.get("recommended"))
    hard_constraints = _as_str_list(strat.get("hard_constraints"))
    not_recommended = _as_str_list(strat.get("not_recommended"))
    strategy_explanation = _clean(strat.get("explanation"))
    strategy_name = _clean(strat.get("name")) or (
        _clean(strategy.get("strategy_package")) if isinstance(strategy, dict) else None
    )

    plan = _extract_recommended_plan(plan_snapshot)
    plan_name = _clean(plan.get("name"))
    timing = plan.get("timing") if isinstance(plan.get("timing"), dict) else {}
    cycle_s = timing.get("cycle_s")
    phase_stages = (
        timing.get("phase_stage_timing_list")
        if isinstance(timing.get("phase_stage_timing_list"), list)
        else []
    )
    expected_effect = _clean(plan.get("expected_effect"))
    risk = _clean(plan.get("risk"))
    rollback_condition = _clean(plan.get("rollback_condition"))

    # 可选：从 artifacts_summary / strategy 里尽力提取规则/问题编码（缺失即空）。
    rule_ids: list[str] = []
    issue_codes: list[str] = []
    if isinstance(artifacts_summary, dict):
        rule_ids = _as_str_list(artifacts_summary.get("rule_ids"))
        issue_codes = _as_str_list(artifacts_summary.get("issue_codes"))

    time_period_label = time_range or period

    match_keywords = [
        kw
        for kw in [intersection_name, problem_type, period, direction, movement]
        if kw
    ]

    constraint_intent = governance_goal
    if constraint_intent is None and isinstance(ticket.get("constraints"), dict):
        constraint_intent = _clean(ticket["constraints"].get("priority"))

    return {
        "inter_id": inter_id,
        "intersection_name": intersection_name,
        "period": period,
        "time_range": time_range,
        "time_period_label": time_period_label,
        "direction": direction,
        "movement": movement,
        "directions": directions,
        "problem_type": problem_type,
        "diagnosis_scope": diagnosis_scope,
        "governance_goal": governance_goal,
        "constraints": constraints,
        "source_utterance_summary": source_utterance_summary,
        "principles": principles,
        "recommended": recommended,
        "hard_constraints": hard_constraints,
        "not_recommended": not_recommended,
        "strategy_explanation": strategy_explanation,
        "strategy_name": strategy_name,
        "plan_name": plan_name,
        "cycle_s": cycle_s,
        "phase_stages": phase_stages,
        "expected_effect": expected_effect,
        "risk": risk,
        "rollback_condition": rollback_condition,
        "rule_ids": rule_ids,
        "issue_codes": issue_codes,
        "match_keywords": match_keywords,
        "constraint_intent": constraint_intent,
    }


def compute_skill_id(ctx: dict[str, Any]) -> str:
    inter_key = ctx.get("inter_id") or slugify(ctx.get("intersection_name")) or "unknown"
    period_key = ctx.get("period") or "all"
    return f"skill-{inter_key}-{period_key}"


def build_tags(ctx: dict[str, Any]) -> dict[str, Any]:
    content: dict[str, Any] = {
        "has_user_constraints": bool(ctx["constraints"]),
        "constraint_intent": ctx["constraint_intent"],
    }
    if ctx["rule_ids"]:
        content["rule_ids"] = ctx["rule_ids"]
    if ctx["issue_codes"]:
        content["issue_codes"] = ctx["issue_codes"]
    return {
        "match": {
            "intersection": ctx["intersection_name"],
            "inter_id": ctx["inter_id"],
            "time_period": ctx["period"],
            "problem_type": ctx["problem_type"],
            "directions": ctx["directions"],
            "match_keywords": ctx["match_keywords"],
        },
        "content": content,
        "meta": {
            "experience_source": "plan_accept",
            "version": "0.1.0",
            "source_utterance_summary": ctx["source_utterance_summary"],
        },
    }


def _phase_stage_line(stage: Any) -> str | None:
    if not isinstance(stage, dict):
        return None
    name = _clean(stage.get("phase_stage_name")) or _clean(stage.get("phase_stage_id"))
    green = stage.get("green_time_s")
    if green is None:
        green = stage.get("greenTime")
    if name is None and green is None:
        return None
    label = name or "相位阶段"
    if green is not None:
        return f"- {label}：绿灯 {green}s"
    return f"- {label}"


def build_skill_md(ctx: dict[str, Any], skill_id: str) -> str:
    intersection = ctx["intersection_name"] or ctx["inter_id"] or "未知路口"
    desc_parts = [p for p in [intersection, ctx["problem_type"], ctx["time_period_label"]] if p]
    description = ("、".join(desc_parts) + " 的治理经验固化技能") if desc_parts else "治理经验固化技能"

    lines: list[str] = ["---"]
    lines.append(f"name: {_yaml_scalar(skill_id)}")
    lines.append(f"description: {_yaml_scalar(description)}")
    lines.append("metadata:")
    lines.append(f"  intersection: {_yaml_scalar(ctx['intersection_name'])}")
    lines.append(f"  inter_id: {_yaml_scalar(ctx['inter_id'])}")
    lines.append(f"  problem_type: {_yaml_scalar(ctx['problem_type'])}")
    lines.append(f"  time_period: {_yaml_scalar(ctx['period'])}")
    lines.append(f"  time_range: {_yaml_scalar(ctx['time_range'])}")
    lines.append(f"  directions: {_yaml_list(ctx['directions'])}")
    lines.append(f"  tags: {_yaml_list(ctx['match_keywords'])}")
    lines.append(f"  experience_source: {_yaml_scalar('plan_accept')}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {intersection} 治理技能")
    lines.append("")

    # 诊断结论
    diag_rows: list[str] = []
    if ctx["intersection_name"]:
        diag_rows.append(f"- 路口：{ctx['intersection_name']}")
    if ctx["inter_id"]:
        diag_rows.append(f"- 路口 ID：{ctx['inter_id']}")
    if ctx["time_period_label"]:
        diag_rows.append(f"- 时段：{ctx['time_period_label']}")
    if ctx["direction"] or ctx["movement"]:
        dm = " / ".join([v for v in [ctx["direction"], ctx["movement"]] if v])
        diag_rows.append(f"- 方向/转向：{dm}")
    if ctx["problem_type"]:
        diag_rows.append(f"- 问题类型：{ctx['problem_type']}")
    if ctx["diagnosis_scope"]:
        diag_rows.append(f"- 诊断范围：{ctx['diagnosis_scope']}")
    if ctx["governance_goal"]:
        diag_rows.append(f"- 治理目标：{ctx['governance_goal']}")
    if diag_rows:
        lines.append("## 诊断结论")
        lines.append("")
        lines.extend(diag_rows)
        lines.append("")

    # 治理策略要点
    if ctx["principles"] or ctx["recommended"]:
        lines.append("## 治理策略要点")
        lines.append("")
        if ctx["principles"]:
            lines.append("### 原则")
            lines.append("")
            lines.extend(f"- {item}" for item in ctx["principles"])
            lines.append("")
        if ctx["recommended"]:
            lines.append("### 推荐做法")
            lines.append("")
            lines.extend(f"- {item}" for item in ctx["recommended"])
            lines.append("")

    # 配时建议摘要
    stage_lines = [line for line in (_phase_stage_line(s) for s in ctx["phase_stages"]) if line]
    if ctx["plan_name"] or ctx["cycle_s"] is not None or stage_lines:
        lines.append("## 配时建议摘要")
        lines.append("")
        if ctx["plan_name"]:
            lines.append(f"- 推荐方案：{ctx['plan_name']}")
        if ctx["cycle_s"] is not None:
            lines.append(f"- 周期：{ctx['cycle_s']}s")
        lines.extend(stage_lines)
        lines.append("")

    # 约束/红线
    if ctx["constraints"] or ctx["hard_constraints"]:
        lines.append("## 约束与红线")
        lines.append("")
        if ctx["constraints"]:
            lines.append("### 用户约束")
            lines.append("")
            lines.extend(f"- {item}" for item in ctx["constraints"])
            lines.append("")
        if ctx["hard_constraints"]:
            lines.append("### 策略红线")
            lines.append("")
            lines.extend(f"- {item}" for item in ctx["hard_constraints"])
            lines.append("")

    # 预期效果/回滚
    if ctx["expected_effect"] or ctx["risk"] or ctx["rollback_condition"]:
        lines.append("## 预期效果与回滚")
        lines.append("")
        if ctx["expected_effect"]:
            lines.append(f"- 预期效果：{ctx['expected_effect']}")
        if ctx["risk"]:
            lines.append(f"- 风险提示：{ctx['risk']}")
        if ctx["rollback_condition"]:
            lines.append(f"- 回滚条件：{ctx['rollback_condition']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_reference_md(ctx: dict[str, Any]) -> str:
    lines: list[str] = ["# 诊断依据与策略要点明细", ""]

    if ctx["source_utterance_summary"]:
        lines.append("## 用户原始诉求")
        lines.append("")
        lines.append(f"> {ctx['source_utterance_summary']}")
        lines.append("")

    if ctx["principles"]:
        lines.append("## 策略原则")
        lines.append("")
        lines.extend(f"{i}. {item}" for i, item in enumerate(ctx["principles"], 1))
        lines.append("")

    if ctx["recommended"]:
        lines.append("## 推荐做法")
        lines.append("")
        lines.extend(f"{i}. {item}" for i, item in enumerate(ctx["recommended"], 1))
        lines.append("")

    if ctx["not_recommended"]:
        lines.append("## 不建议做法")
        lines.append("")
        lines.extend(f"- {item}" for item in ctx["not_recommended"])
        lines.append("")

    if ctx["hard_constraints"]:
        lines.append("## 硬约束（红线）")
        lines.append("")
        lines.extend(f"- {item}" for item in ctx["hard_constraints"])
        lines.append("")

    if ctx["strategy_explanation"]:
        lines.append("## 策略解释")
        lines.append("")
        lines.append(ctx["strategy_explanation"])
        lines.append("")

    if ctx["expected_effect"] or ctx["rollback_condition"]:
        lines.append("## 预期效果与回滚")
        lines.append("")
        if ctx["expected_effect"]:
            lines.append(f"- 预期效果：{ctx['expected_effect']}")
        if ctx["rollback_condition"]:
            lines.append(f"- 回滚条件：{ctx['rollback_condition']}")
        lines.append("")

    if len(lines) <= 2:
        lines.append("_本轮未提供可沉淀的策略要点明细。_")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_fetch_sql(
    ctx: dict[str, Any],
    *,
    pg_schema: str,
    pg_channel_table: str,
    pg_dim_inter_table: str,
) -> str:
    intersection = ctx["intersection_name"] or DISPLAY_DASH
    inter_id = ctx["inter_id"] or DISPLAY_DASH
    period = ctx["time_period_label"] or DISPLAY_DASH
    direction = ctx["direction"] or DISPLAY_DASH
    return (
        f"-- 取数模板：{intersection}（inter_id={inter_id}）\n"
        f"-- 时段：{period}；方向：{direction}\n"
        "-- 说明：本文件为参数化取数模板，占位符 :inter_id / :start_time / :end_time\n"
        "--       由调用方在执行时注入；本模板不含任何示例结果行。\n"
        "SELECT\n"
        "    link.inter_id,\n"
        "    link.link_id,\n"
        "    inter.inter_name\n"
        f"FROM {pg_schema}.{pg_channel_table} AS link\n"
        f"JOIN {pg_schema}.{pg_dim_inter_table} AS inter\n"
        "    ON inter.inter_id = link.inter_id\n"
        "WHERE link.inter_id = :inter_id\n"
        "  AND :start_time <= :end_time\n"
        "ORDER BY link.inter_id, link.link_id;\n"
    )


def content_signature(
    *, skill_md: str, reference_md: str, fetch_sql: str, meta_core: dict[str, Any]
) -> str:
    """内容签名：拼接文件内容（不含时间戳/签名本身）后取 sha256。"""
    blob = "\n\x00\n".join(
        [
            skill_md,
            reference_md,
            fetch_sql,
            json.dumps(meta_core, ensure_ascii=False, sort_keys=True, default=str),
        ]
    )
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _absorption_stage(
    key: str,
    label: str,
    monologue: str,
    chips: list[dict[str, Any]],
    duration_ms: int,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "monologue": monologue,
        "evidence_chips": [c for c in chips if c.get("value") not in (None, "", [])],
        "duration_ms": duration_ms,
    }


def build_absorption(
    ctx: dict[str, Any],
    *,
    action: str,
    skill_id: str,
    existing_skill_count: int,
    file_names: list[str],
) -> dict[str, Any]:
    labels = dict(ABSORPTION_STAGE_DEFS)
    intersection = ctx["intersection_name"] or ctx["inter_id"] or DISPLAY_DASH
    period = ctx["time_period_label"] or DISPLAY_DASH
    problem = ctx["problem_type"] or DISPLAY_DASH
    constraint_total = len(ctx["constraints"]) + len(ctx["hard_constraints"])

    stages = [
        _absorption_stage(
            "recap",
            labels["recap"],
            f"回顾本轮已采纳的诊断与治理约束：{intersection}。",
            [
                {"key": "intersection", "label": "路口", "value": intersection},
                {"key": "period", "label": "时段", "value": period},
                {"key": "problem_type", "label": "问题类型", "value": problem},
            ],
            520,
        ),
        _absorption_stage(
            "decompose",
            labels["decompose"],
            "将约束与方向解构为可索引字段。",
            [
                {"key": "constraints", "label": "约束条数", "value": constraint_total},
                {"key": "directions", "label": "方向", "value": "、".join(ctx["directions"]) or None},
                {"key": "movement", "label": "转向", "value": ctx["movement"]},
            ],
            560,
        ),
        _absorption_stage(
            "retrieve",
            labels["retrieve"],
            "检索既有技能库，判断是否已有同键技能。",
            [
                {"key": "existing", "label": "既有技能数", "value": existing_skill_count},
                {"key": "skill_id", "label": "目录键", "value": skill_id},
            ],
            600,
        ),
        _absorption_stage(
            "compare",
            labels["compare"],
            "比对内容签名，得出创建 / 更新 / 无变化判定。",
            [
                {"key": "action", "label": "判定", "value": _ACTION_ABSORPTION.get(action, action)},
            ],
            520,
        ),
        _absorption_stage(
            "value",
            labels["value"],
            "对照固化前后的复用价值。",
            [
                {"key": "recommended", "label": "推荐做法", "value": len(ctx["recommended"])},
                {"key": "principles", "label": "策略原则", "value": len(ctx["principles"])},
            ],
            560,
        ),
        _absorption_stage(
            "blueprint",
            labels["blueprint"],
            "转化为可落盘的技能包蓝图。",
            [
                {"key": "files", "label": "待写文件", "value": len(file_names)},
            ],
            600,
        ),
    ]

    what_bullets = [
        b
        for b in [
            f"路口：{intersection}" if intersection != DISPLAY_DASH else None,
            f"时段：{period}" if period != DISPLAY_DASH else None,
            f"问题类型：{problem}" if problem != DISPLAY_DASH else None,
            f"沉淀约束：{constraint_total} 条" if constraint_total else None,
        ]
        if b
    ] or ["本轮成果已固化为可检索技能"]

    why_rows = [
        {
            "key": "reuse",
            "label": "复用方式",
            "before": "手工检索历史工单",
            "after": "技能库按标签自动命中",
        },
        {
            "key": "retrieval",
            "label": "检索方式",
            "before": "人工翻阅方案记录",
            "after": "按路口/时段/问题类型秒级匹配",
        },
        {
            "key": "fidelity",
            "label": "约束保真",
            "before": "口头传递易遗漏",
            "after": f"落盘 {constraint_total} 条约束" if constraint_total else "结构化落盘",
        },
    ]

    return {
        "action": _ACTION_ABSORPTION.get(action, action),
        "stages": stages,
        "value_snapshot": {
            "what": {"title": f"固化技能 {skill_id}", "bullets": what_bullets},
            "why_rows": why_rows,
            "delta_rows": [],
        },
    }


def build_build(files: list[dict[str, Any]]) -> dict[str, Any]:
    stages = [
        {"key": key, "label": label, "progress": STAGE_PROGRESS[key]}
        for key, label in BUILD_STAGE_DEFS
    ]
    return {"stages": stages, "files": files}


class SkillSolidificationService:
    """派生真实技能内容并 upsert 落盘，返回可视化结构化结果。"""

    def __init__(
        self,
        skills_root: Path,
        *,
        pg_schema: str = "road6",
        pg_channel_table: str = "dwd_tfc_rltn_wide_inter_ft_link",
        pg_dim_inter_table: str = "dim_inter_info",
    ) -> None:
        self.skills_root = Path(skills_root)
        self.pg_schema = pg_schema
        self.pg_channel_table = pg_channel_table
        self.pg_dim_inter_table = pg_dim_inter_table

    def solidify(
        self,
        *,
        trace_id: str,
        plan_id: str,
        diagnosis_ticket: Any = None,
        plan_snapshot: Any = None,
        strategy: Any = None,
        artifacts_summary: Any = None,
    ) -> dict[str, Any]:
        ctx = derive_context(
            diagnosis_ticket=diagnosis_ticket,
            strategy=strategy,
            plan_snapshot=plan_snapshot,
            artifacts_summary=artifacts_summary,
        )
        skill_id = compute_skill_id(ctx)
        skill_dir = self._skill_dir_rel(skill_id)
        tags = build_tags(ctx)

        skill_md = build_skill_md(ctx, skill_id)
        reference_md = build_reference_md(ctx)
        fetch_sql = build_fetch_sql(
            ctx,
            pg_schema=self.pg_schema,
            pg_channel_table=self.pg_channel_table,
            pg_dim_inter_table=self.pg_dim_inter_table,
        )

        # 签名只反映真实内容，不含随部署位置变化的 skill_dir。
        meta_core = {
            "skill_id": skill_id,
            "intersection": ctx["intersection_name"],
            "inter_id": ctx["inter_id"],
            "problem_type": ctx["problem_type"],
            "time_period_label": ctx["time_period_label"],
            "tags": tags,
        }
        signature = content_signature(
            skill_md=skill_md,
            reference_md=reference_md,
            fetch_sql=fetch_sql,
            meta_core=meta_core,
        )

        target_dir = self.skills_root / skill_id
        existing_meta = self._read_meta(target_dir / "skill.meta.json")
        existing_count = self._count_skills()
        now = _now_iso()

        if existing_meta is None:
            action = "created"
            created_at = now
            updated_at = now
            should_write = True
        elif existing_meta.get("content_signature") == signature:
            action = "unchanged"
            created_at = existing_meta.get("created_at") or now
            updated_at = existing_meta.get("updated_at") or created_at
            should_write = False
        else:
            action = "updated"
            created_at = existing_meta.get("created_at") or now
            updated_at = now
            should_write = True

        meta = {
            "skill_id": skill_id,
            "skill_dir": skill_dir,
            "created_at": created_at,
            "updated_at": updated_at,
            "intersection": ctx["intersection_name"],
            "inter_id": ctx["inter_id"],
            "problem_type": ctx["problem_type"],
            "time_period_label": ctx["time_period_label"],
            "tags": tags,
            "content_signature": signature,
        }
        meta_json = json.dumps(meta, ensure_ascii=False, indent=2) + "\n"

        files_spec = [
            ("SKILL.md", "SKILL.md", "markdown", skill_md),
            ("reference.md", "reference.md", "markdown", reference_md),
            ("scripts/fetch_traffic_data.sql", "fetch_traffic_data.sql", "sql", fetch_sql),
            ("skill.meta.json", "skill.meta.json", "json", meta_json),
        ]

        if should_write:
            self._write_files(target_dir, files_spec)

        files = [
            {"path": path, "name": name, "language": language, "content": content}
            for path, name, language, content in files_spec
        ]

        absorption = build_absorption(
            ctx,
            action=action,
            skill_id=skill_id,
            existing_skill_count=existing_count,
            file_names=[f["name"] for f in files],
        )

        return {
            "action": action,
            "skill_id": skill_id,
            "skill_dir": skill_dir,
            "download_url": f"/api/v1/agent/skills/{skill_id}/download",
            "intersection": ctx["intersection_name"],
            "inter_id": ctx["inter_id"],
            "time_period_label": ctx["time_period_label"],
            "tags": tags,
            "trace_id": trace_id,
            "plan_id": plan_id,
            "absorption": absorption,
            "build": build_build(files),
        }

    def list_skills(self) -> list[dict[str, Any]]:
        """读取 data/skills/*/skill.meta.json，按 updated_at 倒序返回；目录缺失降级为 []。"""
        if not self.skills_root.exists():
            return []
        skills: list[dict[str, Any]] = []
        for meta_path in sorted(self.skills_root.glob("*/skill.meta.json")):
            meta = self._read_meta(meta_path)
            if meta is None:
                continue
            meta = dict(meta)
            meta["download_url"] = f"/api/v1/agent/skills/{meta.get('skill_id')}/download"
            skills.append(meta)
        skills.sort(key=lambda m: m.get("updated_at") or "", reverse=True)
        return skills

    def resolve_skill_dir(self, skill_id: str) -> Path | None:
        """安全解析技能目录：拒绝非法字符/路径穿越，仅允许 skills_root 下已存在目录。"""
        if not skill_id or not SKILL_ID_PATTERN.match(skill_id):
            return None
        root = self.skills_root.resolve()
        target = (self.skills_root / skill_id).resolve()
        if target == root:
            return None
        if root not in target.parents:
            return None
        if not target.is_dir():
            return None
        return target

    def zip_skill(self, skill_id: str) -> bytes | None:
        target = self.resolve_skill_dir(skill_id)
        if target is None:
            return None
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(target.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=str(path.relative_to(target)))
        return buffer.getvalue()

    def _skill_dir_rel(self, skill_id: str) -> str:
        """技能目录相对路径：优先相对仓库根，否则相对 skills_root 父目录。"""
        target = (self.skills_root / skill_id).resolve()
        try:
            return str(target.relative_to(PROJECT_ROOT))
        except ValueError:
            return f"{self.skills_root.name}/{skill_id}"

    def _count_skills(self) -> int:
        if not self.skills_root.exists():
            return 0
        return sum(1 for _ in self.skills_root.glob("*/skill.meta.json"))

    @staticmethod
    def _read_meta(meta_path: Path) -> dict[str, Any] | None:
        if not meta_path.exists():
            return None
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def _write_files(target_dir: Path, files_spec: list[tuple[str, str, str, str]]) -> None:
        for rel_path, _name, _language, content in files_spec:
            file_path = target_dir / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
