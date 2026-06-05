# ── Stage 1: dependency builder ──────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: lean runtime image ──────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Runtime OS deps only (libpq for asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Cache dirs must be writable by the non-root user (site-packages and home are not)
ENV NUMBA_CACHE_DIR=/tmp
ENV YFINANCE_CACHE_DIR=/tmp

# Non-root user for security
RUN useradd --system --no-create-home alphaswarm
USER alphaswarm

# Copy application code
COPY --chown=alphaswarm:alphaswarm . .

EXPOSE 8000

# Liveness probe friendly: responds fast even if DB is slow
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 1 uvicorn worker per container.
# Scale horizontally via docker compose --scale api=N behind nginx.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--loop", "uvloop", \
     "--no-access-log"]
