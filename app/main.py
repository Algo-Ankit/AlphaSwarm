from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse

from app.api.routes import router
from app.core.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────
    # Redis ping — confirm broker is reachable before accepting traffic
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await redis.ping()
        app.state.redis = redis
    except Exception as exc:
        raise RuntimeError(f"Redis unreachable on startup: {exc}") from exc

    # DB connection pool will be initialised here in Phase 2
    # (asyncpg pool → app.state.db_pool)

    yield

    # ── Shutdown ──────────────────────────────────────────────
    await app.state.redis.aclose()


app = FastAPI(
    title=settings.app_name,
    description="Multi-tenant algorithmic trading SaaS API",
    version="1.0.0",
    lifespan=lifespan,
    default_response_class=ORJSONResponse,  # faster JSON serialization
    docs_url="/docs" if not settings.is_production else None,   # hide docs in prod
    redoc_url="/redoc" if not settings.is_production else None,
)

# ── Middleware ────────────────────────────────────────────────
# GZip — compress responses > 1KB (significant for large OHLCV payloads)
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
app.include_router(router)


# ── Health checks ─────────────────────────────────────────────
@app.get("/health", tags=["infra"])
async def health_live():
    """Liveness probe — returns 200 if the process is alive."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["infra"])
async def health_ready():
    """
    Readiness probe — used by nginx/load balancer to decide if this
    container should receive traffic. Checks Redis connectivity.
    Returns 503 if any dependency is unhealthy.
    """
    checks: dict[str, str] = {}

    try:
        await app.state.redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    # DB check added in Phase 2 when asyncpg pool is wired up
    checks["db"] = "pending_phase2"

    all_ok = all(v == "ok" or v.startswith("pending") for v in checks.values())
    status_code = 200 if all_ok else 503

    return ORJSONResponse(
        content={"status": "ready" if all_ok else "degraded", "checks": checks},
        status_code=status_code,
    )


def _build_cors_origins() -> list[str]:
    if settings.is_production:
        # In production, read from env var CORS_ORIGINS=https://app.alphaswarm.io,...
        raw = getattr(settings, "cors_origins", "")
        return [o.strip() for o in raw.split(",") if o.strip()] if raw else []
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
    ]
