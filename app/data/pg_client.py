"""PostgreSQL read helpers for intersection data loading."""

from __future__ import annotations

import contextlib
import contextvars
import logging
import re
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_NAMED_PARAM = re.compile(r"(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)")

# 上下文内复用的单连接：同一次加载的多条查询共享一条连接，避免逐查询重连远端 PG
# （每次 psycopg.connect 到远端约 ~290ms 握手，一份检查单约 20 条查询 → 数秒纯连接开销）。
# contextvar 天然按线程/协程隔离，不同请求互不串连（需求21-R4）。
_ctx_conn: contextvars.ContextVar[Any | None] = contextvars.ContextVar("_pg_ctx_conn", default=None)


def _to_psycopg_sql(sql: str) -> str:
    """Convert SQLAlchemy-style :name params to psycopg %(name)s, preserving ::casts."""
    return _NAMED_PARAM.sub(r"%(\1)s", sql)


@contextlib.contextmanager
def pg_connection() -> Iterator[Any | None]:
    """在此上下文内复用同一条 PG 连接，消除逐查询重连开销。

    - 无 PG_DSN 时 yield None（调用方 read_pg_rows 会照常抛错/降级）。
    - 嵌套进入时复用外层连接，不重复开/关。
    - 使用 autocommit：只读 SELECT 各自独立，单条失败不污染后续查询。
    """
    from app.config import get_settings

    settings = get_settings()
    if not settings.pg_dsn:
        yield None
        return

    existing = _ctx_conn.get()
    if existing is not None:
        yield existing
        return

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - 环境缺依赖
        raise RuntimeError("请安装 psycopg: pip install 'psycopg[binary]'") from exc

    conn = psycopg.connect(settings.pg_dsn, row_factory=dict_row, autocommit=True)
    token = _ctx_conn.set(conn)
    try:
        yield conn
    finally:
        _ctx_conn.reset(token)
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


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

    # 优先复用上下文连接（pg_connection() 内），否则回退为逐查询短连接。
    ctx_conn = _ctx_conn.get()
    if ctx_conn is not None:
        with ctx_conn.cursor() as cur:
            cur.execute(bounded_sql, params)
            rows = cur.fetchall()
        return [dict(row) for row in rows]

    with psycopg.connect(settings.pg_dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(bounded_sql, params)
            rows = cur.fetchall()
    return [dict(row) for row in rows]
