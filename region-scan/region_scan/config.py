"""扫描配置 —— 复用 backend settings，叠加区域扫描参数。

DB / LLM 等连接配置全部走 backend 的 ``intersection_agent.config.get_settings()``
（由 ``backend/.env`` 驱动），本模块**只**追加扫描专属参数，绝不硬编码连接串。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from intersection_agent.config import Settings, get_settings

DEFAULT_PERIODS = ["早高峰", "白平峰", "晚高峰"]
DEFAULT_CONCURRENCY = 4
DEFAULT_SNAPSHOT_DIR = "snapshots"


@dataclass(frozen=True)
class ScanSettings:
    """扫描运行参数 + backend settings 透传。

    访问未知属性时委托给底层 backend ``Settings``（如 ``pgschema``、
    ``pg_version_id``、``mock_db`` 等），避免重复声明连接配置。
    """

    base: Settings
    periods: list[str] = field(default_factory=lambda: list(DEFAULT_PERIODS))
    concurrency: int = DEFAULT_CONCURRENCY
    snapshot_dir: str = DEFAULT_SNAPSHOT_DIR

    def __getattr__(self, name: str):  # pragma: no cover - 简单委托
        # dataclass 字段在实例 __dict__ 中，未命中才走到这里。
        return getattr(self.base, name)


@lru_cache
def get_scan_settings() -> ScanSettings:
    """返回缓存的扫描配置单例。

    扫描参数可被环境变量覆盖：``SCAN_CONCURRENCY``、``SCAN_SNAPSHOT_DIR``、
    ``SCAN_PERIODS``（逗号分隔）。
    """
    concurrency = int(os.environ.get("SCAN_CONCURRENCY", DEFAULT_CONCURRENCY))
    snapshot_dir = os.environ.get("SCAN_SNAPSHOT_DIR", DEFAULT_SNAPSHOT_DIR)
    periods_env = os.environ.get("SCAN_PERIODS", "").strip()
    periods = (
        [p.strip() for p in periods_env.split(",") if p.strip()]
        if periods_env
        else list(DEFAULT_PERIODS)
    )
    return ScanSettings(
        base=get_settings(),
        periods=periods,
        concurrency=concurrency,
        snapshot_dir=snapshot_dir,
    )
