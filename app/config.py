from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    qwen_api_key: str = ""
    dashscope_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"
    qwen_timeout_s: float = 360.0
    qwen_tts_model: str = "qwen3-tts-flash-realtime"
    qwen_tts_voice: str = "Cherry"
    qwen_tts_mode: str = "commit"
    qwen_tts_sample_rate: int = 24000
    qwen_tts_workspace_id: str = ""
    tts_enabled: bool = True
    llm_mock: bool = False
    log_level: str = "INFO"
    case_library_path: str = "data/knowledge_qa.jsonl"
    allow_demo_fallback: bool = False
    pg_dsn: str = ""
    mysql_dsn: str = ""
    pg_schema: str = "road6"
    pg_flow_schema: str = "xianchang"
    pg_dim_inter_table: str = "dim_inter_info"
    pg_channel_table: str = "dwd_tfc_rltn_wide_inter_ft_link"
    feedback_log_path: str = "data/plan_feedback.jsonl"
    user_experience_path: str = "data/user_experience.jsonl"
    skills_output_path: str = "data/skills"

    @property
    def case_library_abs_path(self) -> Path:
        path = Path(self.case_library_path)
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def feedback_log_abs_path(self) -> Path:
        path = Path(self.feedback_log_path)
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def user_experience_abs_path(self) -> Path:
        path = Path(self.user_experience_path)
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def skills_output_abs_path(self) -> Path:
        path = Path(self.skills_output_path)
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def qwen_tts_ws_url(self) -> str:
        return "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"

    @property
    def tts_api_key(self) -> str:
        if self.dashscope_api_key:
            return self.dashscope_api_key
        if "dashscope.aliyuncs.com" in self.qwen_base_url:
            return self.qwen_api_key
        return ""

    @property
    def tts_configured(self) -> bool:
        return bool(self.tts_api_key)

    @property
    def tts_workspace(self) -> str | None:
        return self.qwen_tts_workspace_id or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
