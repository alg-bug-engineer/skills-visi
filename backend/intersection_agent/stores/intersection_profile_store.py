"""路口认知档案的文件级持久化（每路口一个 JSON）。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from intersection_agent.config import get_settings
from intersection_agent.models.experience import (
    CognitionEntry,
    CognitionStatus,
    DiagnosisEntry,
    IntersectionProfile,
    SolutionRef,
)

_SAFE = re.compile(r"\W+", re.UNICODE)


class IntersectionProfileStore:
    """读-改-写的路口三级经验档案仓库。"""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        if base_dir is None:
            base_dir = get_settings().profile_dir_path
        self._base = Path(base_dir)

    def _path(self, inter_id: str) -> Path:
        safe = _SAFE.sub("_", inter_id) or "_"
        return self._base / f"{safe}.json"

    def load(self, inter_id: str) -> IntersectionProfile:
        """加载档案；缺失返回空档案。"""
        path = self._path(inter_id)
        if not path.exists():
            return IntersectionProfile(inter_id=inter_id)
        with open(path, encoding="utf-8") as f:
            return IntersectionProfile.model_validate(json.load(f))

    def _save(self, profile: IntersectionProfile) -> None:
        self._base.mkdir(parents=True, exist_ok=True)
        path = self._path(profile.inter_id)
        with open(path, "w", encoding="utf-8") as f:
            f.write(profile.model_dump_json(indent=2))

    def add_cognition(
        self,
        inter_id: str,
        *,
        text: str,
        status: CognitionStatus = "manual",
        source: str = "data",
        evidence: dict[str, Any] | None = None,
    ) -> IntersectionProfile:
        profile = self.load(inter_id)
        profile.cognition.append(
            CognitionEntry(
                text=text, status=status, source=source, evidence=evidence or {}
            )
        )
        self._save(profile)
        return profile

    def add_diagnosis(
        self,
        inter_id: str,
        *,
        cause: str,
        dimension: str,
        scope: str | None = None,
        source: str = "data",
        confidence: float = 0.0,
    ) -> IntersectionProfile:
        profile = self.load(inter_id)
        profile.diagnosis.append(
            DiagnosisEntry(
                cause=cause,
                dimension=dimension,
                scope=scope,
                source=source,
                confidence=confidence,
            )
        )
        self._save(profile)
        return profile

    def add_solution_ref(
        self,
        inter_id: str,
        *,
        skill_id: str,
        qualitative: str | None = None,
        quantified: str | None = None,
    ) -> IntersectionProfile:
        profile = self.load(inter_id)
        profile.solution_ref.append(
            SolutionRef(
                skill_id=skill_id, qualitative=qualitative, quantified=quantified
            )
        )
        self._save(profile)
        return profile
