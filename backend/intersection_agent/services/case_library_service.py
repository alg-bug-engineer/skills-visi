"""knowledge_qa 案例库轻量匹配（纯关键词/标签，不引入向量库依赖）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# 问题类型 → 案例文本关键词
_PROBLEM_TYPE_KEYWORDS: dict[str, list[str]] = {
    "spillback": ["溢出", "外溢", "积压", "倒灌"],
    "congestion": ["拥堵", "排队", "饱和", "通行能力"],
    "empty_green": ["空放", "绿灯放空", "绿灯利用", "绿损"],
    "conflict": ["冲突", "相位", "相序", "左转", "机非"],
}

_TEXT_FIELDS = ("案例场景", "交通问题诊断", "治理方案")


def _default_path() -> Path:
    return Path(__file__).resolve().parents[3] / "docs" / "knowledge_qa.jsonl"


class CaseLibraryService:
    """按问题类型关键词 + 路口形态标签对案例库做加权关键词匹配，返回 Top-K。"""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else _default_path()
        self._cases: list[dict[str, Any]] | None = None

    def _load(self) -> list[dict[str, Any]]:
        if self._cases is not None:
            return self._cases
        cases: list[dict[str, Any]] = []
        if self._path.exists():
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    record["_text"] = "".join(
                        str(record.get(field, "")) for field in _TEXT_FIELDS
                    )
                    cases.append(record)
        self._cases = cases
        return cases

    def match(
        self,
        problem_types: list[str],
        shape_tags: list[str] | None = None,
        k: int = 3,
    ) -> list[dict[str, Any]]:
        """问题类型关键词权重高于形态标签，按命中分排序取 Top-K（分>0）。"""
        shape_tags = shape_tags or []
        keywords: list[str] = []
        for pt in problem_types:
            keywords.extend(_PROBLEM_TYPE_KEYWORDS.get(pt, []))

        scored: list[tuple[int, dict[str, Any]]] = []
        for record in self._load():
            text = record["_text"]
            pt_hits = sum(1 for kw in keywords if kw in text)
            shape_hits = sum(1 for tag in shape_tags if tag and tag in text)
            score = pt_hits * 3 + shape_hits
            if score > 0:
                scored.append((score, record))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {key: value for key, value in record.items() if key != "_text"}
            for _, record in scored[:k]
        ]
