from functools import lru_cache

from pydantic import Field, model_validator
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
    telemetry_stream_maxlen: int = Field(default=100_000, ge=1, le=5_000_000)
    alert_scan_interval_seconds: int = Field(default=5, ge=1, le=3600)
    jwt_secret_key: str = "dev-only-change-me"
    jwt_issuer: str = "observa-api"
    jwt_audience: str = "observa"
    access_token_minutes: int = Field(default=15, ge=1, le=1440)
    refresh_token_days: int = Field(default=14, ge=1, le=90)
    refresh_cookie_name: str = "observa_refresh"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    auth_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    auth_rate_limit_register: int = Field(default=10, ge=1, le=1000)
    auth_rate_limit_login: int = Field(default=20, ge=1, le=1000)
    auth_rate_limit_refresh: int = Field(default=60, ge=1, le=5000)
    ingestion_rate_limit_per_minute: int = Field(default=600, ge=1, le=100_000)
    notification_secret_key: str = "dev-notification-secret-change-me"
    notification_max_attempts: int = Field(default=5, ge=1, le=20)
    notification_retry_scan_interval_seconds: int = Field(default=15, ge=1, le=3600)
    notification_delivery_lease_seconds: int = Field(default=120, ge=10, le=3600)
    notification_test_rate_limit_per_minute: int = Field(default=20, ge=1, le=1000)
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "alerts@observa.local"
    smtp_tls: bool = True
    webhook_allow_private_networks: bool = False
    webhook_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    query_max_range_seconds: int = Field(default=2_678_400, ge=60, le=31_536_000)
    query_max_points: int = Field(default=10_000, ge=1, le=100_000)
    query_max_groups: int = Field(default=100, ge=1, le=10_000)

    @model_validator(mode="after")
    def production_secrets_are_explicit(self) -> "Settings":
        if self.app_env == "production" and (
            self.notification_secret_key.startswith("dev-") or len(self.notification_secret_key) < 32
        ):
            raise ValueError("NOTIFICATION_SECRET_KEY must be explicitly configured in production")
        return self

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
