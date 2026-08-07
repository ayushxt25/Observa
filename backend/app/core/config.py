from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://observa:observa@localhost:5432/observa"
    redis_url: str = "redis://localhost:6379/0"
    max_ingest_batch_size: int = Field(default=5000, ge=1, le=50000)
    max_query_rows: int = Field(default=10000, ge=1, le=100000)
    cors_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "https://performance-dashboard-rose.vercel.app"
    )
    redis_stream_name: str = "telemetry:events"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
