import base64
from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "AlphaSwarm Control Plane"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # CORS (production: comma-separated allowed origins)
    cors_origins: str = ""  # e.g. "https://app.alphaswarm.io,https://alphaswarm.io"

    # Database
    database_url: str = "postgresql+asyncpg://alphaswarm:alphaswarm@localhost:5432/alphaswarm"
    database_sync_url: str = "postgresql://alphaswarm:alphaswarm@localhost:5432/alphaswarm"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_task_always_eager: bool = False

    # AI (Anthropic)
    anthropic_api_key: str = ""
    strategy_builder_model: str = "claude-sonnet-4-6"
    analysis_model: str = "claude-haiku-4-5-20251001"

    # Alpaca
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    alpaca_data_stream_url: str = "wss://stream.data.alpaca.markets/v2"

    # News & Intelligence
    news_api_key: str = ""
    alpha_vantage_key: str = ""

    # JWT (RS256) - stored as base64-encoded PEM
    jwt_private_key_base64: str = ""
    jwt_public_key_base64: str = ""
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30

    # Broker key encryption (Fernet)
    broker_key_encryption_secret: str = ""

    # Sentry
    sentry_dsn: str = ""
    sentry_environment: str = "development"

    # Risk defaults
    default_max_order_notional: float = 1_000.0
    default_max_daily_notional: float = 5_000.0
    paper_trading_only: bool = True

    # Computed: decode base64 PEM keys
    @computed_field
    @property
    def jwt_private_key(self) -> str:
        if not self.jwt_private_key_base64:
            return ""
        return base64.b64decode(self.jwt_private_key_base64).decode()

    @computed_field
    @property
    def jwt_public_key(self) -> str:
        if not self.jwt_public_key_base64:
            return ""
        return base64.b64decode(self.jwt_public_key_base64).decode()

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
