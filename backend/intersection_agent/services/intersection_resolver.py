"""Intersection name resolution with three-level fallback."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from intersection_agent.config import Settings, get_settings
from intersection_agent.db.postgres import PostgresPool
from intersection_agent.llm.qwen_client import QwenClient
from intersection_agent.utils.place_name_normalize import (
    extract_intersection_phrases,
    normalize_place_names,
)

logger = logging.getLogger(__name__)

NORMALIZE_SYSTEM_PROMPT = """
你是交通地理信息助手。给定口语化路口描述，输出可能的标准路口名称变体 JSON 数组。
只输出 JSON 数组，不要解释。每个元素为完整路口名，可使用"X路与Y路交叉口"或"X路与Y路路口"。
最多返回 5 个变体。注意路名顺序可互换（如"经十路与奥体西路"与"奥体西路与经十路"）。
""".strip()


@dataclass
class ResolutionResult:
    """Intersection resolution outcome."""

    inter_id: str | None = None
    inter_name: str | None = None
    source: str = "not_found"
    candidates: list[str] | None = None
    follow_up: str | None = None


class IntersectionResolver:
    """Resolve intersection names against dim_inter_info."""

    def __init__(
        self,
        pool: PostgresPool | None = None,
        llm: QwenClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._pool = pool or PostgresPool()
        self._llm = llm or QwenClient()
        self._settings = settings or get_settings()

    async def resolve(self, intersection_name: str) -> ResolutionResult:
        """Three-level intersection resolution."""
        intersection_name = normalize_place_names(intersection_name.strip())
        if self._settings.mock_db:
            return self._mock_resolve(intersection_name)

        await self._pool.connect()
        schema = self._settings.pgschema
        version_id = self._settings.pg_version_id

        # L1 exact
        row = await self._pool.fetchrow(
            f"""
            SELECT inter_id, inter_name
            FROM {schema}.dim_inter_info
            WHERE version_id = $1 AND inter_name = $2
            LIMIT 1
            """,
            version_id,
            intersection_name,
        )
        if row:
            return ResolutionResult(
                inter_id=row["inter_id"],
                inter_name=row["inter_name"],
                source="exact",
            )

        # L2 variants + fuzzy
        variants = await self._generate_variants(intersection_name)
        for variant in variants:
            matched = await self._fuzzy_match(variant, schema, version_id)
            if matched:
                return ResolutionResult(
                    inter_id=matched["inter_id"],
                    inter_name=matched["inter_name"],
                    source="variant",
                )

        # L3 candidates
        candidates = await self._search_similar(intersection_name, schema, version_id)
        if candidates:
            lines = "\n".join(f"· {c}" for c in candidates)
            return ResolutionResult(
                source="candidates",
                candidates=candidates,
                follow_up=(
                    f"未能精确找到「{intersection_name}」，您说的是以下路口之一吗？\n{lines}\n"
                    "请回复完整路口名称。"
                ),
            )

        return ResolutionResult(
            source="not_found",
            follow_up="该路口暂无数据，请确认路口名称或联系数据管理员。",
        )

    async def resolve_candidate_selection(
        self, user_text: str, candidates: list[str]
    ) -> ResolutionResult | None:
        """Match user reply against known candidates."""
        text = user_text.strip()
        for candidate in candidates:
            if candidate in text or text in candidate:
                if self._settings.mock_db:
                    return ResolutionResult(
                        inter_id="mock_inter_001",
                        inter_name=candidate,
                        source="candidate_pick",
                    )
                await self._pool.connect()
                row = await self._pool.fetchrow(
                    f"""
                    SELECT inter_id, inter_name
                    FROM {self._settings.pgschema}.dim_inter_info
                    WHERE version_id = $1 AND inter_name = $2
                    LIMIT 1
                    """,
                    self._settings.pg_version_id,
                    candidate,
                )
                if row:
                    return ResolutionResult(
                        inter_id=row["inter_id"],
                        inter_name=row["inter_name"],
                        source="candidate_pick",
                    )
        return None

    async def resolve_with_context(
        self, intersection_name: str, user_context: str
    ) -> ResolutionResult:
        """Resolve NLU intersection, falling back to phrases from raw user text."""
        result = await self.resolve(intersection_name)
        if result.inter_id:
            return result
        for phrase in extract_intersection_phrases(user_context):
            if phrase == intersection_name:
                continue
            alt = await self.resolve(phrase)
            if alt.inter_id:
                return alt
        return result

    async def _generate_variants(self, name: str) -> list[str]:
        """Use LLM to normalize intersection name variants."""
        try:
            variant_prompt = (
                NORMALIZE_SYSTEM_PROMPT
                + '\n输出 JSON 对象：{"variants": ["路口名1", "..."]}'
            )
            text = await self._llm.chat(
                system=variant_prompt,
                user=name,
                json_mode=True,
            )
            parsed = json.loads(text.strip().strip("`").replace("json\n", ""))
            if isinstance(parsed, dict) and isinstance(parsed.get("variants"), list):
                return [str(v) for v in parsed["variants"]]
            if isinstance(parsed, list):
                return [str(v) for v in parsed]
        except (json.JSONDecodeError, RuntimeError, ValueError) as exc:
            logger.warning("Variant generation failed: %s", exc)
        return [name]

    async def _fuzzy_match(
        self, name: str, schema: str, version_id: str
    ) -> dict[str, Any] | None:
        """Fuzzy match using LIKE; pg_trgm if available."""
        stripped = normalize_place_names(name.replace("交叉口", "").replace("路口", ""))
        parts = [p for p in stripped.split("与") if p]
        if not parts:
            parts = [name.replace("交叉口", "").replace("路口", "")]
        pattern = "%" + "%".join(parts) + "%"
        row = await self._pool.fetchrow(
            f"""
            SELECT inter_id, inter_name
            FROM {schema}.dim_inter_info
            WHERE version_id = $1
              AND is_signalized = 1
              AND inter_name LIKE $2
            ORDER BY length(inter_name)
            LIMIT 1
            """,
            version_id,
            pattern,
        )
        return dict(row) if row else None

    async def _search_similar(
        self, name: str, schema: str, version_id: str, top_k: int = 3
    ) -> list[str]:
        """Search top similar intersection names."""
        keywords = [
            normalize_place_names(k)
            for k in name.replace("交叉口", "").replace("路口", "").split("与")
            if k
        ]
        if not keywords:
            return []
        if len(keywords) >= 2:
            pattern = f"%{keywords[0]}%{keywords[1]}%"
        else:
            pattern = f"%{keywords[0]}%"
        rows = await self._pool.fetch(
            f"""
            SELECT inter_name
            FROM {schema}.dim_inter_info
            WHERE version_id = $1
              AND is_signalized = 1
              AND inter_name LIKE $2
            LIMIT $3
            """,
            version_id,
            pattern,
            top_k,
        )
        return [r["inter_name"] for r in rows]

    @staticmethod
    def _mock_resolve(name: str) -> ResolutionResult:
        """Mock resolution for tests."""
        if "不存在" in name or "未知路口" in name:
            return ResolutionResult(
                source="candidates",
                candidates=["奥体西路与经十路交叉口", "经十路与舜华路交叉口"],
                follow_up="未能精确找到，请从候选中选择。",
            )
        if "未知" in name:
            return ResolutionResult(
                source="not_found",
                follow_up="该路口暂无数据。",
            )
        return ResolutionResult(
            inter_id="mock_inter_001",
            inter_name=name or "奥体西路与经十路交叉口",
            source="exact",
        )
