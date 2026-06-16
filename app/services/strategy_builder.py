"""
StrategyBuilderAgent — Microsoft Agent Framework pipeline: NL description →
validated Python BaseStrategy subclass.

Uses agent_framework.Agent backed by an OpenAI-compatible chat client
(agent_framework.openai.OpenAIChatClient) — points at a free local model server
(Ollama, LM Studio) or a free-tier proxy (Groq) via base_url, so strategy
generation never requires a paid API key.

ReAct (Reason + Act): the writer agent is given a `validate_strategy_code` TOOL
that compiles candidate code in the RestrictedPython sandbox and returns the
exact error. The model reasons, writes code, ACTS by calling the tool, observes
the result, and self-corrects — all within a single agent run — instead of the
old hand-rolled "regenerate from scratch" loop. An outer bounded loop remains as
a safety net for models that ignore the tool. Migrated off Microsoft AutoGen,
which entered maintenance mode after Agent Framework 1.0 (GA April 2026).
"""
from __future__ import annotations

import inspect
import logging
import re
from typing import Annotated, Optional

from pydantic import Field

logger = logging.getLogger(__name__)

_WRITER_SYSTEM_PROMPT = """\
You are StrategyWriterAgent, an expert quantitative trading strategy programmer.

Convert the user's natural-language trading strategy into a Python class that extends BaseStrategy.
LIMITATIONS: You do not have access to statistical forecasting, machine learning models, or external data. 
You are constrained to a limited set of Technical Analysis (TA) indicators. Because individual TA indicators 
are often weak alpha factors, you must creatively combine them (e.g., trend alignment with EMA + mean 
reversion with RSI + volatility filters with ATR) to formulate stronger, more robust trading logic.

STRICT RULES:
1. Do NOT include any import statements. Only these symbols are available in scope:
   BaseStrategy, OrderIntent, OrderSide, OrderType, Decimal, Optional, math, datetime
   pd and np are NOT available. Do NOT attempt to use them.
2. Define exactly one class that extends BaseStrategy.
3. Implement on_bar(self) -> Optional[OrderIntent].
4. Return None to hold. Return an OrderIntent to signal a trade.
5. ALL signals must come from self.indicators (a pre-computed dict). Available keys:
   RSI_14, MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9,
   EMA_20, EMA_50, EMA_200, BBU_20_2.0, BBM_20_2.0, BBL_20_2.0, ATRr_14
   Access with: self.indicators.get("RSI_14")  — returns float or None.
6. Use self.close for current bar closing price (float).
7. Use self.is_flat, self.is_long, self.is_short for position state.
8. Use self.position for current held quantity (float or None).
9. Size orders using float(self.ctx.risk.max_order_notional).
10. Populate OrderIntent with self.ctx.strategy_id, self.ctx.symbol, self.ctx.exchange.
11. Always set is_paper=self.ctx.risk.paper_trading_only in OrderIntent.
12. Do NOT access self.bars for custom computation. Use self.close and self.indicators only.
13. No network calls, file I/O, or side effects. on_bar() must complete in < 100ms.
14. NEVER use augmented assignment on attributes (self.x += 1 is FORBIDDEN). Always write self.x = self.x + 1.
15. Use getattr(self, 'key', default) for lazy instance state. Never define __init__.
16. Output ONLY the fenced code block below — no explanations, no preamble, no
    markdown outside the fences, no commentary before or after. Just the class.
17. ReAct workflow: BEFORE giving your final answer, call the `validate_strategy_code`
    tool with your full class source. If it returns anything other than "VALID", read
    the error, fix the code, and call the tool again. Only emit your final fenced
    answer once the tool returns "VALID".

Wrap your code in ```python ... ``` fences. Output ONLY the class, nothing else.

Example:
```python
class RSIMomentum(BaseStrategy):
    def on_bar(self) -> Optional[OrderIntent]:
        rsi = self.indicators.get("RSI_14")
        if rsi is None:
            return None
        close = self.close
        qty = Decimal(str(max(1, int(float(self.ctx.risk.max_order_notional) / close))))
        if rsi < 30 and self.is_flat:
            return OrderIntent(
                strategy_id=self.ctx.strategy_id,
                symbol=self.ctx.symbol,
                exchange=self.ctx.exchange,
                side=OrderSide.buy,
                quantity=qty,
                order_type=OrderType.market,
                estimated_price=Decimal(str(close)),
                is_paper=self.ctx.risk.paper_trading_only,
            )
        if rsi > 70 and self.is_long:
            return OrderIntent(
                strategy_id=self.ctx.strategy_id,
                symbol=self.ctx.symbol,
                exchange=self.ctx.exchange,
                side=OrderSide.sell,
                quantity=Decimal(str(abs(self.position))),
                order_type=OrderType.market,
                estimated_price=Decimal(str(close)),
                is_paper=self.ctx.risk.paper_trading_only,
            )
        return None
```
"""


_EXPLAINER_SYSTEM_PROMPT = """\
You are StrategyExplainerAgent. You translate a validated Python trading strategy into
a short, plain-English explanation for a non-programmer who is about to backtest it.

RULES:
- Write 2-4 short sentences (or up to 4 short bullet points). No more.
- Describe, in plain language: when the strategy BUYS, when it SELLS/exits, and which
  indicators or price conditions drive those decisions.
- Translate indicator names to plain terms where natural (e.g. RSI = momentum,
  EMA = moving-average trend, ATR = volatility, Bollinger Bands = price range).
- Do NOT output any code, code fences, variable names, or Python syntax.
- Do NOT invent behavior that is not in the code. If the code only buys, say it only buys.
- Be neutral and factual. Do not promise profits or give financial advice.
- Output ONLY the explanation prose — no preamble like "This strategy" headers, no markdown.
"""


def _extract_python_block(text: str) -> Optional[str]:
    match = re.search(r"```python\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else None


def _build_explain_message(prompt: str, code: str) -> str:
    return (
        "Explain the following validated trading strategy in plain English.\n\n"
        f"The user originally described it as:\n{prompt}\n\n"
        "Here is the generated strategy code (for your reference only — do not echo it):\n"
        f"{code}\n\n"
        "Write the plain-English explanation now."
    )


def _fallback_explanation(prompt: str) -> str:
    """Deterministic explanation used when the LLM explainer is unavailable.

    The original NL prompt is itself a plain-English description, so echoing it back
    is a safe, code-free fallback that never blocks strategy creation.
    """
    cleaned = " ".join(prompt.split()).strip()
    if not cleaned:
        return "Automated strategy generated from your description."
    return f"This strategy implements your description: “{cleaned}”"


def _build_user_message(prompt: str, symbols: list[str], timeframe: str) -> str:
    return (
        f"Strategy description: {prompt}\n\n"
        f"Symbols: {', '.join(s.upper() for s in symbols)}\n"
        f"Timeframe: {timeframe}\n\n"
        "Available indicator keys (self.indicators dict — all values are float or None):\n"
        "  RSI_14, MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9,\n"
        "  EMA_20, EMA_50, EMA_200, BBU_20_2.0, BBM_20_2.0, BBL_20_2.0, ATRr_14\n\n"
        "Reminder: pd and np are NOT in scope. Use self.indicators and self.close only.\n\n"
        "Generate the Python strategy class now."
    )


def _make_chat_client(api_key: str, base_url: str, model: str):
    """OpenAI-compatible chat client. base_url targets Ollama/LM Studio/Groq, etc.

    Unlike AutoGen, Agent Framework infers model capabilities from the client, so
    no explicit ModelInfo/capability declaration is needed for non-registry models.
    """
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
        logger.debug("chat client cleanup failed (non-fatal): %s", exc)


def validate_strategy_code(
    code: Annotated[str, Field(description="The complete Python source of the BaseStrategy subclass to validate.")]
) -> str:
    """Compile a candidate strategy in the secure sandbox.

    Returns "VALID" if the code passes all sandbox checks, otherwise
    "INVALID: <reason>" with the exact error to fix. This is the agent's ACT step
    in the ReAct loop — call it to check your code before answering.
    """
    from app.services.strategy_sandbox import SandboxError, compile_strategy_code

    try:
        compile_strategy_code(code)
        return "VALID"
    except SandboxError as exc:
        return f"INVALID: {exc}"
    except Exception as exc:  # surface any load-time error to the model verbatim
        return f"INVALID: {exc}"


async def _run_agent(agent, task: str, *, timeout: float, label: str) -> str:
    """Run an agent with a bounded per-call timeout + transient-failure retries."""
    import asyncio

    for net_attempt in range(1, 4):
        try:
            result = await asyncio.wait_for(agent.run(task), timeout=timeout)
            return (result.text or "").strip()
        except asyncio.TimeoutError:
            if net_attempt == 3:
                raise ValueError(f"{label} timed out after 3 network attempts.")
            logger.warning("%s timeout, retrying %d/3...", label, net_attempt)
            await asyncio.sleep(2 ** net_attempt)
        except Exception as exc:
            if net_attempt == 3:
                raise ValueError(f"{label} failed after 3 network attempts: {exc}") from exc
            logger.warning("%s error: %s, retrying %d/3...", label, exc, net_attempt)
            await asyncio.sleep(2 ** net_attempt)
    return ""  # unreachable; loop either returns or raises


async def build_strategy_async(
    prompt: str,
    symbols: list[str],
    timeframe: str,
    api_key: str,
    base_url: str,
    model: str,
    max_retries: int = 3,
) -> str:
    """
    Drives a Microsoft Agent Framework ChatAgent (ReAct) to convert an NL prompt
    into a sandbox-validated Python BaseStrategy subclass. The agent self-corrects
    via the validate_strategy_code tool; the outer loop re-prompts as a safety net.
    Returns validated Python source. Raises ValueError after all retries exhausted.
    """
    from agent_framework import Agent

    from app.services.strategy_sandbox import SandboxError, compile_strategy_code

    client = _make_chat_client(api_key, base_url, model)
    writer = Agent(
        client=client,
        name="StrategyWriter",
        instructions=_WRITER_SYSTEM_PROMPT,
        tools=[validate_strategy_code],  # ReAct: the agent validates as it reasons
    )

    task: str = _build_user_message(prompt, symbols, timeframe)
    last_error = "no attempts made"

    try:
        for attempt in range(1, max_retries + 1):
            logger.info("StrategyBuilderAgent attempt %d/%d", attempt, max_retries)
            content = await _run_agent(writer, task, timeout=60.0, label="Agent Framework LLM call")

            if not content:
                last_error = "LLM returned empty response"
                task = "Your response was empty. Respond with the strategy class in ```python ... ``` fences."
                continue

            code = _extract_python_block(content)
            if not code:
                last_error = "no ```python ... ``` code block found"
                task = "No code block found. Wrap your class in ```python ... ``` fences and respond again."
                continue

            try:
                compile_strategy_code(code)
                logger.info("StrategyBuilderAgent validated on attempt %d", attempt)
                return code
            except SandboxError as exc:
                last_error = str(exc)
                logger.warning("Sandbox failure attempt %d: %s", attempt, exc)
                if attempt < max_retries:
                    task = (
                        f"Sandbox validation failed: {exc}\n\n"
                        "Call validate_strategy_code to confirm your fix, then respond with the "
                        "corrected class only in ```python ... ``` fences."
                    )
    finally:
        await _close_client(client)

    raise ValueError(
        f"StrategyBuilderAgent failed after {max_retries} attempts. Last error: {last_error}"
    )


async def explain_strategy_async(
    prompt: str,
    code: str,
    api_key: str,
    base_url: str,
    model: str,
) -> str:
    """
    Produce a plain-English explanation of an already-validated strategy.

    A SEPARATE agent pass from build_strategy_async (no tools, no sandbox) so the
    strict code-generation contract stays intact. Best-effort: any failure falls
    back to echoing the user's prompt rather than blocking strategy creation.
    """
    from agent_framework import Agent

    client = _make_chat_client(api_key, base_url, model)
    explainer = Agent(
        client=client,
        name="StrategyExplainer",
        instructions=_EXPLAINER_SYSTEM_PROMPT,
    )
    task = _build_explain_message(prompt, code)
    try:
        content = await _run_agent(explainer, task, timeout=30.0, label="StrategyExplainerAgent")
        return content or _fallback_explanation(prompt)
    except Exception as exc:
        logger.warning("StrategyExplainerAgent failed, using fallback: %s", exc)
        return _fallback_explanation(prompt)
    finally:
        await _close_client(client)
