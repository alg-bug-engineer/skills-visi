"""路口治理案例显式落盘（data/cases/），仅在生成并固化治理方案后写入。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, Field

from intersection_agent.config import get_settings
from intersection_agent.models.experience import (
    CognitionEntry,
    DiagnosisEntry,
    _now,
)

_SAFE = re.compile(r"\W+", re.UNICODE)


class IntersectionCaseRecord(BaseModel):
    """单条路口治理案例（与一次 skill 固化对应）。"""

    skill_id: str
    inter_id: str
    intersection: str = ""
    time_period_label: str = ""
    suggestion_narrative: str
    suggestion_formula: str = ""
    solution_measure: str | None = None
    qualitative: str | None = None
    cognition: list[CognitionEntry] = Field(default_factory=list)
    diagnosis: list[DiagnosisEntry] = Field(default_factory=list)
    ts: str = Field(default_factory=_now)


class IntersectionCaseStore:
    """读-写 data/cases/{skill_id}.json。"""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        if base_dir is None:
            base_dir = get_settings().intersection_case_dir_path
        self._base = Path(base_dir)

    def _path(self, skill_id: str) -> Path:
        safe = _SAFE.sub("_", skill_id) or "_"
        return self._base / f"{safe}.json"

    def save(self, record: IntersectionCaseRecord) -> None:
        if not record.suggestion_narrative.strip():
            raise ValueError("路口案例须包含已生成的治理方案")
        self._base.mkdir(parents=True, exist_ok=True)
        path = self._path(record.skill_id)
        with open(path, "w", encoding="utf-8") as f:
            f.write(record.model_dump_json(indent=2))

    def load_all(self) -> list[IntersectionCaseRecord]:
        if not self._base.is_dir():
            return []
        records: list[IntersectionCaseRecord] = []
        for path in sorted(self._base.glob("*.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    records.append(IntersectionCaseRecord.model_validate(json.load(f)))
            except (json.JSONDecodeError, OSError, ValueError):
                continue
        return records
