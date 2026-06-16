import asyncio
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.auth import router as auth_router
from app.api.backtest import router as backtest_router
from app.api.billing import router as billing_router
from app.api.brokers import router as broker_router
from app.api.llm_configs import router as llm_configs_router
from app.api.market import router as market_router
from app.api.notifications import router as notifications_router
from app.api.portfolio import router as portfolio_router
from app.api.routes import router as strategy_router
from app.api.ws import router as ws_router
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.db.connection import close_pool, create_pool, get_pool

settings = get_settings()

# ── Sentry (production error + performance monitoring) ─────────────────────────
# Initialised before the app is constructed so startup/import errors are captured.
# No-op when SENTRY_DSN is unset (local dev / CI).
if settings.sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        # Don't ship request bodies (may contain credentials / order intents).
        send_default_pii=False,
    )


def _build_cors_origins() -> list[str]:
    if settings.is_production:
        raw = getattr(settings, "cors_origins", "")
        return [o.strip() for o in raw.split(",") if o.strip()] if raw else []
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
    ]





@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await redis.ping()
        app.state.redis = redis
    except Exception as exc:
        raise RuntimeError(f"Redis unreachable on startup: {exc}") from exc

    try:
        app.state.db_pool = await create_pool()
    except Exception as exc:
        raise RuntimeError(f"PostgreSQL unreachable on startup: {exc}") from exc

    # Start Redis pub/sub → WebSocket bridge for all AlphaSwarm channels
    from app.ws.manager import ws_manager
    listener_task = asyncio.create_task(
        ws_manager.redis_listener(app.state.redis, "bars:*")
    )
    portfolio_listener_task = asyncio.create_task(
        ws_manager.redis_listener(app.state.redis, "portfolio:*")
    )
    run_listener_task = asyncio.create_task(
        ws_manager.redis_listener(app.state.redis, "run:*")
    )

    yield

    listener_task.cancel()
    portfolio_listener_task.cancel()
    run_listener_task.cancel()

    # ── Shutdown ──────────────────────────────────────────────
    await close_pool()
    await app.state.redis.aclose()


app = FastAPI(
    title=settings.app_name,
    description="Multi-tenant algorithmic trading SaaS API",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Middleware ────────────────────────────────────────────────
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)

# ── Routes ────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(broker_router)
app.include_router(llm_configs_router)
app.include_router(market_router)
app.include_router(ws_router)
app.include_router(strategy_router)
app.include_router(backtest_router)
app.include_router(portfolio_router)
app.include_router(notifications_router)
app.include_router(billing_router)


# ── Health checks ─────────────────────────────────────────────
@app.get("/health", tags=["infra"])
async def health_live():
    return {"status": "ok"}


@app.get("/health/ready", tags=["infra"])
async def health_ready():
    checks: dict[str, str] = {}

    try:
        await app.state.redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["db"] = "ok"
    except Exception as exc:
        checks["db"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        content={"status": "ready" if all_ok else "degraded", "checks": checks},
        status_code=200 if all_ok else 503,
    )
