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

    # AI — news sentiment classification (app/services/news_intel.py only)
    anthropic_api_key: str = ""

    # AI — AutoGen StrategyBuilderAgent, via an OpenAI-compatible client.
    # Points at a free local model server (Ollama, LM Studio) or a free-tier
    # proxy (e.g. Groq) — no paid Anthropic key needed to generate strategies.
    # Default targets Ollama on the HOST machine: api/worker run inside Docker,
    # where "localhost" is the container itself — host.docker.internal reaches
    # the Windows/Mac Docker Desktop host (set llm_base_url in .env to override).
    #   Ollama (host):  llm_base_url=http://host.docker.internal:11434/v1, llm_api_key=ollama
    #   LM Studio:      llm_base_url=http://host.docker.internal:1234/v1,  llm_api_key=lm-studio
    #   Groq free tier: llm_base_url=https://api.groq.com/openai/v1, llm_api_key=<free Groq key>, llm_model=llama-3.1-8b-instant
    llm_base_url: str = "http://host.docker.internal:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "llama3.1"

    # Alpaca
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    alpaca_data_stream_url: str = "wss://stream.data.alpaca.markets/v2"

    # News & Intelligence
    news_api_key: str = ""
    alpha_vantage_key: str = ""

    # JWT — RS256 for production (base64-encoded PEM), HS256 fallback for dev
    jwt_private_key_base64: str = ""
    jwt_public_key_base64: str = ""
    jwt_secret_key: str = "dev-secret-key-change-in-production"  # HS256 dev fallback
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30

    # Broker key encryption (Fernet)
    broker_key_encryption_secret: str = ""

    # OAuth — broker-level credentials (platform-level, not per-user)
    # Upstox: register a platform app at https://upstox.com/developer/
    upstox_client_id: str = ""
    upstox_client_secret: str = ""
    # Base URL of the frontend — used to build OAuth redirect URIs
    app_base_url: str = "http://localhost:3000"

    # Sentry
    sentry_dsn: str = ""
    sentry_environment: str = "development"
    sentry_traces_sample_rate: float = 0.1

    # ── Billing (Stripe) ─────────────────────────────────────────────────────
    # Live agent deployment requires an active "Quant Tier" subscription. The
    # checkout/webhook endpoints are no-ops until stripe_secret_key is set.
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""        # whsec_... — verifies webhook signatures
    stripe_price_quant: str = ""           # price_... for the Quant Tier subscription
    # Where Stripe Checkout redirects after success/cancel (frontend routes).
    stripe_success_url: str = "http://localhost:3000/billing/success?session_id={CHECKOUT_SESSION_ID}"
    stripe_cancel_url: str = "http://localhost:3000/billing/cancel"

    # ── Transactional email (SendGrid) ───────────────────────────────────────
    # Falls back to console-print stubs when sendgrid_api_key is empty, so dev
    # works with no external dependency.
    sendgrid_api_key: str = ""
    email_from: str = "no-reply@alphaswarm.io"
    email_from_name: str = "AlphaSwarm"

    # Strategy sandbox — wall-clock budget for a single on_bar() / backtest loop.
    # Backstops the RestrictedPython sandbox against CPU-exhaustion (e.g.
    # `for i in range(10**18)`) that the AST prescan can't catch. POSIX workers
    # only; Windows/eager mode falls back to Celery's task_time_limit.
    strategy_exec_timeout_seconds: float = 30.0

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
