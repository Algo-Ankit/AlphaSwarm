"""
StrategyBuilderAgent — AutoGen pipeline: NL description → validated Python BaseStrategy subclass.

Uses AutoGen AssistantAgent (autogen-agentchat) backed by an OpenAI-compatible
chat completion endpoint (autogen-ext's OpenAIChatCompletionClient) — points at
a free local model server (Ollama, LM Studio) or a free-tier proxy (Groq), so
strategy generation never requires a paid API key. Up to 3 sandbox-validate retries.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

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


def _extract_python_block(text: str) -> Optional[str]:
    match = re.search(r"```python\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else None


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


def _make_model_client(api_key: str, base_url: str, model: str):
    from autogen_core.models import ModelFamily, ModelInfo
    from autogen_ext.models.openai import OpenAIChatCompletionClient

    return OpenAIChatCompletionClient(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0.2,
        max_tokens=4096,
        # Free/local models (Ollama, LM Studio, Groq) aren't in autogen's model
        # registry, so capabilities must be declared explicitly or the client
        # raises "model_info is required" before making any call.
        model_info=ModelInfo(
            vision=False,
            function_calling=False,
            json_output=False,
            family=ModelFamily.UNKNOWN,
            structured_output=False,
            multiple_system_messages=True,
        ),
    )


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
    Calls AutoGen StrategyWriterAgent via an OpenAI-compatible endpoint, validates
    in the RestrictedPython sandbox. Returns validated Python source string.
    Raises ValueError after all retries exhausted.
    """
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.messages import TextMessage

    from app.services.strategy_sandbox import SandboxError, compile_strategy_code

    model_client = _make_model_client(api_key, base_url, model)
    writer = AssistantAgent(
        name="StrategyWriter",
        model_client=model_client,
        system_message=_WRITER_SYSTEM_PROMPT,
    )

    task: str = _build_user_message(prompt, symbols, timeframe)
    last_error = "no attempts made"

    try:
        for attempt in range(1, max_retries + 1):
            logger.info("StrategyBuilderAgent attempt %d/%d", attempt, max_retries)

            # Network/API retry loop for transient failures (independent of sandbox retries)
            result = None
            import asyncio
            for net_attempt in range(1, 4):
                try:
                    result = await asyncio.wait_for(writer.run(task=task), timeout=45.0)
                    break  # Success
                except asyncio.TimeoutError:
                    if net_attempt == 3:
                        raise ValueError("AutoGen LLM call timed out after 3 network attempts.")
                    logger.warning("LLM API timeout, retrying %d/3...", net_attempt)
                    await asyncio.sleep(2 ** net_attempt)
                except Exception as exc:
                    if net_attempt == 3:
                        raise ValueError(f"AutoGen LLM call failed after 3 network attempts: {exc}") from exc
                    logger.warning("LLM API error: %s, retrying %d/3...", exc, net_attempt)
                    await asyncio.sleep(2 ** net_attempt)

            reply = result.messages[-1] if result.messages else None
            content = reply.content if isinstance(reply, TextMessage) else ""

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
                        "Fix the error and respond with the corrected class only in ```python ... ``` fences."
                    )
    finally:
        await model_client.close()

    raise ValueError(
        f"StrategyBuilderAgent failed after {max_retries} attempts. Last error: {last_error}"
    )
