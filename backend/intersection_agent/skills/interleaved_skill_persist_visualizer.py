"""L3 interleaved absorption + skill write visualization (≤40s demo)."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from intersection_agent.hooks.execution_emitter import ExecutionEmitter
from intersection_agent.models.domain import Session
from intersection_agent.models.skill import SkillDiff, SkillRecord, SkillUpsertResult
from intersection_agent.skills.absorption_renderer import (
    render_stage_lines,
    render_unchanged_short,
)
from intersection_agent.skills.absorption_narrative_service import (
    AbsorptionNarrative,
    AbsorptionNarrativeService,
)
from intersection_agent.skills.absorption_stage_emitter import (
    emit_absorption_stage,
    emit_lines_paced,
)
from intersection_agent.skills.demo_pacing import (
    FILE_TYPING_SPEED_FACTOR,
    FILE_WRITE_BUDGET_SEC,
    L3_LINE_BUDGET_SEC,
    PACKAGING_BUDGET_SEC,
    STAGE_BUDGETS,
    WRITE_PHASE_BUDGET_SEC,
)
from intersection_agent.skills.experience_absorption import (
    ExperienceAbsorptionReport,
    build_absorption_report,
)
from intersection_agent.skills.package_builder import PACKAGE_FILE_PATHS, SkillPackageBuilder
from intersection_agent.skills.skill_build_visualizer import (
    FILE_LANGUAGE,
    FILE_STAGES,
    STAGE_PROGRESS,
    compute_line_diff,
    _typing_chunks,
)

if TYPE_CHECKING:
    from intersection_agent.services.skill_service import SkillService

logger = logging.getLogger(__name__)

MIND_STAGES = ("recap", "retrieve", "compare", "value")


class InterleavedSkillPersistVisualizer:
    """Emit paced absorption mind-phase, then L3 interleaved file write."""

    def __init__(self, skill_service: SkillService, builder: SkillPackageBuilder) -> None:
        self._skills = skill_service
        self._builder = builder
        self._narrative = AbsorptionNarrativeService()

    async def emit(
        self,
        *,
        session: Session,
        candidate: SkillRecord,
        existing: SkillRecord | None,
        diff: SkillDiff,
        snapshot_equal: bool,
        upsert_action: str,
        emitter: ExecutionEmitter,
    ) -> tuple[ExperienceAbsorptionReport, SkillUpsertResult]:
        all_skills = self._skills.list_skills()
        report = build_absorption_report(
            session=session,
            candidate=candidate,
            existing=existing,
            diff=diff,
            all_skills=all_skills,
            snapshot_equal=snapshot_equal,
        )

        await emitter.emit_skill_absorption(
            "skill_absorption_start",
            "",
            session_id=session.session_id,
            skill_id=report.skill_id,
            intersection=report.intersection,
            action=report.action,
        )

        if report.action == "UNCHANGED":
            await self._emit_unchanged(report, emitter)
            download_url = f"/api/v1/skills/{report.skill_id}/download"
            await emitter.emit_skill_build(
                "skill_build_done",
                "packaging",
                display_text="技能已是最新。",
                progress=100,
                skill_id=candidate.skill_id,
                skill_dir=candidate.skill_dir,
                action="unchanged",
                download_url=download_url,
            )
            await emitter.emit_skill_absorption(
                "skill_absorption_done",
                "",
                action=report.action,
                skill_id=report.skill_id,
                progress=100,
            )
            return report, SkillUpsertResult(record=existing or candidate, action="unchanged")

        narrative = await self._narrative.generate(report, session)

        for stage in MIND_STAGES:
            await emit_absorption_stage(
                emitter,
                report,
                stage,
                STAGE_BUDGETS[stage],
                lines=narrative.lines_for(stage, report),
            )

        await emit_absorption_stage(
            emitter,
            report,
            "blueprint",
            STAGE_BUDGETS["blueprint_intro"],
            lines=narrative.lines_for("blueprint", report),
        )

        result = await self._emit_interleaved_write(
            record=candidate,
            session=session,
            report=report,
            narrative=narrative,
            upsert_action=upsert_action,
            diff_changes=diff.changes,
            emitter=emitter,
        )

        await emitter.emit_skill_absorption(
            "skill_absorption_done",
            "",
            action=report.action,
            skill_id=report.skill_id,
            progress=100,
            library_count_before=report.library_count_before,
            library_count_after=report.library_count_after,
        )

        logger.info(
            "skill.interleaved_persist skill_id=%s action=%s",
            report.skill_id,
            upsert_action,
        )
        return report, result

    async def _emit_unchanged(
        self,
        report: ExperienceAbsorptionReport,
        emitter: ExecutionEmitter,
    ) -> None:
        await emitter.emit_skill_absorption(
            "stage_start",
            "compare",
            display_text="compare",
            action=report.action,
        )
        await emit_lines_paced(
            emitter,
            stage="compare",
            lines=render_unchanged_short(report),
            budget_sec=3.0,
        )
        await emitter.emit_skill_absorption(
            "stage_done",
            "compare",
            action=report.action,
        )

    async def _emit_interleaved_write(
        self,
        *,
        record: SkillRecord,
        session: Session,
        report: ExperienceAbsorptionReport,
        narrative: AbsorptionNarrative,
        upsert_action: str,
        diff_changes: list[str],
        emitter: ExecutionEmitter,
    ) -> SkillUpsertResult:
        record.tags = report.tags
        new_files = self._builder.build_file_contents(record, session)
        old_files = self._builder.read_package_files(record) if upsert_action == "update" else {}
        is_update = upsert_action == "update" and bool(old_files)

        await emitter.emit_skill_absorption(
            "write_phase_start",
            "blueprint",
            display_text="interleaved_write",
            budget_sec=WRITE_PHASE_BUDGET_SEC,
        )

        await emitter.emit_skill_build(
            "drawer_open",
            "writing",
            display_text="终端抽屉已展开",
            action=upsert_action,
            skill_id=record.skill_id,
            intersection=record.intersection,
            time_period_label=record.time_period_label,
            diff_changes=diff_changes,
            is_update=is_update,
            progress=10,
        )

        await emitter.emit_skill_build(
            "skill_build_start",
            "writing",
            display_text="开始写入技能包",
            progress=12,
            action=upsert_action,
            skill_id=record.skill_id,
            intersection=record.intersection,
            time_period_label=record.time_period_label,
            diff_changes=diff_changes,
            is_update=is_update,
            interleaved=True,
        )

        write_started = time.perf_counter()
        blueprint_log_started = False
        for rel in PACKAGE_FILE_PATHS:
            if time.perf_counter() - write_started > WRITE_PHASE_BUDGET_SEC + 2:
                break
            linkage_lines = narrative.linkage_for(report, rel)
            linkage_budget = L3_LINE_BUDGET_SEC * max(len(linkage_lines), 1)
            await emit_lines_paced(
                emitter,
                stage="blueprint",
                lines=linkage_lines,
                budget_sec=linkage_budget,
                continue_previous=blueprint_log_started,
            )
            blueprint_log_started = blueprint_log_started or bool(linkage_lines)
            await self._write_file_paced(
                emitter,
                record=record,
                rel=rel,
                content=new_files[rel],
                old_content=old_files.get(rel, ""),
                is_update=is_update,
                budget_sec=FILE_WRITE_BUDGET_SEC,
            )

        await self._packaging_paced(emitter, record, upsert_action, PACKAGING_BUDGET_SEC)

        download_url = f"/api/v1/skills/{record.skill_id}/download"
        await emitter.emit_skill_build(
            "drawer_close",
            "packaging",
            display_text="终端抽屉收起",
            progress=98,
        )
        await emitter.emit_skill_build(
            "skill_build_done",
            "packaging",
            display_text="技能沉淀完成。",
            progress=100,
            skill_id=record.skill_id,
            skill_dir=record.skill_dir,
            action=upsert_action,
            download_url=download_url,
        )

        return SkillUpsertResult(record=record, action=upsert_action)

    async def _write_file_paced(
        self,
        emitter: ExecutionEmitter,
        *,
        record: SkillRecord,
        rel: str,
        content: str,
        old_content: str,
        is_update: bool,
        budget_sec: float,
    ) -> None:
        stage = FILE_STAGES[rel]
        language = FILE_LANGUAGE[rel]
        has_diff = is_update and old_content and old_content != content

        await emitter.emit_skill_build(
            "stage_start",
            stage,
            display_text=f"writing {Path(rel).name}",
            progress=STAGE_PROGRESS[stage] - 6,
            path=rel,
        )

        if has_diff:
            line_diff = compute_line_diff(old_content, content)
            await emitter.emit_skill_build(
                "file_diff",
                stage,
                path=rel,
                language=language,
                lines=line_diff,
            )

        await emitter.emit_skill_build(
            "file_created",
            stage,
            path=rel,
            language=language,
            is_update=has_diff,
        )

        chunks = _typing_chunks(content)
        delay = max(0.014, min(0.042, budget_sec / max(len(chunks), 1)))
        delay /= FILE_TYPING_SPEED_FACTOR

        accumulated = ""
        for chunk in chunks:
            accumulated += chunk
            await emitter.emit_skill_build(
                "file_delta",
                stage,
                path=rel,
                language=language,
                delta=chunk,
            )
            await asyncio.sleep(delay)

        self._builder.write_file(record, rel, accumulated)

        await emitter.emit_skill_build(
            "file_done",
            stage,
            path=rel,
        )
        await emitter.emit_skill_build(
            "stage_done",
            stage,
            progress=STAGE_PROGRESS[stage],
            path=rel,
        )

    async def _packaging_paced(
        self,
        emitter: ExecutionEmitter,
        record: SkillRecord,
        upsert_action: str,
        budget_sec: float,
    ) -> None:
        await emitter.emit_skill_absorption(
            "thought_delta",
            "blueprint",
            delta="打包技能产物，写入完成。",
        )
        await emitter.emit_skill_build(
            "stage_start",
            "packaging",
            display_text="packaging",
            progress=92,
        )
        await asyncio.sleep(budget_sec)
        await emitter.emit_skill_build(
            "stage_done",
            "packaging",
            progress=100,
        )
