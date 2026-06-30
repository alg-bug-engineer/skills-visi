"""路口认知档案的文件级持久化（每路口一个 JSON）。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

AbsorptionOutcome = Literal["inserted", "exists", "updated"]

from intersection_agent.config import get_settings
from intersection_agent.models.experience import (
    CognitionEntry,
    CognitionStatus,
    DiagnosisEntry,
    IntersectionProfile,
    SolutionRef,
    _now,
)

_SAFE = re.compile(r"\W+", re.UNICODE)
_PUNCT = re.compile(r"[\s，。、；;,.!！?？:：·\-—_/\\()（）\[\]【】\"'“”‘’]+", re.UNICODE)

# 认知状态优先级：去重时高状态覆盖低状态（数据验证升级）。
_STATUS_RANK: dict[str, int] = {"verified": 2, "data_doubt": 1, "manual": 0}


def _norm(text: str | None) -> str:
    """归一化文本：去空白/标点、转小写，用于路口内同桶判重。"""
    if not text:
        return ""
    return _PUNCT.sub("", text).lower()


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

    def load_all(self) -> list[IntersectionProfile]:
        """扫描档案目录，返回全部路口认知档案（供经验库聚合）。"""
        if not self._base.is_dir():
            return []
        profiles: list[IntersectionProfile] = []
        for path in sorted(self._base.glob("*.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    profiles.append(IntersectionProfile.model_validate(json.load(f)))
            except (json.JSONDecodeError, OSError, ValueError):
                continue
        return profiles

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
    ) -> tuple[IntersectionProfile, AbsorptionOutcome]:
        profile = self.load(inter_id)
        key = _norm(text)
        existing = next((c for c in profile.cognition if _norm(c.text) == key), None)
        if existing is not None:
            # 数据验证升级：高状态覆盖低状态，evidence 非空覆盖空。
            changed = False
            if _STATUS_RANK.get(status, 0) > _STATUS_RANK.get(existing.status, 0):
                existing.status = status
                changed = True
            if evidence and not existing.evidence:
                existing.evidence = evidence
                changed = True
            existing.ts = _now()
            outcome: AbsorptionOutcome = "updated" if changed else "exists"
        else:
            profile.cognition.append(
                CognitionEntry(
                    text=text, status=status, source=source, evidence=evidence or {}
                )
            )
            outcome = "inserted"
        self._save(profile)
        return profile, outcome

    def add_diagnosis(
        self,
        inter_id: str,
        *,
        cause: str,
        dimension: str,
        scope: str | None = None,
        source: str = "data",
        confidence: float = 0.0,
    ) -> tuple[IntersectionProfile, AbsorptionOutcome]:
        profile = self.load(inter_id)
        key = (_norm(cause), dimension, _norm(scope))
        existing = next(
            (
                d
                for d in profile.diagnosis
                if (_norm(d.cause), d.dimension, _norm(d.scope)) == key
            ),
            None,
        )
        if existing is not None:
            # 保留高 confidence；data 来源优先于 user。
            changed = False
            if confidence > existing.confidence:
                existing.confidence = confidence
                changed = True
            if source == "data" and existing.source != "data":
                existing.source = source
                changed = True
            existing.ts = _now()
            outcome: AbsorptionOutcome = "updated" if changed else "exists"
        else:
            profile.diagnosis.append(
                DiagnosisEntry(
                    cause=cause,
                    dimension=dimension,
                    scope=scope,
                    source=source,
                    confidence=confidence,
                )
            )
            outcome = "inserted"
        self._save(profile)
        return profile, outcome

    def add_solution_ref(
        self,
        inter_id: str,
        *,
        skill_id: str,
        qualitative: str | None = None,
        quantified: str | None = None,
    ) -> tuple[IntersectionProfile, AbsorptionOutcome]:
        profile = self.load(inter_id)
        key = (skill_id, _norm(quantified))
        existing = next(
            (
                s
                for s in profile.solution_ref
                if (s.skill_id, _norm(s.quantified)) == key
            ),
            None,
        )
        if existing is not None:
            # 同方案以最新内容更新。
            changed = existing.qualitative != qualitative
            existing.qualitative = qualitative
            existing.quantified = quantified
            existing.ts = _now()
            outcome: AbsorptionOutcome = "updated" if changed else "exists"
        else:
            profile.solution_ref.append(
                SolutionRef(
                    skill_id=skill_id, qualitative=qualitative, quantified=quantified
                )
            )
            outcome = "inserted"
        self._save(profile)
        return profile, outcome
