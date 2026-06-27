"""LLM narrative for corridor scan results."""

from __future__ import annotations

import json
import logging
from typing import Any

from intersection_agent.llm.qwen_client import QwenClient

logger = logging.getLogger(__name__)

NARRATIVE_SYSTEM = """
你是交通运行分析助手。根据系统提供的干线扫描结构化数据，用中文写 2-3 段分析：

1. 第一段：干线整体态势（必须引用数据覆盖路口数、干线延误或平均饱和度等真实数字）
2. 第二段：明确列出拥堵最严重的前三个路口（全名 + 饱和度 + 等级），不足三个则列出现有数量
3. 第三段：必须使用类似引导语：
   「地图上已标出全部路口的拥堵水平。您想深入分析哪一个？可以说「最拥堵的」「第二个」，或直接说路口名称。」

约束：只使用素材中的数字和路口名；不要替用户决定分析哪个路口；180-320 字；不要 markdown。
""".strip()


class CorridorNarrativeService:
    def __init__(self, llm: QwenClient | None = None) -> None:
        self._llm = llm or QwenClient()

    async def build(self, scan: dict[str, Any]) -> str:
        material = self._material(scan)
        try:
            return await self._llm.chat(
                system=NARRATIVE_SYSTEM,
                user=f"【扫描素材】\n{json.dumps(material, ensure_ascii=False, indent=2)}",
                temperature=0.3,
            )
        except (ValueError, RuntimeError) as exc:
            logger.warning("corridor narrative LLM failed: %s", exc)
            return self._fallback(material)

    @staticmethod
    def _material(scan: dict[str, Any]) -> dict[str, Any]:
        ranked = sorted(
            [i for i in (scan.get("intersections") or []) if i.get("has_data") and i.get("rank")],
            key=lambda x: int(x.get("rank") or 999),
        )
        top3 = []
        for item in ranked[:3]:
            m = item.get("metrics") or {}
            top3.append(
                {
                    "rank": item.get("rank"),
                    "inter_name": item.get("inter_name"),
                    "saturation_max": m.get("saturation_max"),
                    "level_label": m.get("level_label"),
                }
            )
        return {
            "line_name": scan.get("road_name") or scan.get("line_name"),
            "time_period_label": (scan.get("time_period") or {}).get("label"),
            "intersection_count": scan.get("intersection_count"),
            "data_coverage_count": scan.get("data_coverage_count"),
            "line_metrics": scan.get("line_metrics"),
            "overall_pattern": scan.get("overall_pattern"),
            "top3": top3,
        }

    @staticmethod
    def _fallback(material: dict[str, Any]) -> str:
        line = material.get("line_name") or "该干线"
        label = material.get("time_period_label") or "指定时段"
        cov = material.get("data_coverage_count", 0)
        total = material.get("intersection_count", 0)
        parts = [
            f"{label}，{line}共有 {total} 个信控路口，其中 {cov} 个有运行数据。"
            f"{material.get('overall_pattern', '')}",
        ]
        tops = []
        for item in material.get("top3") or []:
            sat = item.get("saturation_max")
            sat_text = f"{float(sat):.2f}" if sat is not None else "—"
            tops.append(
                f"{item.get('rank')}. {item.get('inter_name')}（饱和 {sat_text}，{item.get('level_label')}）"
            )
        if tops:
            parts.append("拥堵最严重的路口依次为：" + "；".join(tops) + "。")
        parts.append(
            "地图上已标出全部路口的拥堵水平。您想深入分析哪一个？"
            "可以说「最拥堵的」「第二个」，或直接说路口名称。"
        )
        return "\n\n".join(parts)
