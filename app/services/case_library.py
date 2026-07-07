from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OVERFLOW_KEYWORDS = ("溢出", "溢流", "排队溢出", "反堵", "回溢")


def _extract_similarity_points(case: dict[str, Any]) -> list[str]:
    points: list[str] = []
    text = f"{case.get('案例场景', '')} {case.get('交通问题诊断', '')}"
    mapping = {
        "晚高峰": "晚高峰短时段",
        "排队": "目标方向排队高",
        "下游": "下游节点高饱和",
        "上游": "上游来车冲击",
        "绿灯": "绿灯利用率高",
    }
    for key, label in mapping.items():
        if key in text and label not in points:
            points.append(label)
    return points[:4] or ["场景特征相似"]


def _extract_lesson(case: dict[str, Any], case_type: str) -> str:
    if case_type == "risk":
        return "下游接不住时，不宜单点激进放行"
    effect = case.get("预期效果", "")
    if effect:
        return effect[:120]
    return "上游控流+目标小步释放+下游保护后，外溢风险更可控"


class CaseLibraryService:
    def __init__(self, library_path: Path) -> None:
        self.library_path = library_path
        self._cases: list[dict[str, Any]] | None = None

    def _load(self) -> list[dict[str, Any]]:
        if self._cases is not None:
            return self._cases
        if not self.library_path.exists():
            logger.warning("案例库文件不存在: %s", self.library_path)
            self._cases = []
            return self._cases

        cases: list[dict[str, Any]] = []
        with self.library_path.open(encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    cases.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    logger.warning("案例库第 %d 行解析失败: %s", line_no, exc)
        self._cases = cases
        logger.info("案例库加载完成 path=%s count=%d", self.library_path, len(cases))
        return self._cases

    def search_similar(self, problem_type: str = "", limit: int = 5) -> list[dict[str, Any]]:
        cases = self._load()
        scored: list[tuple[float, dict[str, Any]]] = []

        for case in cases:
            scene = case.get("案例场景", "")
            diagnosis = case.get("交通问题诊断", "")
            text = f"{scene} {diagnosis}"
            score = 0.0
            if problem_type and problem_type in text:
                score += 2.0
            for kw in OVERFLOW_KEYWORDS:
                if kw in text:
                    score += 1.0
            if "下游" in text:
                score += 0.5
            if "上游" in text or "协调" in text:
                score += 0.5
            if score > 0:
                scored.append((score, case))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, case in scored[:limit]:
            results.append(
                {
                    "score": score,
                    "scene": case.get("案例场景", "")[:200],
                    "diagnosis": case.get("交通问题诊断", "")[:200],
                    "solution": case.get("治理方案", "")[:200],
                    "effect": case.get("预期效果", "")[:150],
                }
            )
        return results

    def search_case_cards(self, problem_type: str = "", limit: int = 6) -> dict[str, Any]:
        cases = self._load()
        scored: list[tuple[float, dict[str, Any]]] = []
        for case in cases:
            scene = case.get("案例场景", "")
            diagnosis = case.get("交通问题诊断", "")
            solution = case.get("治理方案", "")
            text = f"{scene} {diagnosis} {solution}"
            score = 0.0
            if problem_type and problem_type in text:
                score += 2.0
            for kw in OVERFLOW_KEYWORDS:
                if kw in text:
                    score += 1.0
            if "下游" in text:
                score += 0.5
            if "上游" in text or "协调" in text:
                score += 0.5
            if score > 0:
                scored.append((score, case))

        scored.sort(key=lambda x: x[0], reverse=True)
        high_similarity = [item for item in scored if item[0] >= 3.0]
        cards = []
        labels = "ABCDEF"
        for idx, (score, case) in enumerate(scored[:3]):
            solution = case.get("治理方案", "")
            effect = case.get("预期效果", "")
            case_type = "risk" if any(k in solution for k in ("单点", "加绿", "增绿")) else "recommended"
            cards.append(
                {
                    "case_id": labels[idx] if idx < len(labels) else str(idx),
                    "title": case.get("案例场景", "")[:80],
                    "similarity_points": _extract_similarity_points(case),
                    "historical_action": solution[:120],
                    "outcome": effect[:120] or "效果待回填",
                    "lesson": _extract_lesson(case, case_type),
                    "case_type": case_type,
                    "score": score,
                }
            )
        return {
            "matched_count": len(scored),
            "high_similarity_count": len(high_similarity),
            "cards": cards,
        }

    def count(self) -> int:
        return len(self._load())
