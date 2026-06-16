import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_current_user, get_db_pool
from app.services.ai_advisor import analyze_query

router = APIRouter(prefix="/v1/ai-advisor", tags=["ai-advisor"])


class AdvisorQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000, description="Natural-language analysis or planning request.")


class AdvisorResponse(BaseModel):
    response: str


@router.post("/analyze", response_model=AdvisorResponse)
async def analyze(
    body: AdvisorQueryRequest,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> AdvisorResponse:
    """Run an investment-advisor query through the BYOK agent and return markdown."""
    query = body.query.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query must not be empty.",
        )
    try:
        markdown = await analyze_query(query, current_user, pool=pool)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AdvisorResponse(response=markdown)
