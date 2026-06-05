"""
Strategy compiler — converts NL prompt to Python BaseStrategy subclass via AutoGen.
Sync fallback used when API key is not configured (returns placeholder comment).
"""
from __future__ import annotations

import logging

from app.domain.models import StrategyCreateRequest

logger = logging.getLogger(__name__)

_PLACEHOLDER = """\
# AutoGen strategy generation requires ANTHROPIC_API_KEY in your .env
# This placeholder will use the default RSI(14) momentum strategy at runtime.
# Set ANTHROPIC_API_KEY and recreate this strategy to generate real code.
"""


async def compile_strategy_prompt(request: StrategyCreateRequest) -> str:
    """
    Generate Python strategy code from NL prompt using AutoGen StrategyBuilderAgent.
    Falls back to a placeholder comment if ANTHROPIC_API_KEY is not set.
    """
    from app.core.config import get_settings
    settings = get_settings()

    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set — returning placeholder strategy code")
        return _PLACEHOLDER

    from app.services.strategy_builder import build_strategy_async
    try:
        code = await build_strategy_async(
            prompt=request.prompt,
            symbols=request.symbols,
            timeframe=request.timeframe,
            api_key=settings.anthropic_api_key,
        )
        logger.info("StrategyBuilderAgent generated code for strategy '%s'", request.name)
        return code
    except Exception as exc:
        logger.error("StrategyBuilderAgent failed for '%s': %s", request.name, exc)
        return _PLACEHOLDER
