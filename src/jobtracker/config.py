from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Paths
    config_dir: Path = Path("config")

    # Database
    database_url: str = "postgresql+asyncpg://jobtracker:jobtracker@localhost:5432/jobtracker"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Embedding
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_batch_size: int = 64

    # Cross-encoder reranker
    reranker_model: str = "BAAI/bge-reranker-base"
    reranker_batch_size: int = 32
    reranker_top_k: int = 100

    # Matching
    match_score_threshold: float = 0.65
    notify_score_threshold: float = 0.75

    # Notifications
    discord_webhook_url: str = ""

    # Adzuna API (https://developer.adzuna.com/)
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""

    # Metrics server ports
    metrics_port: int = 8000
    enricher_metrics_port: int = 8001

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # "json" or "console"

    @field_validator("log_level")
    @classmethod
    def uppercase_log_level(cls, v: str) -> str:
        return v.upper()

    @property
    def sources_config(self) -> Path:
        return self.config_dir / "sources.yaml"

    @property
    def profile_config(self) -> Path:
        return self.config_dir / "profile.yaml"


settings = Settings()
