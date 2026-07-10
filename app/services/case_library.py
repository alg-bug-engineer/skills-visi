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


def _similarity_dimensions(case: dict[str, Any], problem_type: str, score: float) -> list[dict[str, str]]:
    scene = case.get("案例场景", "") or ""
    diagnosis = case.get("交通问题诊断", "") or ""
    solution = case.get("治理方案", "") or ""
    dims: list[dict[str, str]] = []
    if problem_type and problem_type in f"{scene} {diagnosis}":
        dims.append({"key": "problem", "label": f"问题形态：{problem_type}"})
    for kw, label in (
        ("晚高峰", "同时段：晚高峰"),
        ("早高峰", "同时段：早高峰"),
        ("下游", "空间：下游承接"),
        ("上游", "空间：上游来车"),
        ("排队", "指标：排队积压"),
        ("饱和", "指标：饱和偏高"),
    ):
        if kw in f"{scene} {diagnosis}":
            dims.append({"key": kw, "label": label})
    if solution.strip():
        dims.append({"key": "measure", "label": "措施：历史治理方案可对照"})
    if score >= 3.0:
        dims.append({"key": "tier", "label": "匹配：高度相似"})
    return dims[:5] or [{"key": "scene", "label": "场景特征相似"}]


def _transferable_actions(case: dict[str, Any]) -> list[str]:
    solution = (case.get("治理方案", "") or "").strip()
    if not solution:
        return []
    actions: list[str] = []
    for kw, label in (
        ("截流", "上游截流节奏控制"),
        ("协调", "上下游协调配时"),
        ("绿波", "干线绿波协调"),
        ("防溢流", "防溢流相位保护"),
        ("增绿", "局部增绿（需核下游）"),
    ):
        if kw in solution and label not in actions:
            actions.append(label)
    if not actions:
        actions.append(solution[:60])
    return actions[:3]


def _caveats(case: dict[str, Any], case_type: str) -> list[str]:
    if case_type == "risk":
        return ["下游承接不足时不宜单点照搬加绿", "需核对本路口转向结构与相位方案"]
    return ["需核对本路口配时结构与下游拓扑", "历史方案仅作参考，须结合实时指标"]


def _help_summary(case: dict[str, Any], case_type: str) -> str:
    if case_type == "risk":
        return "提示下游约束与防溢流做法，避免重复单点加压"
    effect = (case.get("预期效果", "") or "").strip()
    if effect:
        return f"可借鉴处置路径：{effect[:80]}"
    return "可借鉴历史协调/截流思路，结合本路口指标微调"


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
                    "similarity_dimensions": _similarity_dimensions(case, problem_type, score),
                    "transferable_actions": _transferable_actions(case),
                    "caveats": _caveats(case, case_type),
                    "help_summary": _help_summary(case, case_type),
                    "similarity_tier": "high" if score >= 3.0 else "matched",
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
