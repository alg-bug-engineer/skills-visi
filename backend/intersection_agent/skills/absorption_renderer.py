"""Template monologue lines for experience absorption (LLM fallback)."""

from __future__ import annotations

from pathlib import Path

from intersection_agent.skills.experience_absorption import ExperienceAbsorptionReport
from intersection_agent.skills.package_builder import (
    META_FILENAME,
    REFERENCE_FILENAME,
    SKILL_FILENAME,
)


def _match_summary(report: ExperienceAbsorptionReport) -> str:
    match_tags = report.tags.get("match") or {}
    inter_id = match_tags.get("inter_id", "—")
    period = match_tags.get("time_period", "—")
    directions = match_tags.get("directions") or []
    direction_text = "、".join(directions) if directions else "—"
    return f"{inter_id} · {period} · {direction_text}"


def _rule_summary(report: ExperienceAbsorptionReport) -> str:
    content = report.tags.get("content") or {}
    rule_ids = content.get("rule_ids") or []
    return "、".join(rule_ids) if rule_ids else "—"


def _profile_summary(report: ExperienceAbsorptionReport) -> str:
    content = report.tags.get("content") or {}
    profile = content.get("data_window_profile")
    return str(profile) if profile else "data_window_profile"


def _experience_hint(report: ExperienceAbsorptionReport) -> str:
    if report.experience_points:
        return report.experience_points[0]
    return _match_summary(report)


def render_stage_lines(report: ExperienceAbsorptionReport, stage: str) -> list[str]:
    """Return system-voice log lines for a stage."""
    renderers = {
        "recap": _recap_lines,
        "retrieve": _retrieve_lines,
        "compare": _compare_lines,
        "value": _value_lines,
        "blueprint": _blueprint_intro_lines,
    }
    renderer = renderers.get(stage)
    if not renderer:
        return []
    return renderer(report)


def render_file_linkage_lines(
    report: ExperienceAbsorptionReport,
    rel_path: str,
) -> list[str]:
    """L3: narration while skill package files are written."""
    match_text = _match_summary(report)
    rule_text = _rule_summary(report)
    profile_text = _profile_summary(report)
    content = report.tags.get("content") or {}
    constraint = content.get("constraint_intent") or _experience_hint(report)
    what_bullets = report.what.get("bullets") or []
    bullet_hint = what_bullets[0] if what_bullets else match_text
    version = (report.tags.get("meta") or {}).get("version", report.version)

    builders: dict[str, list[str]] = {
        SKILL_FILENAME: [
            f"> 写入 SKILL.md：场景键 {match_text}。",
            f"> 纳入本次经验：{_experience_hint(report)}。",
        ],
        REFERENCE_FILENAME: [
            f"> 写入 reference.md：规则快照 [{rule_text}]。",
            f"> 固化治理边界：{constraint}。",
        ],
        "scripts/fetch_traffic_data.sql": [
            f"> 写入 fetch_traffic_data.sql，锚定查数口径 {profile_text}。",
            f"> 绑定路口 {match_text.split(' · ')[0] if ' · ' in match_text else match_text}。",
        ],
        "scripts/fetch_traffic_data.py": [
            "> 写入 fetch_traffic_data.py，与 SQL 口径一致。",
            "> 供快路径自动复用，减少重复查数。",
        ],
        META_FILENAME: [
            "> 写入 skill.meta.json：match / content / meta 三层索引。",
            f"> 版本 v{version}；{bullet_hint}。",
        ],
    }

    lines = builders.get(rel_path)
    if not lines:
        name = Path(rel_path).name
        return [f"> 写入 {name}，纳入 {report.package_dir}。"]

    return lines


def render_file_linkage_line(report: ExperienceAbsorptionReport, rel_path: str) -> str:
    """Single-line L3 linkage (compat)."""
    lines = render_file_linkage_lines(report, rel_path)
    return lines[0] if lines else f"> 写入 {Path(rel_path).name}。"


def _recap_lines(report: ExperienceAbsorptionReport) -> list[str]:
    lines = ["> 收到固化指令。"]
    if report.utterance_summary:
        lines.append(f"> 挂载会话摘要：「{report.utterance_summary}」")
    for point in report.experience_points[:2]:
        lines.append(f"> 识别本次沉淀：{point}")
    return lines


def _retrieve_lines(report: ExperienceAbsorptionReport) -> list[str]:
    retrieve = report.retrieve
    lines = [
        f"> 扫描经验库：共 {retrieve.total_skills} 条，match 过滤后 {retrieve.hit_count} 条。",
    ]
    if retrieve.hit_count == 0:
        lines.append(f"> 槽位 {report.skill_id} 尚无同类记录。")
    else:
        for candidate in retrieve.candidates[:3]:
            lines.append(f"> 候选 skill_id={candidate['skill_id']} created_at={candidate['created_at']}")
    return lines


def _compare_lines(report: ExperienceAbsorptionReport) -> list[str]:
    action = report.action
    lines = [f"> 判定：{action}。"]
    if action == "UPDATE" and report.delta_rows:
        for change in report.delta_rows:
            lines.append(f"> diff：{change}")
    elif action == "UNCHANGED":
        lines.append("> 快照与库中记录一致，跳过实质更新。")
    elif action == "CREATE":
        lines.append(
            f"> 经验库计数 {report.library_count_before} → {report.library_count_after}。"
        )
    return lines


def _value_lines(report: ExperienceAbsorptionReport) -> list[str]:
    lines = [f"> 沉淀物：{report.what.get('title', report.intersection)}"]
    for point in report.experience_points:
        lines.append(f"> {point}")
    lines.append(
        f"> 经验库计数 {report.library_count_before} → {report.library_count_after}。"
    )
    return lines


def _blueprint_intro_lines(report: ExperienceAbsorptionReport) -> list[str]:
    files = "、".join(Path(p).name for p in report.blueprint_files[:5])
    return [
        f"> 准备写入技能包 {report.package_dir}。",
        f"> 将落盘：{files}。",
    ]


def render_unchanged_short(report: ExperienceAbsorptionReport) -> list[str]:
    """Compressed monologue when snapshot is unchanged."""
    return [
        "> 收到固化指令。",
        f"> 扫描经验库：槽位 {report.skill_id} 已存在。",
        "> 判定：UNCHANGED。快照与库中记录一致。",
        "> 吸收完成。",
    ]
