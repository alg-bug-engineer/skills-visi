"""Resolve corridor / trunk road names against dim_line_info."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from intersection_agent.config import Settings, get_settings
from intersection_agent.db.postgres import PostgresPool
from intersection_agent.llm.qwen_client import QwenClient
from intersection_agent.utils.place_name_normalize import normalize_place_names

logger = logging.getLogger(__name__)

VARIANT_SYSTEM_PROMPT = """
你是交通地理信息助手。给定口语化道路/干线名称，输出可能的标准干线名称变体 JSON 数组。
只输出 JSON 数组，不要解释。每个元素为完整路名（如"奥体西路"）。最多 5 个变体。
""".strip()


@dataclass
class LineResolutionResult:
    line_id: str | None = None
    line_name: str | None = None
    source: str = "not_found"
    candidates: list[str] | None = None
    follow_up: str | None = None
    scan_mode: str = "line"
    road_name: str | None = None
    intersection_rows: list[dict] = field(default_factory=list)


class LineResolver:
    """Resolve corridor names; prefer line segments that start with the road name."""

    def __init__(
        self,
        pool: PostgresPool | None = None,
        llm: QwenClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._pool = pool or PostgresPool()
        self._llm = llm or QwenClient()
        self._settings = settings or get_settings()

    async def resolve(self, corridor_name: str) -> LineResolutionResult:
        corridor_name = self._normalize_corridor(corridor_name.strip())
        if self._settings.mock_db:
            return self._mock_resolve(corridor_name)

        await self._pool.connect()
        schema = self._settings.pgschema
        version_id = self._settings.pg_version_id

        best = await self._best_line_segment(corridor_name, schema)
        if best:
            return LineResolutionResult(
                line_id=str(best["line_id"]),
                line_name=str(best["line_name"]),
                source="segment",
                road_name=corridor_name,
            )

        for variant in await self._generate_variants(corridor_name):
            best = await self._best_line_segment(variant, schema)
            if best:
                return LineResolutionResult(
                    line_id=str(best["line_id"]),
                    line_name=str(best["line_name"]),
                    source="variant_segment",
                    road_name=variant,
                )

        inter_rows = await self._intersections_on_road(corridor_name, schema, version_id)
        if inter_rows:
            return LineResolutionResult(
                line_id=f"road:{corridor_name}",
                line_name=corridor_name,
                source="road_intersections",
                scan_mode="road_intersections",
                road_name=corridor_name,
                intersection_rows=[dict(r) for r in inter_rows],
            )

        candidates = await self._search_similar(corridor_name, schema)
        if candidates:
            lines = "\n".join(f"· {c}" for c in candidates)
            return LineResolutionResult(
                source="candidates",
                candidates=candidates,
                follow_up=(
                    f"未能精确找到「{corridor_name}」，您指的是以下干线之一吗？\n{lines}\n"
                    "请回复完整干线名称。"
                ),
            )

        return LineResolutionResult(
            source="not_found",
            follow_up="未找到该干线，请确认道路名称或联系数据管理员。",
        )

    async def resolve_candidate_selection(
        self, user_text: str, candidates: list[str]
    ) -> LineResolutionResult | None:
        text = user_text.strip()
        for candidate in candidates:
            if candidate in text or text in candidate:
                return await self.resolve(candidate)
        return None

    async def _best_line_segment(self, road_name: str, schema: str) -> dict | None:
        rows = await self._pool.fetch(
            f"""
            SELECT l.line_id, l.line_name, COUNT(r.inter_id) AS inter_count
            FROM {schema}.dim_line_info l
            JOIN {schema}.dim_line_inter_rltn r
              ON r.line_id = l.line_id AND r.is_deleted = 0
            WHERE l.is_deleted = 0
              AND (l.line_name LIKE $1 || '%' OR l.line_name LIKE $1 || '（%')
            GROUP BY l.line_id, l.line_name
            ORDER BY inter_count DESC, length(l.line_name) DESC
            LIMIT 1
            """,
            road_name,
        )
        return dict(rows[0]) if rows else None

    async def _intersections_on_road(
        self, road_name: str, schema: str, version_id: str
    ) -> list[dict]:
        pattern = f"%{road_name}%"
        return await self._pool.fetch(
            f"""
            SELECT i.inter_id, i.inter_name, i.geom_center,
                   NULL::int AS seq_no, NULL::float AS gap_to_prev_m
            FROM {schema}.dim_inter_info i
            WHERE i.version_id = $1
              AND i.is_signalized = 1
              AND i.inter_name LIKE $2
            ORDER BY i.inter_name
            LIMIT 40
            """,
            version_id,
            pattern,
        )

    async def _search_similar(self, name: str, schema: str, top_k: int = 5) -> list[str]:
        pattern = f"%{name}%"
        rows = await self._pool.fetch(
            f"""
            SELECT DISTINCT line_name
            FROM {schema}.dim_line_info
            WHERE is_deleted = 0 AND line_name LIKE $1
            ORDER BY length(line_name)
            LIMIT $2
            """,
            pattern,
            top_k,
        )
        return [str(r["line_name"]) for r in rows]

    async def _generate_variants(self, name: str) -> list[str]:
        variants = [name]
        if not name.endswith("路"):
            variants.append(f"{name}路")
        if name.endswith("路"):
            variants.append(name[:-1])
        try:
            raw = await self._llm.chat_json(system=VARIANT_SYSTEM_PROMPT, user=name)
            if isinstance(raw, list):
                variants.extend(str(x) for x in raw)
        except (ValueError, RuntimeError) as exc:
            logger.warning("line variant generation failed: %s", exc)
        deduped: list[str] = []
        seen: set[str] = set()
        for v in variants:
            v = self._normalize_corridor(v.strip())
            if v and v not in seen:
                seen.add(v)
                deduped.append(v)
        return deduped

    @staticmethod
    def _normalize_corridor(name: str) -> str:
        name = normalize_place_names(name)
        if "奥体西" in name and "奥体西路" not in name:
            return "奥体西路"
        if name and not name.endswith("路") and len(name) <= 8:
            return f"{name}路"
        return name

    @staticmethod
    def _mock_resolve(name: str) -> LineResolutionResult:
        key = name or "奥体西路"
        return LineResolutionResult(
            line_id="mock_line_001",
            line_name="奥体西路（演示段）",
            source="exact",
            road_name="奥体西路",
        )
