"""PostgreSQL access layer."""

from __future__ import annotations

import logging
from typing import Any

import asyncpg

from intersection_agent.config import Settings, get_settings

logger = logging.getLogger(__name__)


class PostgresPool:
    """Lazy asyncpg connection pool."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Initialize connection pool."""
        if self._settings.mock_db:
            return
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                host=self._settings.pghost,
                port=self._settings.pgport,
                user=self._settings.pguser,
                password=self._settings.pgpassword,
                database=self._settings.pgdatabase,
                min_size=1,
                max_size=5,
                command_timeout=30,
            )
            logger.info("PostgreSQL pool connected")

    async def close(self) -> None:
        """Close pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        """Run fetch query."""
        if self._settings.mock_db or self._pool is None:
            return []
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:
        """Run fetchrow query."""
        if self._settings.mock_db or self._pool is None:
            return None
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
