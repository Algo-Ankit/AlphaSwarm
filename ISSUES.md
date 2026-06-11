# AlphaSwarm Phase 5 Issues

The following bugs have been identified in the Phase 5 (Strategy Builder & Backtesting) implementation. These are the root causes for the agent creation failures and terminal errors.

## 1. AutoGen LLM Model Name Configuration is Invalid
**Location:** `app/services/strategy_builder.py` (Line 113)
**Description:** The AutoGen `llm_config` is hardcoded to use `claude-sonnet-4-6`. This is not a valid model identifier for the Anthropic API (e.g., it should be `claude-3-5-sonnet-20241022`). As a result, the `StrategyWriterAgent` fails to communicate with the Anthropic API on every attempt.

## 2. Strategy Compiler Silently Swallows Generation Errors
**Location:** `app/services/strategy_compiler.py` (Line 42)
**Description:** The `compile_strategy_prompt` function catches all exceptions (including the invalid model name error mentioned above) and silently returns a `_PLACEHOLDER` string instead of propagating the error to the user. This makes the frontend think the strategy was deployed successfully (returning a 201), but it actually deploys a broken/empty strategy that defaults to the fallback RSI logic later.

## 3. Market Hours Check Blocks Agent Runs & Causes Terminal Errors
**Location:** `app/domain/risk.py` (Line 40) and `app/worker/tasks.py` (Line 385)
**Description:** The strategy runner (`_execute_async`) creates a `MarketState` based on the current real-time session status. If the agent is run outside of regular NASDAQ trading hours, `verify_order_intent` immediately rejects all generated signals. This causes the terminal to show a bunch of "REJECTED" errors and no orders are executed, even in paper/dry-run mode if the check is rigidly enforced.

## 4. Sandbox Environment Lacks Mathematical & Datetime Utilities
**Location:** `app/services/strategy_sandbox.py` (Line 53)
**Description:** The `RestrictedPython` sandbox injects a very limited set of globals. While `max` and `int` are available via `safe_builtins`, common modules like `math` and `datetime` are entirely blocked. If the AutoGen LLM generates a strategy that attempts to use `math.sqrt` or `datetime.timedelta` (which quantitative strategies frequently do), the strategy will crash during `compile_strategy_code` or at runtime.

---

**How to resolve these issues:**
1. Update `strategy_builder.py` to use a valid Anthropic model name.
2. Update `strategy_compiler.py` to raise an `HTTPException(400)` with the generation error instead of falling back to `_PLACEHOLDER`.
3. Update `tasks.py` or `risk.py` to gracefully bypass or handle the market hours check during backtesting / dry runs, or surface a clear user-facing warning rather than a terminal rejection loop.
4. Inject safe `math` functions (like `math.sqrt`, `math.log`) into the `safe_globals` dict in `strategy_sandbox.py`.
