"""LLM-guided monologue for experience absorption (grounded in report facts)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from intersection_agent.llm.qwen_client import QwenClient
from intersection_agent.logging.helpers import log_event, safe_preview
from intersection_agent.models.domain import Session
from intersection_agent.skills.absorption_renderer import (
    render_file_linkage_lines,
    render_stage_lines,
)
from intersection_agent.skills.experience_absorption import ExperienceAbsorptionReport
from intersection_agent.skills.package_builder import PACKAGE_FILE_PATHS

logger = logging.getLogger(__name__)

MIND_STAGES = ("recap", "retrieve", "compare", "value", "blueprint")

BANNED_PHRASES = (
    "左侧",
    "右侧",
    "左栏",
    "右栏",
    "终端",
    "抽屉",
    "落笔",
    "继续追踪",
    "追踪面板",
    "界面",
    "众智成城",
    "接下来为您",
    "为您介绍",
    "tags.match",
    "解构 tags",
)

ABSORPTION_NARRATIVE_SYSTEM = """
你是交通智能体内部的「经验吸收追踪日志」生成器。根据给定的事实 JSON，生成各阶段的系统自言自语日志。

硬性规则：
1. 每行是完整中文句子，不要以 "> " 开头（系统会自动加前缀）
2. 禁止描述 UI、布局、终端、抽屉、左/右侧、落笔、追踪面板等任何界面元素
3. 禁止宣讲口吻（「接下来」「为您」「众智成城意味着」等）
4. 只能使用事实 JSON 中的字段与数值，禁止编造
5. recap 与 value 必须点出 experience_points 里的本次经验沉淀（约束、治理边界、诊断特点）
6. retrieve/compare 只陈述库检索与比对结果
7. blueprint 只说明即将写入的技能包目录与文件清单，不涉及界面
8. file_linkage 为写文件时的联动说明，每文件 1-2 行，须体现该文件承载的经验点（若有）

输出严格 JSON，字段：
{
  "recap": ["...", "..."],
  "retrieve": ["..."],
  "compare": ["..."],
  "value": ["..."],
  "blueprint": ["..."],
  "file_linkage": {
    "SKILL.md": ["...", "..."],
    "reference.md": ["..."],
    ...
  }
}
每阶段 2-5 行，每行不超过 80 字。
""".strip()


@dataclass
class AbsorptionNarrative:
    """Stage lines keyed by stage name; file_linkage keyed by package relative path."""

    stages: dict[str, list[str]] = field(default_factory=dict)
    file_linkage: dict[str, list[str]] = field(default_factory=dict)

    def lines_for(self, stage: str, report: ExperienceAbsorptionReport) -> list[str]:
        cached = self.stages.get(stage)
        if cached:
            return [_ensure_prefix(line) for line in cached]
        return render_stage_lines(report, stage)

    def linkage_for(self, report: ExperienceAbsorptionReport, rel_path: str) -> list[str]:
        cached = self.file_linkage.get(rel_path)
        if cached:
            return [_ensure_prefix(line) for line in cached]
        return render_file_linkage_lines(report, rel_path)


class AbsorptionNarrativeService:
    """Generate paced absorption copy via LLM with template fallback."""

    def __init__(self, llm: QwenClient | None = None) -> None:
        self._llm = llm or QwenClient()

    async def generate(
        self,
        report: ExperienceAbsorptionReport,
        session: Session,
    ) -> AbsorptionNarrative:
        facts = _build_facts(report, session)
        try:
            raw = await self._llm.chat_json(
                system=ABSORPTION_NARRATIVE_SYSTEM,
                user=json.dumps(facts, ensure_ascii=False),
            )
            narrative = _parse_llm_output(raw, report)
            log_event(
                logger,
                logging.INFO,
                "absorption.narrative.generated",
                skill_id=report.skill_id,
                preview=safe_preview(json.dumps(narrative.stages, ensure_ascii=False), 200),
            )
            return narrative
        except (ValueError, RuntimeError) as exc:
            logger.warning("absorption narrative LLM failed, using fallback: %s", exc)
            return _fallback_narrative(report)

    async def generate_sync_fallback(self, report: ExperienceAbsorptionReport) -> AbsorptionNarrative:
        """Template-only narrative (tests / explicit offline)."""
        return _fallback_narrative(report)


def _build_facts(report: ExperienceAbsorptionReport, session: Session) -> dict[str, Any]:
    match_tags = report.tags.get("match") or {}
    content_tags = report.tags.get("content") or {}
    return {
        "action": report.action,
        "skill_id": report.skill_id,
        "intersection": report.intersection,
        "utterance_summary": report.utterance_summary,
        "experience_points": report.experience_points,
        "match": {
            "inter_id": match_tags.get("inter_id"),
            "time_period": match_tags.get("time_period"),
            "directions": match_tags.get("directions") or [],
            "problem_type": match_tags.get("problem_type"),
        },
        "content": {
            "rule_ids": content_tags.get("rule_ids") or [],
            "constraint_intent": content_tags.get("constraint_intent"),
            "issue_codes": content_tags.get("issue_codes") or [],
            "data_window_profile": content_tags.get("data_window_profile"),
        },
        "retrieve": {
            "total_skills": report.retrieve.total_skills,
            "hit_count": report.retrieve.hit_count,
            "matched": report.retrieve.matched,
        },
        "delta_rows": report.delta_rows,
        "what": report.what,
        "library_count_before": report.library_count_before,
        "library_count_after": report.library_count_after,
        "package_dir": report.package_dir,
        "blueprint_files": report.blueprint_files,
        "diagnosis_summary": _diagnosis_summary(session),
    }


def _diagnosis_summary(session: Session) -> str:
    if not session.diagnosis or not session.diagnosis.matched_rules:
        return ""
    parts: list[str] = []
    for rule in session.diagnosis.matched_rules[:3]:
        rule_id = rule.get("id") or rule.get("rule_id")
        if rule_id:
            parts.append(str(rule_id))
    return "、".join(parts)


def _parse_llm_output(raw: dict[str, Any], report: ExperienceAbsorptionReport) -> AbsorptionNarrative:
    stages: dict[str, list[str]] = {}
    for stage in MIND_STAGES:
        lines = _sanitize_lines(raw.get(stage))
        if lines:
            stages[stage] = lines
        else:
            stages[stage] = _strip_prefixes(render_stage_lines(report, stage))

    file_linkage: dict[str, list[str]] = {}
    raw_linkage = raw.get("file_linkage")
    if isinstance(raw_linkage, dict):
        for rel in PACKAGE_FILE_PATHS:
            lines = _sanitize_lines(raw_linkage.get(rel))
            if lines:
                file_linkage[rel] = lines

    return AbsorptionNarrative(stages=stages, file_linkage=file_linkage)


def _fallback_narrative(report: ExperienceAbsorptionReport) -> AbsorptionNarrative:
    stages = {stage: _strip_prefixes(render_stage_lines(report, stage)) for stage in MIND_STAGES}
    file_linkage = {
        rel: _strip_prefixes(render_file_linkage_lines(report, rel)) for rel in PACKAGE_FILE_PATHS
    }
    return AbsorptionNarrative(stages=stages, file_linkage=file_linkage)


def _sanitize_lines(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    lines: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        if any(banned in text for banned in BANNED_PHRASES):
            continue
        lines.append(text)
    return lines


def _strip_prefixes(lines: list[str]) -> list[str]:
    return [line.removeprefix("> ").strip() for line in lines if line.strip()]


def _ensure_prefix(line: str) -> str:
    text = line.strip()
    if not text:
        return text
    return text if text.startswith("> ") else f"> {text}"


def contains_banned_narration(text: str) -> bool:
    """Test helper: detect forbidden UI/meta narration."""
    return any(phrase in text for phrase in BANNED_PHRASES)


def mock_narration_from_facts(facts: dict[str, Any]) -> dict[str, Any]:
    """Deterministic mock JSON for offline LLM."""
    points = facts.get("experience_points") or []
    match = facts.get("match") or {}
    action = facts.get("action", "CREATE")
    retrieve = facts.get("retrieve") or {}
    package_dir = facts.get("package_dir", "pkg")

    recap = ["收到固化指令。"]
    if facts.get("utterance_summary"):
        recap.append(f"挂载会话：「{facts['utterance_summary']}」")
    for point in points[:2]:
        recap.append(f"识别本次沉淀：{point}")

    retrieve_lines = [
        f"扫描经验库：共 {retrieve.get('total_skills', 0)} 条，"
        f"match 过滤后 {retrieve.get('hit_count', 0)} 条。",
    ]
    if retrieve.get("hit_count", 0) == 0:
        retrieve_lines.append(f"槽位 {facts.get('skill_id', '')} 尚无同类记录。")

    compare_lines = [f"判定：{action}。"]
    if action == "CREATE":
        compare_lines.append(
            f"经验库 {facts.get('library_count_before')} → {facts.get('library_count_after')}。"
        )

    value_lines = [f"沉淀物：{facts.get('what', {}).get('title', facts.get('intersection'))}"]
    for point in points:
        value_lines.append(point)

    blueprint_lines = [
        f"准备写入技能包 {package_dir}。",
        f"将落盘：{', '.join(facts.get('blueprint_files') or [])}。",
    ]

    constraint_hint = points[0] if points else "场景 match 键"
    file_linkage = {
        "SKILL.md": [
            "写入 SKILL.md，固化场景键与快路径触发说明。",
            f"纳入本次特点：{constraint_hint}。",
        ],
        "reference.md": [
            "写入 reference.md，保存诊断结论与规则快照。",
            f"保留治理边界：{constraint_hint}。",
        ],
    }

    return {
        "recap": recap,
        "retrieve": retrieve_lines,
        "compare": compare_lines,
        "value": value_lines,
        "blueprint": blueprint_lines,
        "file_linkage": file_linkage,
    }
