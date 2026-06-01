from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AlphaSwarm Control Plane"
    database_url: str = "postgresql://alphaswarm:alphaswarm@localhost:5432/alphaswarm"
    redis_url: str = "redis://localhost:6379/0"
    celery_task_always_eager: bool = False
    broker_mode: str = "paper"
    max_order_notional: float = 10_000.0
    max_daily_strategy_notional: float = 50_000.0
    allowed_symbols: str = "AAPL,MSFT,NVDA,QQQ,SPY,TSLA"

    model_config = SettingsConfigDict(env_prefix="ALPHASWARM_", extra="ignore")

    @property
    def allowed_symbol_set(self) -> set[str]:
        return {
            symbol.strip().upper()
            for symbol in self.allowed_symbols.split(",")
            if symbol.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
