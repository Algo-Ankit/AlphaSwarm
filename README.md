# AlphaSwarm

AlphaSwarm is a multi-tenant agentic trading SaaS. The control plane exposes a FastAPI API for creating natural-language strategies and dispatching runs. The execution plane runs strategy work in isolated Celery workers through Redis. Broker execution is paper-mode scaffolding until Alpaca is wired in.

## Current Capabilities

- FastAPI health check and `/v1` strategy endpoints.
- Strategy prompt capture with generated execution notes.
- Celery task dispatch to a dedicated `trading_tasks` queue.
- Centralized risk verification before simulated broker execution.
- PostgreSQL schema for tenants, users, strategies, runs, orders, and audit events.
- Redis/PostgreSQL local services through Docker Compose.
- Generated OpenAPI contract in `openapi.json`.

## Local Development

Start infrastructure:

```powershell
docker compose up -d
```

Run the API:

```powershell
uvicorn app.main:app --reload
```

Run a worker:

```powershell
celery -A app.core.celery_app.celery_app worker -Q trading_tasks --loglevel=info
```

Regenerate the API contract after endpoint changes:

```powershell
python -m app.scripts.generate_openapi
```

Example strategy request:

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/v1/strategies `
  -Headers @{"X-Tenant-Id"="demo-tenant"; "X-User-Id"="demo-user"} `
  -ContentType "application/json" `
  -Body '{"name":"SPY momentum","prompt":"Buy SPY when short-term momentum is positive and exit when it weakens.","symbols":["SPY"],"timeframe":"1Min"}'
```
