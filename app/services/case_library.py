from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.services.case_tag_extractor import CaseTagExtractor

logger = logging.getLogger(__name__)

OVERFLOW_KEYWORDS = ("溢出", "溢流", "排队溢出", "反堵", "回溢")


def _extract_similarity_points(case: dict[str, Any], matched_dims: list[dict[str, str]]) -> list[str]:
    if matched_dims:
        return [d["label"] for d in matched_dims[:4]]
    points: list[str] = []
    text = (
        f"{case.get('案例场景', '') or case.get('scene', '')} "
        f"{case.get('交通问题诊断', '') or case.get('diagnosis', '')}"
    )
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


def _transferable_actions(case: dict[str, Any], case_tags: dict[str, list[str]]) -> list[str]:
    strategy_values = case_tags.get("strategy_actions") or []
    extractor = CaseTagExtractor()
    dim_spec = extractor._dimensions.get("strategy_actions") or {}
    actions: list[str] = []
    for value_key in strategy_values:
        label = (dim_spec.get(value_key) or {}).get("label")
        if label and label not in actions:
            actions.append(label)
    if actions:
        return actions[:3]

    solution = (case.get("治理方案") or case.get("solution") or "").strip()
    if not solution:
        return []
    fallback: list[str] = []
    for kw, label in (
        ("截流", "上游截流节奏控制"),
        ("协调", "上下游协调配时"),
        ("绿波", "干线绿波协调"),
        ("防溢流", "防溢流相位保护"),
        ("增绿", "局部增绿（需核下游）"),
    ):
        if kw in solution and label not in fallback:
            fallback.append(label)
    if not fallback:
        fallback.append(solution[:60])
    return fallback[:3]


def _caveats(case: dict[str, Any], case_type: str, case_tags: dict[str, list[str]]) -> list[str]:
    caveats: list[str] = []
    scope = case_tags.get("scope_type") or []
    if "arterial_coordination" in scope:
        caveats.append("干线协调方案需核对本路段路口间距与周期统一条件")
    if "point_intersection" in scope:
        caveats.append("单点渠化/相位方案不宜直接套用于多路口协调场景")
    if case_type == "risk":
        caveats.append("下游承接不足时不宜单点照搬加绿")
    caveats.append("需核对本路口配时结构与下游拓扑")
    return list(dict.fromkeys(caveats))[:3]


def _help_summary(case: dict[str, Any], case_type: str, matched_dims: list[dict[str, str]]) -> str:
    if matched_dims:
        top = matched_dims[0]["label"]
        return f"与本场景在{top}上相近，可对照历史处置路径"
    if case_type == "risk":
        return "提示下游约束与防溢流做法，避免重复单点加压"
    effect = (case.get("预期效果") or case.get("effect") or "").strip()
    if effect:
        return f"可借鉴处置路径：{effect[:80]}"
    return "可借鉴历史协调/截流思路，结合本路口指标微调"


def _extract_lesson(case: dict[str, Any], case_type: str) -> str:
    if case_type == "risk":
        return "下游接不住时，不宜单点激进放行"
    effect = case.get("预期效果") or case.get("effect") or ""
    if effect:
        return effect[:120]
    return "上游控流+目标小步释放+下游保护后，外溢风险更可控"


class CaseLibraryService:
    def __init__(
        self,
        library_path: Path,
        tag_extractor: CaseTagExtractor | None = None,
        structured_industry_path: Path | None = None,
    ) -> None:
        self.library_path = library_path
        self.structured_industry_path = structured_industry_path
        self.tag_extractor = tag_extractor or CaseTagExtractor()
        self._cases: list[dict[str, Any]] | None = None
        self._tag_cache: dict[int, dict[str, list[str]]] = {}
        self._from_structured = False

    def build_query_profile(
        self,
        ticket: dict[str, Any] | None = None,
        diagnosis: dict[str, Any] | None = None,
    ) -> dict[str, list[str]]:
        return self.tag_extractor.build_query_profile(ticket, diagnosis)

    def _load(self) -> list[dict[str, Any]]:
        if self._cases is not None:
            return self._cases

        structured = self.structured_industry_path
        if structured is not None and structured.exists():
            cases: list[dict[str, Any]] = []
            with structured.open(encoding="utf-8") as f:
                for line_no, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        cases.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        logger.warning("结构化行业案例第 %d 行解析失败: %s", line_no, exc)
            if cases:
                self._cases = cases
                self._from_structured = True
                logger.info(
                    "案例库从结构化沉淀加载 path=%s count=%d",
                    structured,
                    len(cases),
                )
                return self._cases

        if not self.library_path.exists():
            logger.warning("案例库文件不存在: %s", self.library_path)
            self._cases = []
            return self._cases

        cases = []
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
        self._from_structured = False
        logger.info("案例库加载完成 path=%s count=%d", self.library_path, len(cases))
        return self._cases

    def _case_tags(self, case: dict[str, Any], index: int) -> dict[str, list[str]]:
        if index not in self._tag_cache:
            precomputed = case.get("tag_keys")
            if isinstance(precomputed, dict) and precomputed:
                self._tag_cache[index] = {
                    k: list(v) for k, v in precomputed.items() if isinstance(v, list)
                }
            else:
                self._tag_cache[index] = self.tag_extractor.extract_tags(case)
        return self._tag_cache[index]

    def _score_case(
        self,
        case: dict[str, Any],
        index: int,
        *,
        problem_type: str,
        query_profile: dict[str, list[str]] | None,
    ) -> tuple[float, list[dict[str, str]], dict[str, float]]:
        tags = self._case_tags(case, index)
        score, matched_dims, dim_scores = self.tag_extractor.score_match(
            tags,
            query_profile,
            problem_type=problem_type,
        )
        if score <= 0:
            text = self.tag_extractor.case_text(case)
            legacy = 0.0
            if problem_type and problem_type in text:
                legacy += 2.0
            for kw in OVERFLOW_KEYWORDS:
                if kw in text:
                    legacy += 1.0
            if legacy > 0:
                score = legacy
                if not matched_dims:
                    matched_dims = [{"key": "legacy", "label": "关键词匹配"}]
        return score, matched_dims, dim_scores

    def search_similar(
        self,
        problem_type: str = "",
        limit: int = 5,
        query_profile: dict[str, list[str]] | None = None,
    ) -> list[dict[str, Any]]:
        cases = self._load()
        scored: list[tuple[float, dict[str, Any], list[dict[str, str]]]] = []

        for index, case in enumerate(cases):
            score, matched_dims, _ = self._score_case(
                case,
                index,
                problem_type=problem_type,
                query_profile=query_profile,
            )
            if score > 0:
                scored.append((score, case, matched_dims))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, case, matched_dims in scored[:limit]:
            case_index = next(i for i, c in enumerate(cases) if c is case)
            tags = self._case_tags(case, case_index)
            results.append(
                {
                    "score": score,
                    "scene": (case.get("案例场景") or case.get("scene") or "")[:200],
                    "diagnosis": (case.get("交通问题诊断") or case.get("diagnosis") or "")[:200],
                    "solution": (case.get("治理方案") or case.get("solution") or "")[:200],
                    "effect": (case.get("预期效果") or case.get("effect") or "")[:150],
                    "structured_tags": case.get("structured_tags")
                    or self.tag_extractor.tags_to_labels(tags),
                    "similarity_dimensions": matched_dims[:5],
                }
            )
        return results

    def search_case_cards(
        self,
        problem_type: str = "",
        limit: int = 6,
        query_profile: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        cases = self._load()
        scored: list[tuple[float, dict[str, Any], list[dict[str, str]], dict[str, float], int]] = []

        for index, case in enumerate(cases):
            score, matched_dims, dim_scores = self._score_case(
                case,
                index,
                problem_type=problem_type,
                query_profile=query_profile,
            )
            if score > 0:
                scored.append((score, case, matched_dims, dim_scores, index))

        scored.sort(key=lambda x: x[0], reverse=True)
        high_similarity = [
            item for item in scored if self.tag_extractor.is_high_similarity(item[0])
        ]
        cards = []
        labels = "ABCDEF"
        for idx, (score, case, matched_dims, dim_scores, case_index) in enumerate(scored[:3]):
            solution = case.get("治理方案") or case.get("solution") or ""
            effect = case.get("预期效果") or case.get("effect") or ""
            tags = self._case_tags(case, case_index)
            title = case.get("案例场景") or case.get("title") or case.get("scene") or ""
            case_type = (
                "risk"
                if any(k in solution for k in ("单点", "加绿", "增绿"))
                else "recommended"
            )
            labels_map = case.get("structured_tags") or self.tag_extractor.tags_to_labels(tags)
            cards.append(
                {
                    "case_id": labels[idx] if idx < len(labels) else str(idx),
                    "title": title[:80],
                    "similarity_points": _extract_similarity_points(case, matched_dims),
                    "similarity_dimensions": matched_dims[:5]
                    or [{"key": "scene", "label": "场景特征相似"}],
                    "structured_tags": labels_map,
                    "transferable_actions": _transferable_actions(case, tags),
                    "caveats": _caveats(case, case_type, tags),
                    "help_summary": _help_summary(case, case_type, matched_dims),
                    "similarity_tier": (
                        "high" if self.tag_extractor.is_high_similarity(score) else "matched"
                    ),
                    "historical_action": solution[:120],
                    "outcome": effect[:120] or "效果待回填",
                    "lesson": _extract_lesson(case, case_type),
                    "case_type": case_type,
                    "score": score,
                    "dimension_scores": dim_scores,
                }
            )
        return {
            "matched_count": len(scored),
            "high_similarity_count": len(high_similarity),
            "cards": cards,
            "query_profile": query_profile or {},
        }

    def count(self) -> int:
        return len(self._load())
