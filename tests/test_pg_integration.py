import re

import pytest

from app.data.pg_client import _to_psycopg_sql


def test_named_param_conversion_preserves_casts():
    sql = "SELECT inter_id::text FROM t WHERE inter_id = :inter_id AND day_of_week = :dow"
    converted = _to_psycopg_sql(sql)
    assert ":inter_id" not in converted
    assert "%(inter_id)s" in converted
    assert "inter_id::text" in converted


@pytest.mark.integration
def test_pg_connection_from_env():
    from dotenv import load_dotenv

    load_dotenv()
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    if not settings.pg_dsn:
        pytest.skip("PG_DSN 未配置")

    from app.data.pg_client import read_pg_rows

    rows = read_pg_rows("SELECT current_database() AS db", {}, limit=1)
    assert rows[0]["db"]


@pytest.mark.integration
def test_pg_load_bundle_real_intersection():
    from dotenv import load_dotenv

    load_dotenv()
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    if not settings.pg_dsn:
        pytest.skip("PG_DSN 未配置")

    from app.data.load_pg_bundle import load_pg_diagnosis_bundle
    from app.data.pg_client import read_pg_rows

    rows = read_pg_rows(
        f"""
        SELECT inter_id, inter_name
        FROM {settings.pg_schema}.{settings.pg_dim_inter_table}
        WHERE is_signalized = 1
        LIMIT 1
        """,
        {},
        limit=1,
    )
    if not rows:
        pytest.skip("PG 无信控路口样本")

    inter = rows[0]
    ticket = {
        "intersection_name": inter["inter_name"],
        "inter_id": inter["inter_id"],
        "direction": "东向西",
        "movement": "直行",
        "time_range": "17:30-18:30",
        "period": "工作日晚高峰",
    }
    task: dict = {"diagnosis_ticket": ticket}
    loaded = load_pg_diagnosis_bundle(task, ticket, settings)
    assert loaded.get("source") == "pg"
    if loaded.get("ok"):
        assert loaded["metrics"]
        assert loaded["topology"]
    else:
        assert loaded.get("reason")
