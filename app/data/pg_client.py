"""PostgreSQL read helpers for intersection data loading."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_NAMED_PARAM = re.compile(r"(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)")


def _to_psycopg_sql(sql: str) -> str:
    """Convert SQLAlchemy-style :name params to psycopg %(name)s, preserving ::casts."""
    return _NAMED_PARAM.sub(r"%(\1)s", sql)


def read_pg_rows(sql: str, params: dict[str, Any], *, limit: int = 500) -> list[dict[str, Any]]:
    from app.config import get_settings

    settings = get_settings()
    if not settings.pg_dsn:
        raise RuntimeError("PG_DSN 未配置")

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("请安装 psycopg: pip install 'psycopg[binary]'") from exc

    bounded_sql = sql.strip().rstrip(";")
    if re.search(r"\blimit\b", bounded_sql, re.I) is None and limit > 0:
        bounded_sql = f"{bounded_sql} LIMIT {int(limit)}"

    bounded_sql = _to_psycopg_sql(bounded_sql)
    logger.debug("执行 PG 查询 limit=%s", limit)
    with psycopg.connect(settings.pg_dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(bounded_sql, params)
            rows = cur.fetchall()
    return [dict(row) for row in rows]

