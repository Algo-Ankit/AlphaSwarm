from fastapi import FastAPI

from app.api.routes import router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Multi-tenant algorithmic trading SaaS API",
    version="1.0.0",
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "AlphaSwarm API is running"}


app.include_router(router)
