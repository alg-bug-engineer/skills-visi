"""Stream skill package creation events for frontend visualization."""

from __future__ import annotations

import asyncio
import difflib
import logging
from pathlib import Path
from typing import Any

from intersection_agent.hooks.execution_emitter import ExecutionEmitter
from intersection_agent.models.domain import Session
from intersection_agent.models.skill import SkillRecord, SkillUpsertResult
from intersection_agent.skills.package_builder import (
    META_FILENAME,
    PACKAGE_FILE_PATHS,
    REFERENCE_FILENAME,
    SKILL_FILENAME,
    SkillPackageBuilder,
)

logger = logging.getLogger(__name__)

STAGE_PROGRESS: dict[str, int] = {
    "understanding": 8,
    "planning": 16,
    "writing_skill_md": 32,
    "writing_reference": 48,
    "writing_scripts": 72,
    "writing_meta": 88,
    "packaging": 100,
}

FILE_STAGES: dict[str, str] = {
    SKILL_FILENAME: "writing_skill_md",
    REFERENCE_FILENAME: "writing_reference",
    "scripts/fetch_traffic_data.sql": "writing_scripts",
    "scripts/fetch_traffic_data.py": "writing_scripts",
    META_FILENAME: "writing_meta",
}

FILE_LANGUAGE: dict[str, str] = {
    SKILL_FILENAME: "markdown",
    REFERENCE_FILENAME: "markdown",
    "scripts/fetch_traffic_data.sql": "sql",
    "scripts/fetch_traffic_data.py": "python",
    META_FILENAME: "json",
}

CHUNK_SIZE = 18
CHUNK_DELAY_SEC = 0.035


class SkillBuildVisualizer:
    """Emit granular skill-build events while writing a real package."""

    def __init__(self, builder: SkillPackageBuilder) -> None:
        self._builder = builder

    async def upsert_with_visualization(
        self,
        *,
        record: SkillRecord,
        session: Session,
        upsert_action: str,
        diff_changes: list[str],
        emitter: ExecutionEmitter,
    ) -> SkillUpsertResult:
        """Render, stream, and persist a skill package."""
        new_files = self._builder.build_file_contents(record, session)
        old_files = self._builder.read_package_files(record) if upsert_action == "update" else {}
        is_update = upsert_action == "update" and bool(old_files)

        await emitter.emit_skill_build(
            "skill_build_start",
            "understanding",
            display_text="开始将本次诊断结论沉淀为可复用技能包。",
            progress=1,
            action=upsert_action,
            skill_id=record.skill_id,
            intersection=record.intersection,
            time_period_label=record.time_period_label,
            diff_changes=diff_changes,
            is_update=is_update,
        )

        await self._stage(
            emitter,
            "understanding",
            "正在整理本次拥堵诊断结论与治理建议……",
            f"已识别目标：{record.intersection} · {record.time_period_label}",
        )

        thought_lines = [
            f"路口：{record.intersection}（{record.inter_id}）\n",
            (
                f"时段：{record.time_period_label}，命中规则 "
                f"{', '.join(record.rule_ids) or '见 reference.md'}\n"
            ),
            f"建议公式：{record.suggestion_formula}\n",
        ]
        if diff_changes:
            thought_lines.append("本次为技能更新，将高亮展示变更内容。\n")
            for change in diff_changes:
                thought_lines.append(f"· {change}\n")
        else:
            thought_lines.append("将把诊断流程写入标准 Skills 目录，供下次自动命中。\n")

        await self._thought_stream(emitter, "understanding", thought_lines)

        await self._stage(
            emitter,
            "planning",
            "正在规划技能目录结构……",
            "目录：SKILL.md、reference.md、scripts/、skill.meta.json",
        )

        for rel in PACKAGE_FILE_PATHS:
            stage = FILE_STAGES[rel]
            language = FILE_LANGUAGE[rel]
            content = new_files[rel]
            old_content = old_files.get(rel, "")
            has_diff = is_update and old_content and old_content != content

            await emitter.emit_skill_build(
                "stage_start",
                stage,
                display_text=f"正在编写 {Path(rel).name}……",
                progress=STAGE_PROGRESS[stage] - 6,
            )

            if has_diff:
                line_diff = compute_line_diff(old_content, content)
                changed_count = sum(1 for line in line_diff if line["kind"] != "same")
                await emitter.emit_skill_build(
                    "file_diff",
                    stage,
                    path=rel,
                    language=language,
                    lines=line_diff,
                    display_text=f"{Path(rel).name} 有 {changed_count} 处变更",
                )

            await emitter.emit_skill_build(
                "file_created",
                stage,
                path=rel,
                language=language,
                is_update=has_diff,
                display_text=f"创建 {Path(rel).name}",
            )

            accumulated = ""
            for chunk in _typing_chunks(content):
                accumulated += chunk
                await emitter.emit_skill_build(
                    "file_delta",
                    stage,
                    path=rel,
                    language=language,
                    delta=chunk,
                    display_text=f"正在写入 {Path(rel).name}……",
                )
                await asyncio.sleep(CHUNK_DELAY_SEC)

            self._builder.write_file(record, rel, accumulated)

            await emitter.emit_skill_build(
                "file_done",
                stage,
                path=rel,
                display_text=f"{Path(rel).name} 已落盘",
            )
            await emitter.emit_skill_build(
                "stage_done",
                stage,
                display_text=f"{Path(rel).name} 编写完成",
                progress=STAGE_PROGRESS[stage],
            )

        await self._stage(
            emitter,
            "packaging",
            "正在打包技能产物……",
            "技能包已就绪，可下载使用",
        )

        download_url = f"/api/v1/skills/{record.skill_id}/download"
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

        logger.info(
            "skill.build_visualized skill_id=%s action=%s dir=%s",
            record.skill_id,
            upsert_action,
            record.skill_dir,
        )
        return SkillUpsertResult(record=record, action=upsert_action)

    async def _stage(
        self,
        emitter: ExecutionEmitter,
        stage: str,
        start_text: str,
        done_text: str,
    ) -> None:
        await emitter.emit_skill_build(
            "stage_start",
            stage,
            display_text=start_text,
            progress=max(STAGE_PROGRESS.get(stage, 0) - 4, 1),
        )
        await asyncio.sleep(0.08)
        await emitter.emit_skill_build(
            "stage_done",
            stage,
            display_text=done_text,
            progress=STAGE_PROGRESS.get(stage, 0),
        )

    async def _thought_stream(
        self,
        emitter: ExecutionEmitter,
        stage: str,
        deltas: list[str],
    ) -> None:
        await emitter.emit_skill_build(
            "model_call_start",
            stage,
            display_text="正在组织技能沉淀思路……",
        )
        for piece in deltas:
            for chunk in _text_pieces(piece, size=10):
                await emitter.emit_skill_build(
                    "thought_delta",
                    stage,
                    delta=chunk,
                    display_text="正在形成可展示的思考摘要……",
                )
                await asyncio.sleep(0.05)
        await emitter.emit_skill_build(
            "model_call_done",
            stage,
            display_text="思路整理完成，开始编写文件。",
        )


def compute_line_diff(old: str, new: str) -> list[dict[str, Any]]:
    """Line-level diff for frontend highlighting."""
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    result: list[dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset, line in enumerate(old_lines[i1:i2]):
                result.append({"kind": "same", "line_no": j1 + offset + 1, "text": line})
        elif tag == "delete":
            for offset, line in enumerate(old_lines[i1:i2]):
                result.append({"kind": "removed", "line_no": i1 + offset + 1, "text": line})
        elif tag == "insert":
            for offset, line in enumerate(new_lines[j1:j2]):
                result.append({"kind": "added", "line_no": j1 + offset + 1, "text": line})
        elif tag == "replace":
            for offset, line in enumerate(old_lines[i1:i2]):
                result.append({"kind": "removed", "line_no": i1 + offset + 1, "text": line})
            for offset, line in enumerate(new_lines[j1:j2]):
                result.append({"kind": "added", "line_no": j1 + offset + 1, "text": line})
    return result


def _text_pieces(text: str, size: int) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)] or [text]


def _typing_chunks(content: str) -> list[str]:
    chunks: list[str] = []
    for line in content.splitlines(keepends=True):
        if not line.strip():
            chunks.append(line)
            continue
        chunks.extend(_text_pieces(line, size=CHUNK_SIZE))
    return chunks or [content]
