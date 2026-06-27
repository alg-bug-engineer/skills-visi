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
    mock_llm: bool = False
    mock_db: bool = False
    evidence_debug: bool = False
    demo_mode: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "*"
    public_url: str = ""

    aliyun_nls_appkey: str = ""
    aliyun_ak_id: str = ""
    aliyun_ak_secret: str = ""
    aliyun_nls_region: str = "cn-shanghai"
    aliyun_nls_voice: str = "zhishuo"
    aliyun_nls_format: str = "mp3"
    aliyun_nls_sample_rate: int = 16000
    aliyun_nls_speech_rate: int = 0
    tts_enabled: bool = True

    rules_dir: Path = _BACKEND_ROOT / "rules"

    @property
    def aliyun_nls_gateway_host(self) -> str:
        """NLS gateway host for TTS REST API."""
        region = self.aliyun_nls_region.strip() or "cn-shanghai"
        return f"nls-gateway-{region}.aliyuncs.com"

    @property
    def tts_configured(self) -> bool:
        """Whether Aliyun TTS credentials are present."""
        return bool(self.aliyun_nls_appkey and self.aliyun_ak_id and self.aliyun_ak_secret)

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
