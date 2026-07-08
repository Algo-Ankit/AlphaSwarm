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


# Words too generic to be useful retrieval signal.
_STOPWORDS = frozenset(
    "the a an and or for to of in on with my me i want should would like strategy "
    "stock stocks trade trading buy sell invest investment portfolio how what when "
    "is are be my our your that this it as at by".split()
)


def _tokenize(text: str) -> set[str]:
    import re

    # Uppercase runs are likely tickers (RELIANCE, AAPL) — keep them as-is; the
    # rest is lowercased word tokens with stopwords removed.
    tickers = {t for t in re.findall(r"\b[A-Z]{2,10}\b", text)}
    words = {w for w in re.findall(r"[a-zA-Z]{3,}", text.lower()) if w not in _STOPWORDS}
    return {t.lower() for t in tickers} | words


async def _retrieve_commons_context(
    pool: "asyncpg.Pool | None",
    current_user: CurrentUser,
    query: str,
    top_k: int = 3,
) -> str:
    """
    Retrieve the most relevant published commons strategies for this query and
    render them as a few-shot grounding block. Ranking is lightweight token
    overlap (symbols + title + description) — no embedding infra required — with
    Sharpe as the tiebreak. Returns "" if nothing is relevant or on any error;
    retrieval must never break the advisor.
    """
    if pool is None:
        return ""
    try:
        from app.db.repositories.social import SocialRepo

        repo = SocialRepo(pool, current_user.tenant_id)
        candidates = await repo.commons_candidates_for_context(limit=40)
        if not candidates:
            return ""

        q_tokens = _tokenize(query)
        if not q_tokens:
            return ""

        scored: list[tuple[float, "asyncpg.Record"]] = []
        for c in candidates:
            symbols = [s.lower() for s in (c["symbols"] or [])]
            hay = _tokenize(f"{c['title']} {c['description']}") | set(symbols)
            overlap = len(q_tokens & hay)
            # Symbol matches are the strongest signal — weight them heavily.
            symbol_hits = len(q_tokens & set(symbols))
            score = overlap + 2 * symbol_hits
            if score > 0:
                scored.append((score, c))

        if not scored:
            return ""
        scored.sort(key=lambda x: x[0], reverse=True)

        blocks: list[str] = []
        for _, c in scored[:top_k]:
            code = (c["generated_logic"] or "").strip()
            snippet = code[:700] + ("\n# …(truncated)" if len(code) > 700 else "")
            sharpe = f"{c['sharpe_ratio']:.2f}" if c["sharpe_ratio"] is not None else "n/a"
            cagr = f"{c['cagr_pct']:.1f}%" if c["cagr_pct"] is not None else "n/a"
            if c["oos_computed_at"] is not None and c["oos_cagr_pct"] is not None:
                oos = f"{c['oos_cagr_pct']:.1f}% (out-of-sample, post-publish)"
            else:
                oos = "not yet measured"
            blocks.append(
                f"### {c['title']}\n"
                f"- Symbols: {', '.join(c['symbols'] or []) or 'n/a'} ({c['exchange']})\n"
                f"- In-sample CAGR {cagr}, Sharpe {sharpe}; OOS CAGR {oos}\n"
                f"- Approach: {(c['description'] or 'n/a').strip()[:280]}\n"
                f"```python\n{snippet}\n```"
            )

        return (
            "\n\n---\n"
            "The following are real, backtested strategies from the AlphaSwarm "
            "commons that are relevant to the user's thesis. Use them as grounding "
            "— cite what works, and be honest where the out-of-sample number shows "
            "alpha decayed. Do NOT copy them verbatim.\n\n" + "\n\n".join(blocks)
        )
    except Exception as exc:  # retrieval is best-effort, never fatal
        logger.debug("commons retrieval failed (non-fatal): %s", exc)
        return ""


def _render_holdings_review_prompt(risk: dict) -> str:
    """Build a grounded prompt from the deterministic risk scorecard."""
    lines = [
        "You are reviewing a user's real, consolidated multi-broker holdings. Below is a "
        "risk scorecard already computed deterministically — treat its numbers as ground "
        "truth. Give concise, plain-English guidance: which positions to TRIM, which to "
        "REVIEW/sell, and which to HOLD, and why. Be direct about concentration and losses. "
        "End with 2-3 concrete next steps. Always add one line reminding the user this is "
        "not personalised financial advice and the platform never sells on their behalf.",
        "",
        f"Portfolio: {risk['holdings_count']} holdings, total value {risk['total_value']:.0f}, "
        f"diversification={risk['diversification']}, "
        f"largest position {risk['top_weight_pct']:.0f}%, "
        f"broker concentration {risk['broker_concentration_pct']:.0f}%.",
        f"Overall: {risk['verdict']}",
        "",
        "Positions (symbol · weight · unrealized P&L · signal):",
    ]
    for h in risk["holdings"][:25]:
        pnl = f"{h['unrealized_pnl_pct']:+.0f}%" if h["unrealized_pnl_pct"] is not None else "n/a"
        lines.append(
            f"- {h['symbol']} ({h['broker']}): {h['weight_pct']:.0f}% · {pnl} · {h['signal']}"
        )
    return "\n".join(lines)


async def review_holdings(
    risk: dict,
    current_user: CurrentUser,
    pool: "asyncpg.Pool | None" = None,
) -> str:
    """
    Turn a deterministic risk scorecard (services/portfolio_risk.analyze_holdings)
    into plain-English trim/sell/hold guidance via the user's BYOK model. Same
    strict-BYOK enforcement as analyze_query. Raises ValueError on BYOK rejection
    or agent failure so the route can map it to the right HTTP status.
    """
    import asyncio

    from agent_framework import Agent

    if not risk.get("holdings"):
        return "No priced holdings to review yet — import a CAS statement first."

    api_key, base_url, model = await _resolve_byok(pool, current_user)
    client = _make_chat_client(api_key, base_url, model)
    advisor = Agent(
        client=client,
        name="PortfolioRiskAdvisor",
        instructions=ADVISOR_SYSTEM_PROMPT,
    )
    try:
        result = await asyncio.wait_for(
            advisor.run(_render_holdings_review_prompt(risk)), timeout=120.0
        )
        text = (result.text or "").strip()
        if not text:
            raise ValueError("The AI advisor returned an empty response. Please try again.")
        return text
    except asyncio.TimeoutError as exc:
        raise ValueError("The AI advisor timed out. Please try again.") from exc
    except ValueError:
        raise
    except Exception as exc:
        logger.error("review_holdings failed: %s", exc)
        raise ValueError(f"AI review failed: {exc}") from exc
    finally:
        await _close_client(client)


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

    # Retrieval-augmented grounding: every published commons strategy makes the
    # advisor smarter. Best-effort — an empty block leaves behavior unchanged.
    commons_context = await _retrieve_commons_context(pool, current_user, query)
    augmented_query = f"{query}{commons_context}" if commons_context else query

    client = _make_chat_client(api_key, base_url, model)
    advisor = Agent(
        client=client,
        name="InvestmentAdvisor",
        instructions=ADVISOR_SYSTEM_PROMPT,
    )

    try:
        result = await asyncio.wait_for(advisor.run(augmented_query), timeout=120.0)
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
