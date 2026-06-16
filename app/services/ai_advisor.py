"""
InvestmentAdvisorAgent — Microsoft Agent Framework pipeline that runs a user's
natural-language wealth-management query (stock/ETF analysis, SIP/SWP planning)
through the ADVISOR_SYSTEM_PROMPT and returns a markdown response.

BYOK is enforced exactly as in strategy_compiler.py: the user's own decrypted
LLM key is the default path for everyone. The platform-level .env key is a
FOUNDER-ONLY fallback (FOUNDER_EMAIL) — every other account is rejected with a
strict-BYOK error, so the platform never pays for API usage.
"""
from __future__ import annotations

import inspect
import logging
import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncpg

from app.api.deps import CurrentUser
from app.domain.prompts.advisor_system import ADVISOR_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# User-facing message when a non-founder tries to analyze without their own key.
_STRICT_BYOK_MESSAGE = "Strict BYOK enforced: Please add your free API key in Settings."


def _is_founder(user_email: str | None, founder_email: str) -> bool:
    """Constant-time, case-insensitive match against the configured founder email.

    Mirrors strategy_compiler._is_founder: timing-safe comparison, founder email is
    never logged, and an unset FOUNDER_EMAIL grants NO exemption (returns False).
    """
    founder = (founder_email or "").strip().lower()
    candidate = (user_email or "").strip().lower()
    if not founder or not candidate:
        return False
    return secrets.compare_digest(candidate, founder)


def _make_chat_client(api_key: str, base_url: str | None, model: str):
    """OpenAI-compatible chat client — same primitive used by the strategy builder."""
    from agent_framework.openai import OpenAIChatClient

    return OpenAIChatClient(model=model, api_key=api_key, base_url=base_url)


async def _close_client(client) -> None:
    """Best-effort cleanup — close whichever coroutine/method the client exposes."""
    closer = getattr(client, "aclose", None) or getattr(client, "close", None)
    if closer is None:
        return
    try:
        res = closer()
        if inspect.isawaitable(res):
            await res
    except Exception as exc:  # cleanup must never mask the real result/error
        logger.debug("advisor chat client cleanup failed (non-fatal): %s", exc)


async def _resolve_byok(
    pool: "asyncpg.Pool | None",
    current_user: CurrentUser,
) -> tuple[str, str | None, str]:
    """Resolve (api_key, base_url, model) for this user under strict BYOK.

    1. The user's OWN active LLM config (first one) is the default for everyone.
    2. No usable key → platform fallback, FOUNDER-ONLY. Everyone else is rejected.

    Raises ValueError(_STRICT_BYOK_MESSAGE) when a non-founder has no usable key.
    """
    from app.core.config import get_settings

    settings = get_settings()
    api_key = base_url = model = None

    if pool is not None:
        from app.db.repositories.llm_configs import LLMConfigRepo
        from app.services.broker_crypto import decrypt_key

        repo = LLMConfigRepo(pool, current_user.tenant_id)
        configs = await repo.get_all()
        if configs:
            row = configs[0]
            try:
                api_key = decrypt_key(row["key_encrypted"])
                base_url = row["base_url"]
                model = row["model"]
            except ValueError:
                logger.warning("LLM config %s key decryption failed", row["id"])

    if not api_key:
        if not _is_founder(current_user.email, settings.founder_email):
            raise ValueError(_STRICT_BYOK_MESSAGE)
        logger.info("Founder account — using platform LLM key fallback for advisor.")
        api_key = settings.llm_api_key
        base_url = settings.llm_base_url
        model = settings.llm_model

    return api_key, base_url, model


async def analyze_query(
    query: str,
    current_user: CurrentUser,
    pool: "asyncpg.Pool | None" = None,
) -> str:
    """
    Run the user's NL wealth-management query through the InvestmentAdvisorAgent and
    return the markdown response.

    Uses strict BYOK (see _resolve_byok). Raises ValueError on BYOK rejection or on
    agent failure — the route translates these to the right HTTP status.
    """
    import asyncio

    from agent_framework import Agent

    api_key, base_url, model = await _resolve_byok(pool, current_user)

    client = _make_chat_client(api_key, base_url, model)
    advisor = Agent(
        client=client,
        name="InvestmentAdvisor",
        instructions=ADVISOR_SYSTEM_PROMPT,
    )

    try:
        result = await asyncio.wait_for(advisor.run(query), timeout=120.0)
        text = (result.text or "").strip()
        if not text:
            raise ValueError("The AI advisor returned an empty response. Please try again.")
        return text
    except asyncio.TimeoutError as exc:
        raise ValueError("The AI advisor timed out. Please try a shorter query.") from exc
    except ValueError:
        raise
    except Exception as exc:
        logger.error("InvestmentAdvisorAgent failed: %s", exc)
        raise ValueError(f"AI advisor failed: {exc}") from exc
    finally:
        await _close_client(client)
