"""
Strategy compiler — converts NL prompt to Python BaseStrategy subclass via AutoGen.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncpg

from app.domain.models import StrategyCreateRequest

logger = logging.getLogger(__name__)


async def compile_strategy_prompt(
    request: StrategyCreateRequest,
    pool: "asyncpg.Pool | None" = None,
) -> tuple[str, str]:
    """
    Generate Python strategy code + a plain-English explanation from an NL prompt.

    Returns (generated_code, explanation). If request.llm_config_id is set, decrypts
    and uses that user-supplied key. Otherwise falls back to the platform-level key
    from server .env.

    Always raises ValueError on code-generation failure — never silently substitutes a
    placeholder. The explanation is best-effort and never blocks creation.
    """
    from app.core.config import get_settings
    from app.services.strategy_builder import build_strategy_async, explain_strategy_async

    settings = get_settings()
    api_key  = settings.llm_api_key
    base_url = settings.llm_base_url
    model    = settings.llm_model

    if request.llm_config_id and pool is not None:
        from uuid import UUID
        from app.db.repositories.llm_configs import LLMConfigRepo
        from app.services.broker_crypto import decrypt_key
        # tenant_id not available here — repo fetch by id only; route already validated ownership
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM llm_configs WHERE id = $1 AND is_active = TRUE",
                UUID(request.llm_config_id),
            )
        if row:
            try:
                api_key  = decrypt_key(row["key_encrypted"])
                base_url = row["base_url"]
                model    = row["model"]
            except ValueError:
                logger.warning("LLM config %s key decryption failed — using platform default", request.llm_config_id)

    try:
        code = await build_strategy_async(
            prompt=request.prompt,
            symbols=request.symbols,
            timeframe=request.timeframe,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
    except Exception as exc:
        logger.error("StrategyBuilderAgent failed for '%s': %s", request.name, exc)
        raise ValueError(f"Failed to generate strategy: {exc}") from exc

    logger.info("StrategyBuilderAgent generated code for strategy '%s' via model %s", request.name, model)

    # Separate pass: plain-English explanation (best-effort, never blocks creation).
    explanation = await explain_strategy_async(
        prompt=request.prompt,
        code=code,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    return code, explanation
