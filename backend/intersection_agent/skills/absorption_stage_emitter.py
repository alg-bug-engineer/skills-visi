"""Paced absorption stage emitter (demo timing)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from intersection_agent.hooks.execution_emitter import ExecutionEmitter
from intersection_agent.skills.absorption_renderer import render_stage_lines
from intersection_agent.skills.demo_pacing import (
    CHAR_DELAY_MS,
    CHUNK_CHAR_SIZE,
    RETRIEVE_SCAN_PAUSE_SEC,
    STAGE_GAP_SEC,
    VALUE_DWELL_SEC,
)
from intersection_agent.skills.experience_absorption import ExperienceAbsorptionReport


async def emit_lines_paced(
    emitter: ExecutionEmitter,
    *,
    stage: str,
    lines: list[str],
    budget_sec: float,
    continue_previous: bool = False,
) -> None:
    """Type out log lines within a stage time budget."""
    if not lines:
        await asyncio.sleep(min(budget_sec, STAGE_GAP_SEC))
        return

    total_chars = 0
    stripped_lines: list[str] = []
    for line in lines:
        text = line.removeprefix("> ").strip()
        if not text:
            continue
        stripped_lines.append(text)
    for index, text in enumerate(stripped_lines):
        prefix_len = 3 if index == 0 and continue_previous else (2 if index == 0 else 3)
        total_chars += prefix_len + len(text)
    if total_chars <= 0:
        await asyncio.sleep(budget_sec)
        return

    delay = min(CHAR_DELAY_MS / 1000.0, budget_sec / max(total_chars, 1))
    typed_any = continue_previous
    for line in lines:
        text = line.removeprefix("> ").strip()
        if not text:
            continue
        prefix = "\n> " if typed_any else "> "
        typed_any = True
        payload = prefix + text
        for index in range(0, len(payload), CHUNK_CHAR_SIZE):
            await emitter.emit_skill_absorption(
                "thought_delta",
                stage,
                delta=payload[index : index + CHUNK_CHAR_SIZE],
            )
            await asyncio.sleep(delay)


async def emit_absorption_stage(
    emitter: ExecutionEmitter,
    report: ExperienceAbsorptionReport,
    stage: str,
    budget_sec: float,
    *,
    lines: list[str] | None = None,
) -> None:
    """Emit one absorption stage with pacing and optional pauses."""
    started = time.perf_counter()
    await emitter.emit_skill_absorption(
        "stage_start",
        stage,
        display_text=f"stage:{stage}",
        **stage_start_payload(report, stage),
    )

    if stage == "retrieve":
        await emitter.emit_skill_absorption(
            "stage_running",
            stage,
            display_text="scanning",
        )
        await asyncio.sleep(RETRIEVE_SCAN_PAUSE_SEC)

    stage_lines = lines if lines is not None else render_stage_lines(report, stage)
    typing_budget = budget_sec
    if stage == "retrieve":
        typing_budget = max(1.0, budget_sec - RETRIEVE_SCAN_PAUSE_SEC)
    elif stage == "value":
        typing_budget = max(1.5, budget_sec - VALUE_DWELL_SEC)

    await emit_lines_paced(emitter, stage=stage, lines=stage_lines, budget_sec=typing_budget)

    evidence = stage_evidence(report, stage)
    if evidence:
        chips = evidence.pop("chips", None)
        experience_chips = evidence.pop("experience_chips", None)
        if experience_chips:
            chip_delay = min(0.55, typing_budget / max(len(experience_chips), 1))
            for chip in experience_chips:
                await emitter.emit_skill_absorption("evidence", stage, chip=chip)
                await asyncio.sleep(chip_delay)
        elif chips:
            evidence["chips"] = chips
            await emitter.emit_skill_absorption("evidence", stage, **evidence)
        else:
            await emitter.emit_skill_absorption("evidence", stage, **evidence)

    if stage == "value":
        await asyncio.sleep(VALUE_DWELL_SEC)

    await asyncio.sleep(STAGE_GAP_SEC)
    await emitter.emit_skill_absorption(
        "stage_done",
        stage,
        duration_ms=int((time.perf_counter() - started) * 1000),
        **stage_done_payload(report, stage),
    )


async def emit_absorption_line(
    emitter: ExecutionEmitter,
    *,
    stage: str,
    line: str,
    budget_sec: float,
) -> None:
    """Emit a single L3 linkage line during interleaved write."""
    await emit_lines_paced(emitter, stage=stage, lines=[line], budget_sec=budget_sec)


def stage_start_payload(report: ExperienceAbsorptionReport, stage: str) -> dict[str, Any]:
    if stage == "recap":
        return {
            "utterance_summary": report.utterance_summary,
            "experience_points": report.experience_points,
        }
    if stage == "retrieve":
        return {
            "total_skills": report.retrieve.total_skills,
            "query": report.retrieve.query,
        }
    if stage == "compare":
        return {"action": report.action}
    if stage == "value":
        return {
            "what": report.what,
            "why_rows": report.why_rows,
            "delta_rows": report.delta_rows,
            "experience_points": report.experience_points,
        }
    if stage == "blueprint":
        return {
            "files": report.blueprint_files,
            "package_dir": report.package_dir,
        }
    return {}


def stage_evidence(report: ExperienceAbsorptionReport, stage: str) -> dict[str, Any]:
    if stage == "value" and report.experience_points:
        return {
            "experience_chips": [
                {
                    "key": f"experience.{index}",
                    "label": "沉淀",
                    "value": point,
                }
                for index, point in enumerate(report.experience_points)
            ]
        }
    if stage == "retrieve":
        return {"candidates": report.retrieve.candidates}
    if stage == "compare":
        return {
            "changes": report.delta_rows,
            "action": report.action,
        }
    return {}


def stage_done_payload(report: ExperienceAbsorptionReport, stage: str) -> dict[str, Any]:
    if stage == "retrieve":
        return {
            "matched": report.retrieve.matched,
            "hit_count": report.retrieve.hit_count,
        }
    if stage == "compare":
        return {"action": report.action}
    if stage == "value":
        return {
            "library_count_before": report.library_count_before,
            "library_count_after": report.library_count_after,
        }
    return {}
