"""Stream experience-absorption events for frontend visualization."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from intersection_agent.hooks.execution_emitter import ExecutionEmitter
from intersection_agent.models.domain import Session
from intersection_agent.models.skill import SkillDiff, SkillRecord
from intersection_agent.skills.absorption_narrative_service import (
    AbsorptionNarrative,
    AbsorptionNarrativeService,
)
from intersection_agent.skills.absorption_renderer import render_stage_lines, render_unchanged_short
from intersection_agent.skills.absorption_stage_emitter import (
    stage_done_payload,
    stage_evidence,
    stage_start_payload,
)
from intersection_agent.skills.experience_absorption import (
    ExperienceAbsorptionReport,
    build_absorption_report,
)

if TYPE_CHECKING:
    from intersection_agent.services.skill_service import SkillService

logger = logging.getLogger(__name__)

STAGES = ("recap", "retrieve", "compare", "value", "blueprint")
CHUNK_DELAY_SEC = 0.03
STAGE_GAP_SEC = 0.05


class ExperienceAbsorptionVisualizer:
    """Emit skill_absorption SSE before skill package file writing."""

    def __init__(self, skill_service: SkillService) -> None:
        self._skills = skill_service
        self._narrative = AbsorptionNarrativeService()

    async def emit(
        self,
        *,
        session: Session,
        candidate: SkillRecord,
        existing: SkillRecord | None,
        diff: SkillDiff,
        snapshot_equal: bool,
        emitter: ExecutionEmitter,
    ) -> ExperienceAbsorptionReport:
        """Build report, stream stages, return report for caller."""
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
            await self._emit_compressed(report, emitter)
        else:
            narrative = await self._narrative.generate(report, session)
            for stage in STAGES:
                await self._emit_stage(report, stage, emitter, narrative)

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
            "skill.absorption_visualized skill_id=%s action=%s",
            report.skill_id,
            report.action,
        )
        return report

    async def _emit_compressed(
        self,
        report: ExperienceAbsorptionReport,
        emitter: ExecutionEmitter,
    ) -> None:
        started = time.perf_counter()
        await emitter.emit_skill_absorption(
            "stage_start",
            "compare",
            display_text="比对库中快照",
            action=report.action,
        )
        for line in render_unchanged_short(report):
            await self._emit_line(emitter, "compare", line)
        await emitter.emit_skill_absorption(
            "stage_done",
            "compare",
            duration_ms=int((time.perf_counter() - started) * 1000),
            action=report.action,
        )

    async def _emit_stage(
        self,
        report: ExperienceAbsorptionReport,
        stage: str,
        emitter: ExecutionEmitter,
        narrative: AbsorptionNarrative | None = None,
    ) -> None:
        started = time.perf_counter()
        await emitter.emit_skill_absorption(
            "stage_start",
            stage,
            display_text=f"stage:{stage}",
            **stage_start_payload(report, stage),
        )

        lines = narrative.lines_for(stage, report) if narrative else render_stage_lines(report, stage)

        for line in lines:
            await self._emit_line(emitter, stage, line)

        evidence = stage_evidence(report, stage)
        if evidence:
            experience_chips = evidence.pop("experience_chips", None)
            if experience_chips:
                for chip in experience_chips:
                    await emitter.emit_skill_absorption("evidence", stage, chip=chip)
            else:
                await emitter.emit_skill_absorption("evidence", stage, **evidence)

        await asyncio.sleep(STAGE_GAP_SEC)
        await emitter.emit_skill_absorption(
            "stage_done",
            stage,
            duration_ms=int((time.perf_counter() - started) * 1000),
            **stage_done_payload(report, stage),
        )

    async def _emit_line(self, emitter: ExecutionEmitter, stage: str, line: str) -> None:
        text = line.removeprefix("> ").strip()
        if not text:
            return
        chunk_size = 12
        for index in range(0, len(text), chunk_size):
            await emitter.emit_skill_absorption(
                "thought_delta",
                stage,
                delta=text[index : index + chunk_size],
            )
            await asyncio.sleep(CHUNK_DELAY_SEC)
