from fastapi import FastAPI

app = FastAPI(
    title="AlphaSwarm Control Plane",
    description="Multi-tenant algorithmic trading SaaS API",
    version="1.0.0"
)

@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "AlphaSwarm API is running"}
