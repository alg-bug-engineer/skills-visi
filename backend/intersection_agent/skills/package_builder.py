"""Build and load standard Agent Skill packages (SKILL.md + scripts + reference)."""

from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from intersection_agent.models.domain import Session
from intersection_agent.models.skill import DEFAULT_PROBLEM_TYPE, SkillRecord

logger = logging.getLogger(__name__)

META_FILENAME = "skill.meta.json"
SKILL_FILENAME = "SKILL.md"
REFERENCE_FILENAME = "reference.md"

PACKAGE_FILE_PATHS = (
    SKILL_FILENAME,
    REFERENCE_FILENAME,
    "scripts/fetch_traffic_data.sql",
    "scripts/fetch_traffic_data.py",
    META_FILENAME,
)

TIME_LABEL_SLUG = {
    "早高峰": "morning-peak",
    "午高峰": "noon-peak",
    "晚高峰": "evening-peak",
    "平峰": "off-peak",
    "夜间": "night",
}


@dataclass
class SkillPackage:
    """Resolved skill package on disk."""

    record: SkillRecord
    root: Path


class SkillPackageBuilder:
    """Write/read Cursor-compatible skill directories under data/skills/."""

    def __init__(self, skills_root: Path) -> None:
        self._root = skills_root
        self._root.mkdir(parents=True, exist_ok=True)

    def build_file_contents(
        self, record: SkillRecord, session: Session | None = None
    ) -> dict[str, str]:
        """Render all package files in memory (paths relative to package root)."""
        matched_rules = _matched_rules(session)
        return {
            SKILL_FILENAME: _render_skill_md(record, matched_rules),
            REFERENCE_FILENAME: _render_reference_md(record, matched_rules, session),
            "scripts/fetch_traffic_data.sql": _render_fetch_sql(record),
            "scripts/fetch_traffic_data.py": _render_fetch_py(record),
            META_FILENAME: json.dumps(asdict(record), ensure_ascii=False, indent=2),
        }

    def read_package_files(self, record: SkillRecord) -> dict[str, str]:
        """Read existing package files from disk."""
        pkg_dir = self._root / record.skill_dir
        if not pkg_dir.is_dir():
            return {}
        contents: dict[str, str] = {}
        for rel in PACKAGE_FILE_PATHS:
            path = pkg_dir / rel
            if path.is_file():
                contents[rel] = path.read_text(encoding="utf-8")
        return contents

    def write_package_files(
        self,
        record: SkillRecord,
        files: dict[str, str],
        *,
        session: Session | None = None,
    ) -> Path:
        """Write pre-rendered package files to disk."""
        pkg_dir = self._root / record.skill_dir
        scripts_dir = pkg_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        for rel, content in files.items():
            target = pkg_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        logger.info("skill.package_written dir=%s", pkg_dir)
        return pkg_dir

    def write_package(self, record: SkillRecord, session: Session | None = None) -> Path:
        """Create or overwrite a full skill package directory."""
        files = self.build_file_contents(record, session)
        return self.write_package_files(record, files, session=session)

    def package_zip(self, record: SkillRecord) -> bytes:
        """Zip skill package directory for download."""
        pkg_dir = self._root / record.skill_dir
        if not pkg_dir.is_dir():
            raise FileNotFoundError(f"Skill package not found: {record.skill_dir}")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(pkg_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(pkg_dir).as_posix())
        return buffer.getvalue()

    def load_all(self) -> list[SkillRecord]:
        """Scan skill root for valid packages."""
        records: list[SkillRecord] = []
        if not self._root.is_dir():
            return records

        for entry in sorted(self._root.iterdir()):
            if not entry.is_dir() or entry.name.startswith(("_", ".")):
                continue
            record = self.load_from_dir(entry)
            if record:
                records.append(record)

        records.sort(key=lambda r: r.created_at, reverse=True)
        return records

    def load_by_id(self, skill_id: str) -> SkillRecord | None:
        """Find skill by skill_id across packages."""
        for record in self.load_all():
            if record.skill_id == skill_id:
                return record
        return None

    def load_from_dir(self, pkg_dir: Path) -> SkillRecord | None:
        """Load skill record from package directory."""
        meta_path = pkg_dir / META_FILENAME
        if meta_path.is_file():
            return _record_from_meta(meta_path, pkg_dir)

        skill_md = pkg_dir / SKILL_FILENAME
        if skill_md.is_file():
            return _record_from_skill_md(skill_md, pkg_dir)

        return None

    def package_path(self, record: SkillRecord) -> Path:
        """Absolute path to skill package directory."""
        return self._root / record.skill_dir

    def write_file(self, record: SkillRecord, relative_path: str, content: str) -> None:
        """Write a single file inside the skill package."""
        target = self.package_path(record) / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _matched_rules(session: Session | None) -> list[dict[str, Any]]:
    if session and session.diagnosis and session.diagnosis.matched_rules:
        return session.diagnosis.matched_rules
    return []


def skill_dir_name(inter_id: str, problem_type: str, time_period_label: str) -> str:
    """Directory slug for a skill package (lowercase, hyphens)."""
    period_slug = TIME_LABEL_SLUG.get(time_period_label) or _slugify(time_period_label)
    safe_inter = re.sub(r"[^\w\-]+", "-", inter_id).strip("-").lower()
    return f"{problem_type}-{safe_inter}-{period_slug}"


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\-]+", "-", text.strip()).strip("-").lower()
    return slug or "unknown"


def _record_from_meta(meta_path: Path, pkg_dir: Path) -> SkillRecord:
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    return SkillRecord(
        skill_id=data["skill_id"],
        skill_dir=pkg_dir.name,
        intersection=data["intersection"],
        inter_id=data["inter_id"],
        problem_type=data.get("problem_type", DEFAULT_PROBLEM_TYPE),
        time_period_label=data["time_period_label"],
        match_keywords=list(data.get("match_keywords") or []),
        data_query_spec=dict(data.get("data_query_spec") or {}),
        rule_ids=list(data.get("rule_ids") or []),
        suggestion_formula=data["suggestion_formula"],
        created_at=data["created_at"],
        updated_at=data.get("updated_at"),
        user_constraints=data.get("user_constraints"),
        quantitative_constraints=data.get("quantitative_constraints"),
        tags=data.get("tags"),
    )


def _record_from_skill_md(skill_md: Path, pkg_dir: Path) -> SkillRecord | None:
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    front = yaml.safe_load(parts[1]) or {}
    if not isinstance(front, dict):
        return None
    skill_id = front.get("skill_id") or front.get("name")
    if not skill_id:
        return None
    return SkillRecord(
        skill_id=str(skill_id),
        skill_dir=pkg_dir.name,
        intersection=str(front.get("intersection", "")),
        inter_id=str(front.get("inter_id", "")),
        problem_type=str(front.get("problem_type", DEFAULT_PROBLEM_TYPE)),
        time_period_label=str(front.get("time_period_label", "")),
        match_keywords=list(front.get("match_keywords") or []),
        data_query_spec=dict(front.get("data_query_spec") or {}),
        rule_ids=list(front.get("rule_ids") or []),
        suggestion_formula=str(front.get("suggestion_formula", "")),
        created_at=str(front.get("created_at", "")),
        updated_at=front.get("updated_at"),
        user_constraints=front.get("user_constraints"),
    )


def _render_skill_md(record: SkillRecord, matched_rules: list[dict[str, Any]]) -> str:
    rule_names = [r.get("name", r.get("id", "")) for r in matched_rules]
    conclusion = matched_rules[0].get("conclusion", "") if matched_rules else ""
    keywords_yaml = yaml.dump(
        record.match_keywords,
        allow_unicode=True,
        default_flow_style=True,
    ).strip()
    rule_ids_yaml = yaml.dump(record.rule_ids, default_flow_style=True).strip()

    description = (
        f"对「{record.intersection}」在{record.time_period_label}进行拥堵诊断。"
        f"当用户提到该路口及时段拥堵时使用。"
        f"命中规则：{', '.join(rule_names) or '见 reference.md'}。"
    )

    return f"""---
name: {record.skill_dir}
description: {description}
skill_id: {record.skill_id}
intersection: {record.intersection}
inter_id: {record.inter_id}
problem_type: {record.problem_type}
time_period_label: {record.time_period_label}
match_keywords: {keywords_yaml}
rule_ids: {rule_ids_yaml}
suggestion_formula: "{record.suggestion_formula}"
user_constraints: {json.dumps(record.user_constraints, ensure_ascii=False)}
created_at: {record.created_at}
updated_at: {record.updated_at or record.created_at}
---

# {record.intersection} · {record.time_period_label}拥堵诊断

## 适用场景

- 路口：{record.intersection}（`{record.inter_id}`）
- 时段：{record.time_period_label}
- 问题类型：拥堵诊断（固定）
- 匹配关键词：{", ".join(record.match_keywords) or "无"}
- 用户约束/建议：{record.user_constraints or "无"}
- 量化约束：{json.dumps(record.quantitative_constraints, ensure_ascii=False) if record.quantitative_constraints else "无"}

## 执行流程

1. **获取运行数据**（方案 D：近 7 日 DWD，无数据时 DWS 降级）

   ```bash
   cd "$(dirname "$0")/.."
   python scripts/fetch_traffic_data.py
   ```

2. **应用诊断规则** — 见 [reference.md](reference.md) 中固化的规则 ID 与结论

3. **生成治理建议** — 使用公式：

   ```
   {record.suggestion_formula}
   ```

   若用户约束/建议不为空，治理建议必须优先体现：{record.user_constraints or "无"}。

## 诊断结论（固化快照）

{conclusion or "见 reference.md"}

## 附加资源

- [reference.md](reference.md) — 规则条件、结论与数据窗口说明
- [scripts/fetch_traffic_data.sql](scripts/fetch_traffic_data.sql) — PostgreSQL 查询脚本
- [scripts/fetch_traffic_data.py](scripts/fetch_traffic_data.py) — 可执行查数脚本
"""


def _render_reference_md(
    record: SkillRecord,
    matched_rules: list[dict[str, Any]],
    session: Session | None,
) -> str:
    spec = record.data_query_spec
    window = spec.get("data_window") or {}
    tp = spec.get("time_period") or {}

    lines = [
        f"# {record.intersection} · 诊断参考",
        "",
        "## 数据查询规格",
        "",
        f"- 路口 ID：`{record.inter_id}`",
        f"- 时段：{record.time_period_label}（{tp.get('start', '?')}-{tp.get('end', '?')}）",
        "",
    ]

    if window:
        lines.extend(
            [
                "### 时间窗（方案 D）",
                "",
                f"- 类型：`{window.get('type', 'rolling_7d')}`",
                f"- 日期范围：{window.get('date_from')} ~ {window.get('date_to')}",
                f"- 时段切片：{window.get('time_slot', '')}",
                f"- 星期过滤：{window.get('dow_filter', [])}",
                f"- 数据源层级：`{window.get('source_tier', 'unknown')}`",
                "",
            ]
        )

    lines.extend(["## 固化规则", ""])
    if matched_rules:
        for rule in matched_rules:
            lines.append(f"### {rule.get('id', 'rule')}")
            lines.append("")
            lines.append(f"- 名称：{rule.get('name', '')}")
            lines.append(f"- 结论：{rule.get('conclusion', '')}")
            action = rule.get("action") or {}
            lines.append(f"- 建议类型：{action.get('type', '')}")
            lines.append(f"- 公式：`{action.get('formula', record.suggestion_formula)}`")
            lines.append("")
    else:
        for rid in record.rule_ids:
            lines.append(f"- `{rid}`")
        lines.append("")

    if session and session.suggestion:
        lines.extend(
            [
                "## 固化建议快照",
                "",
                session.suggestion.narrative,
                "",
            ]
        )

    if record.user_constraints:
        lines.extend(
            [
                "## 用户约束/建议沉淀重点",
                "",
                record.user_constraints,
                "",
                "后续生成治理建议时必须优先体现该约束，避免建议只给出单方向绿灯调整。",
                "",
            ]
        )

    lines.extend(
        [
            "## 建议计算公式",
            "",
            "```",
            record.suggestion_formula,
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _render_fetch_sql(record: SkillRecord) -> str:
    spec = record.data_query_spec
    inter_id = spec.get("inter_id") or record.inter_id
    tp = spec.get("time_period") or {}
    window = spec.get("data_window") or {}
    slot_start = tp.get("start", "16:00")
    slot_end = tp.get("end", "18:00")
    date_from = window.get("date_from", "CURRENT_DATE - 6")
    date_to = window.get("date_to", "CURRENT_DATE")
    dow = window.get("dow_filter") or [1, 2, 3, 4, 5]

    return f"""-- {record.intersection} · {record.time_period_label} 拥堵诊断查数脚本
-- 方案 D：优先 DWD 近 7 日滚动窗口，无样本时改用 DWS + primary_dow
-- 参数：inter_id = '{inter_id}'

-- 1) DWD 延误指数（主路径）
SELECT AVG(delay_index) AS delay_index,
       COUNT(*)::int AS sample_count
FROM xianchang.dwd_tfc_inter_dir_perf_5min
WHERE inter_id = '{inter_id}' AND is_deleted = 0
  AND stat_time::date BETWEEN '{date_from}' AND '{date_to}'
  AND stat_time::time >= '{slot_start}' AND stat_time::time < '{slot_end}'
  AND EXTRACT(ISODOW FROM stat_time)::int = ANY(ARRAY{dow});

-- 2) DWS 评估（DWD 无数据时降级，按提问日星期几过滤）
-- SELECT AVG(saturation_max) AS saturation_max,
--        AVG(unbalance_index) AS imbalance_index
-- FROM xianchang.dws_inter_evaluation_5min_mm
-- WHERE inter_id = '{inter_id}'
--   AND day_of_week = EXTRACT(ISODOW FROM CURRENT_DATE)::int
--   AND step_index BETWEEN ...;

-- 3) 信号配时概况
SELECT AVG(p.cycle_len_sec) AS cycle_length,
       AVG(t.green_sec::float / NULLIF(p.cycle_len_sec, 0)) AS green_ratio
FROM xianchang.dwd_ctl_inter_plan_cfg p
JOIN xianchang.dwd_ctl_inter_plan_stage_timing t
  ON p.inter_id = t.inter_id AND p.plan_no = t.plan_no
WHERE p.inter_id = '{inter_id}' AND p.is_deleted = 0 AND t.is_deleted = 0;
"""


def _render_fetch_py(record: SkillRecord) -> str:
    spec = record.data_query_spec
    inter_id = spec.get("inter_id") or record.inter_id
    tp = spec.get("time_period") or {}
    window = spec.get("data_window") or {}

    return f'''#!/usr/bin/env python3
"""Fetch traffic metrics for skill: {record.skill_id}

Usage (from skill package root):
    python scripts/fetch_traffic_data.py

Requires backend/.env with PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

# Resolve backend root (…/backend) for .env and imports
BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv

load_dotenv(BACKEND_ROOT / ".env")

INTER_ID = "{inter_id}"
TIME_PERIOD = {json.dumps(tp, ensure_ascii=False)}
DATA_WINDOW = {json.dumps(window, ensure_ascii=False)}


async def main() -> None:
    import asyncpg

    conn = await asyncpg.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=int(os.environ.get("PGPORT", "5432")),
        user=os.environ.get("PGUSER", ""),
        password=os.environ.get("PGPASSWORD", ""),
        database=os.environ.get("PGDATABASE", ""),
    )
    try:
        flow_schema = os.environ.get("PG_FLOW_SCHEMA", "xianchang")
        date_from = date.fromisoformat(DATA_WINDOW.get("date_from", date.today().isoformat()))
        date_to = date.fromisoformat(DATA_WINDOW.get("date_to", date.today().isoformat()))
        slot_start = TIME_PERIOD.get("start", "16:00")
        slot_end = TIME_PERIOD.get("end", "18:00")
        dow = DATA_WINDOW.get("dow_filter") or [1, 2, 3, 4, 5]

        row = await conn.fetchrow(
            f"""
            SELECT AVG(delay_index) AS delay_index,
                   COUNT(*)::int AS sample_count
            FROM {{flow_schema}}.dwd_tfc_inter_dir_perf_5min
            WHERE inter_id = $1 AND is_deleted = 0
              AND stat_time::date BETWEEN $2 AND $3
              AND stat_time::time >= $4::time AND stat_time::time < $5::time
              AND EXTRACT(ISODOW FROM stat_time)::int = ANY($6::int[])
            """,
            INTER_ID,
            date_from,
            date_to,
            slot_start,
            slot_end,
            dow,
        )
        print(json.dumps({{"dwd": dict(row) if row else None}}, ensure_ascii=False, indent=2))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
'''
