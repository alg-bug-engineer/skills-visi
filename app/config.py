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
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"
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
    signal_opt_engine_src: str = ""
    feedback_log_path: str = "data/plan_feedback.jsonl"

    @property
    def case_library_abs_path(self) -> Path:
        path = Path(self.case_library_path)
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def feedback_log_abs_path(self) -> Path:
        path = Path(self.feedback_log_path)
        return path if path.is_absolute() else PROJECT_ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
