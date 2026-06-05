"""
StrategyBuilderAgent — AutoGen pipeline: NL description → validated Python BaseStrategy subclass.

Uses AutoGen AssistantAgent backed by Claude Sonnet 4.6. Up to 3 sandbox-validate retries.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_WRITER_SYSTEM_PROMPT = """\
You are StrategyWriterAgent, an expert quantitative trading strategy programmer.

Convert the user's natural-language trading strategy into a Python class that extends BaseStrategy.

STRICT RULES:
1. Do NOT include any import statements. Only these symbols are available in scope:
   BaseStrategy, OrderIntent, OrderSide, OrderType, Decimal, Optional
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


def build_strategy_sync(
    prompt: str,
    symbols: list[str],
    timeframe: str,
    api_key: str,
    max_retries: int = 3,
) -> str:
    """
    Calls AutoGen StrategyWriterAgent (Claude Sonnet 4.6), validates in RestrictedPython sandbox.
    Returns validated Python source string. Raises ValueError after all retries exhausted.
    """
    import autogen
    from app.services.strategy_sandbox import SandboxError, compile_strategy_code

    llm_config = {
        "config_list": [
            {
                "model": "claude-sonnet-4-6",
                "api_key": api_key,
                "api_type": "anthropic",
            }
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
    }

    writer = autogen.AssistantAgent(
        name="StrategyWriter",
        llm_config=llm_config,
        system_message=_WRITER_SYSTEM_PROMPT,
    )

    conversation: list[dict] = [
        {"role": "user", "content": _build_user_message(prompt, symbols, timeframe)}
    ]
    last_error = "no attempts made"

    for attempt in range(1, max_retries + 1):
        logger.info("StrategyBuilderAgent attempt %d/%d", attempt, max_retries)

        try:
            response = writer.generate_reply(messages=conversation)
        except Exception as exc:
            raise ValueError(f"AutoGen LLM call failed: {exc}") from exc

        if not response:
            last_error = "LLM returned empty response"
            conversation.append({
                "role": "user",
                "content": "Your response was empty. Respond with the strategy class in ```python ... ``` fences.",
            })
            continue

        content = response.get("content", str(response)) if isinstance(response, dict) else str(response)
        conversation.append({"role": "assistant", "content": content})

        code = _extract_python_block(content)
        if not code:
            last_error = "no ```python ... ``` code block found"
            conversation.append({
                "role": "user",
                "content": "No code block found. Wrap your class in ```python ... ``` fences and respond again.",
            })
            continue

        try:
            compile_strategy_code(code)
            logger.info("StrategyBuilderAgent validated on attempt %d", attempt)
            return code
        except SandboxError as exc:
            last_error = str(exc)
            logger.warning("Sandbox failure attempt %d: %s", attempt, exc)
            if attempt < max_retries:
                conversation.append({
                    "role": "user",
                    "content": (
                        f"Sandbox validation failed: {exc}\n\n"
                        "Fix the error and respond with the corrected class only in ```python ... ``` fences."
                    ),
                })

    raise ValueError(
        f"StrategyBuilderAgent failed after {max_retries} attempts. Last error: {last_error}"
    )


async def build_strategy_async(
    prompt: str,
    symbols: list[str],
    timeframe: str,
    api_key: str,
) -> str:
    """Async wrapper — runs build_strategy_sync in a thread pool so it doesn't block the event loop."""
    return await asyncio.to_thread(build_strategy_sync, prompt, symbols, timeframe, api_key)
