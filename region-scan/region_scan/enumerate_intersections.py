"""枚举当前版本全部信号路口（有坐标）。

仿照 ``corridor_scan_service`` 的 ``dim_inter_info`` 查询，但不限定 line ——
取 ``version_id=当前版本`` 且 ``is_signalized=1`` 且 ``geom_center`` 非空的全部路口。
坐标解析复用 corridor_scan 的 ``_parse_point``（WKT ``POINT(lon lat)``）。
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from intersection_agent.services.corridor_scan_service import _parse_point

# 注入式 fetch：(sql, *params) -> list[row]，row 支持 __getitem__（dict / asyncpg.Record）。
FetchFn = Callable[..., Awaitable[list[Any]]]


def _build_query(road_schema: str) -> str:
    return f"""
        SELECT inter_id, inter_name, geom_center
        FROM {road_schema}.dim_inter_info
        WHERE version_id = $1 AND is_signalized = 1 AND geom_center IS NOT NULL
    """


async def enumerate_signalized_intersections(
    pool: Any,
    settings: Any,
    *,
    fetch: FetchFn | None = None,
) -> list[dict[str, Any]]:
    """返回 ``[{inter_id, inter_name, lon, lat}, ...]``，丢弃坐标无法解析的路口。

    ``fetch`` 可注入用于单测；默认走 ``pool.fetch``。
    """
    road_schema = settings.pgschema
    version_id = settings.pg_version_id
    sql = _build_query(road_schema)

    if fetch is None:
        await pool.connect()
        fetch = pool.fetch

    rows = await fetch(sql, version_id)

    result: list[dict[str, Any]] = []
    for row in rows:
        lon, lat = _parse_point(row["geom_center"])
        if lon is None or lat is None:
            continue
        inter_id = str(row["inter_id"])
        inter_name = row["inter_name"]
        result.append(
            {
                "inter_id": inter_id,
                "inter_name": str(inter_name) if inter_name else inter_id,
                "lon": lon,
                "lat": lat,
            }
        )
    return result
