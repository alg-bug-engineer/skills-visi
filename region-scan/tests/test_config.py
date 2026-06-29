"""Task 0.2 — 配置与 backend 复用打通。"""


def test_can_import_backend_services():
    """能从同一环境 import backend 的关键服务与 PG 访问层。"""
    from intersection_agent.services.intersection_cognition_service import (
        IntersectionCognitionService,
    )
    from intersection_agent.services.flow_timing_governance_service import (
        FlowTimingGovernanceService,
    )
    from intersection_agent.db.postgres import PostgresPool

    assert IntersectionCognitionService is not None
    assert FlowTimingGovernanceService is not None
    assert PostgresPool is not None


def test_get_scan_settings_exposes_scan_params():
    """get_scan_settings() 复用 backend settings 并叠加扫描参数。"""
    from region_scan.config import get_scan_settings

    settings = get_scan_settings()

    # 叠加的扫描参数
    assert settings.periods == ["早高峰", "白平峰", "晚高峰"]
    assert settings.concurrency == 4
    assert settings.snapshot_dir == "snapshots"

    # 透传 backend settings（不硬编码连接串）
    assert settings.pgschema
    assert settings.pg_version_id
