"""Fetch Ring-Barrier diagram record from PostgreSQL ODS."""

from __future__ import annotations

import logging
from typing import Any

from intersection_agent.config import Settings, get_settings
from intersection_agent.db.postgres import PostgresPool
from intersection_agent.utils.json_safe import to_json_safe
from intersection_agent.utils.ring_diagram_parser import parse_ods_scheme_row

logger = logging.getLogger(__name__)

STAGE_TABLE = "ods_ctl_inter_scheme_hisense_stage"


class RingDiagramService:
    def __init__(
        self,
        pool: PostgresPool | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._pool = pool or PostgresPool()
        self._settings = settings or get_settings()

    async def build(self, inter_id: str) -> dict[str, Any]:
        if self._settings.mock_db:
            return self._mock()

        await self._pool.connect()
        schema = self._settings.pg_flow_schema
        try:
            row = await self._pool.fetchrow(
                f"""
                SELECT *
                FROM {schema}.{STAGE_TABLE}
                WHERE inter_id = $1 AND is_deleted = 0
                ORDER BY plan_no, pattern_no
                LIMIT 1
                """,
                inter_id,
            )
            if not row:
                return {"available": False, "reason": "no_scheme_row"}
            record = parse_ods_scheme_row(dict(row), source_table=f"{schema}.{STAGE_TABLE}")
            return {"available": True, "record": to_json_safe(record)}
        except Exception as exc:
            logger.warning("ring_diagram build failed: %s", exc)
            return {"available": False, "reason": str(exc)}

    @staticmethod
    def _mock() -> dict[str, Any]:
        return {
            "available": True,
            "record": {
                "cycle_len": 120,
                "ring_count": 2,
                "pattern": "plan1/pattern1",
                "green_times": [32, 28, 24, 20, 30, 26, 22, 18],
                "yellow_times": [3] * 8,
                "red_times": [2] * 8,
                "rings": [
                    {"phases": [1, 2, 3, 4], "barriers": [1]},
                    {"phases": [5, 6, 7, 8], "barriers": [1]},
                ],
                "channel_info": [
                    [[2, 11]],
                    [[2, 12]],
                    [[6, 11]],
                    [[6, 12]],
                    [[0, 11]],
                    [[0, 12]],
                    [[4, 11]],
                    [[4, 12]],
                ],
                "follow_phase_info": [],
            },
        }
