# AlphaSwarm Phase 5 Issues

> **STATUS: ✅ ALL RESOLVED.** Every issue below has been fixed in the working tree. Status notes added per-issue.

The following bugs have been identified in the Phase 5 (Strategy Builder & Backtesting) implementation. These are the root causes for the agent creation failures and terminal errors.

## 1. AutoGen LLM Model Name Configuration is Invalid
**Status:** ✅ FIXED — model name no longer hardcoded to an invalid identifier.
**Location:** `app/services/strategy_builder.py` (Line 113)
**Description:** The AutoGen `llm_config` is hardcoded to use `claude-sonnet-4-6`. This is not a valid model identifier for the Anthropic API (e.g., it should be `claude-3-5-sonnet-20241022`). As a result, the `StrategyWriterAgent` fails to communicate with the Anthropic API on every attempt.

## 2. Strategy Compiler Silently Swallows Generation Errors
**Status:** ✅ FIXED — generation errors propagate; no `_PLACEHOLDER` fallback masking failures.
**Location:** `app/services/strategy_compiler.py` (Line 42)
**Description:** The `compile_strategy_prompt` function catches all exceptions (including the invalid model name error mentioned above) and silently returns a `_PLACEHOLDER` string instead of propagating the error to the user. This makes the frontend think the strategy was deployed successfully (returning a 201), but it actually deploys a broken/empty strategy that defaults to the fallback RSI logic later.

## 3. Market Hours Check Blocks Agent Runs & Causes Terminal Errors
**Status:** ✅ FIXED — paper/dry-run passes `MarketState(is_open=True, session_status="paper")`, skipping the hours gate while the daily-notional cap still applies.
**Location:** `app/domain/risk.py` (Line 40) and `app/worker/tasks.py` (Line 385)
**Description:** The strategy runner (`_execute_async`) creates a `MarketState` based on the current real-time session status. If the agent is run outside of regular NASDAQ trading hours, `verify_order_intent` immediately rejects all generated signals. This causes the terminal to show a bunch of "REJECTED" errors and no orders are executed, even in paper/dry-run mode if the check is rigidly enforced.

## 4. Sandbox Environment Lacks Mathematical & Datetime Utilities
**Status:** ✅ FIXED — safe `math`/`datetime` helpers injected into the sandbox globals.
**Location:** `app/services/strategy_sandbox.py` (Line 53)
**Description:** The `RestrictedPython` sandbox injects a very limited set of globals. While `max` and `int` are available via `safe_builtins`, common modules like `math` and `datetime` are entirely blocked. If the AutoGen LLM generates a strategy that attempts to use `math.sqrt` or `datetime.timedelta` (which quantitative strategies frequently do), the strategy will crash during `compile_strategy_code` or at runtime.

---

**How these issues were resolved:**
1. ✅ `strategy_builder.py` uses a valid model name (no hardcoded invalid id).
2. ✅ `strategy_compiler.py` propagates the generation error instead of falling back to `_PLACEHOLDER`.
3. ✅ Paper/dry-run runs pass `MarketState(is_open=True, session_status="paper")` so the hours gate is skipped while the daily-notional cap still applies.
4. ✅ Safe `math`/`datetime` helpers injected into the sandbox globals.
