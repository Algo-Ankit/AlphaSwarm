from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.brokers import router as broker_router
from app.api.routes import router as strategy_router
from app.core.config import get_settings
from app.db.connection import close_pool, create_pool, get_pool

settings = get_settings()

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

    yield

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
app.include_router(strategy_router)


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
