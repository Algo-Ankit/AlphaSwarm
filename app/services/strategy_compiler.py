"""
Strategy compiler — converts NL prompt to Python BaseStrategy subclass via the
Microsoft Agent Framework strategy builder.
"""
from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncpg

from app.domain.models import StrategyCreateRequest

logger = logging.getLogger(__name__)

# User-facing message when a non-founder tries to generate without their own key.
_STRICT_BYOK_MESSAGE = "Strict BYOK enforced: Please add your free API key in Settings."


def _is_founder(user_email: str | None, founder_email: str) -> bool:
    """Constant-time, case-insensitive match against the configured founder email.

    Security notes: comparison is timing-safe (secrets.compare_digest); the founder
    email is never logged or echoed; an unset FOUNDER_EMAIL grants NO exemption
    (returns False), so the platform key stays locked by default.
    """
    founder = (founder_email or "").strip().lower()
    candidate = (user_email or "").strip().lower()
    if not founder or not candidate:
        return False
    return secrets.compare_digest(candidate, founder)


async def compile_strategy_prompt(
    request: StrategyCreateRequest,
    pool: "asyncpg.Pool | None" = None,
    user_email: str | None = None,
) -> tuple[str, str]:
    """
    Generate Python strategy code + a plain-English explanation from an NL prompt.

    Returns (generated_code, explanation). If request.llm_config_id is set, decrypts
    and uses that user-supplied key (BYOK). If the user has NO usable key, the
    platform-level .env key is used ONLY for the founder account (FOUNDER_EMAIL);
    every other account is rejected with a strict-BYOK error.

    Always raises ValueError on code-generation failure — never silently substitutes a
    placeholder. The explanation is best-effort and never blocks creation.
    """
    from app.core.config import get_settings
    from app.services.strategy_builder import build_strategy_async, explain_strategy_async

    settings = get_settings()

    # 1. Resolve the user's OWN key first (BYOK is the default path for everyone).
    api_key = base_url = model = None
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
                logger.warning("LLM config %s key decryption failed", request.llm_config_id)

    # 2. No usable user key → platform fallback is FOUNDER-ONLY (strict BYOK for all others).
    if not api_key:
        if not _is_founder(user_email, settings.founder_email):
            raise ValueError(_STRICT_BYOK_MESSAGE)
        logger.info("Founder account — using platform LLM key fallback.")
        api_key  = settings.llm_api_key
        base_url = settings.llm_base_url
        model    = settings.llm_model

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
