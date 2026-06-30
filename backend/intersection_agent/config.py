"""Application configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    dashscope_api_key: str = ""
    qwen_model: str = "qwen3.6-flash-2026-04-16"
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_timeout_s: float = 60.0
    # 可选：仅 LLM HTTP 客户端使用（HTTP 代理，勿用 SOCKS）。Clash TUN 假 IP 场景下需显式配置。
    llm_http_proxy: str = ""

    pghost: str = "121.40.233.80"
    pgport: int = 15432
    pguser: str = "ycx"
    pgpassword: str = ""
    pgdatabase: str = "ycx"
    pgschema: str = "road6"
    pg_flow_schema: str = "xianchang"
    pg_version_id: str = "20260501"

    log_level: str = "INFO"
    log_file: str = "data/logs/app.log"
    log_max_bytes: int = 10_485_760
    log_backup_count: int = 5
    skill_dir_path: str = "data/skills"
    profile_dir_path: str = "data/profiles"
    case_library_path: str = "data/expert_knowledge.md"
    mock_llm: bool = False
    mock_db: bool = False
    evidence_debug: bool = False
    demo_mode: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "*"
    public_url: str = ""

    dashscope_workspace_id: str = ""
    qwen_tts_model: str = "qwen3-tts-flash-realtime"
    qwen_tts_voice: str = "Cherry"
    qwen_tts_mode: str = "commit"
    qwen_tts_sample_rate: int = 24000
    tts_enabled: bool = True
    # TTS Realtime 专用 workspace：默认留空（按 API Key 默认工作空间鉴权）。
    # LLM 的 DASHSCOPE_WORKSPACE_ID 对 TTS Realtime WS 可能无访问权（Workspace access denied），
    # 故 TTS 不复用 LLM workspace；仅当确有 TTS 可用的 workspace 时再单独设置。
    qwen_tts_workspace_id: str = ""

    rules_dir: Path = _BACKEND_ROOT / "rules"

    @property
    def qwen_tts_ws_url(self) -> str:
        """WebSocket URL for Qwen-TTS Realtime (Beijing).

        Workspace is sent via ``X-DashScope-WorkSpace`` on the client, not in the host.
        """
        return "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"

    @property
    def tts_configured(self) -> bool:
        """Whether Qwen TTS Realtime credentials are present.

        TTS Realtime 仅需 API Key；workspace 可选（见 ``qwen_tts_workspace_id``）。
        """
        return bool(self.dashscope_api_key)

    @property
    def tts_workspace(self) -> str | None:
        """Workspace 传给 TTS Realtime 客户端（默认不传，按 Key 默认空间鉴权）。"""
        return self.qwen_tts_workspace_id or None

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse CORS_ORIGINS env (comma-separated or *)."""
        raw = (self.cors_origins or "*").strip()
        if raw == "*":
            return ["*"]
        return [part.strip() for part in raw.split(",") if part.strip()]

    @property
    def pg_dsn(self) -> str:
        """PostgreSQL connection string."""
        return (
            f"postgresql://{self.pguser}:{self.pgpassword}"
            f"@{self.pghost}:{self.pgport}/{self.pgdatabase}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
