import re

with open('app/worker/tasks.py', 'r') as f:
    content = f.read()

# 1. DB write helper transaction
db_write_orig = '''async def _write_order_async(
    pool,
    tenant_id: str,
    strategy_id: str,
    run_id: str,
    intent: OrderIntent,
    result: OrderResult,
    risk_status: str,
    risk_reason: str,
) -> None:'''

db_write_new = '''async def _write_order_async(
    pool,
    tenant_id: str,
    strategy_id: str,
    run_id: str,
    intent: OrderIntent,
    result: OrderResult,
    risk_status: str,
    risk_reason: str,
) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():'''

content = content.replace(db_write_orig, db_write_new)
content = content.replace('    await pool.execute(', '            await conn.execute(')

# 2. Global pool
import_orig = '''async def _execute_async(
    strategy_id: str,
    tenant_id: str,
    user_id: str,
    run_id: str | None,
    dry_run: bool,
    symbols: list[str],
    timeframe: str,
    risk_config: dict,
) -> dict:
    import asyncpg'''

import_new = '''_pool = None

async def _execute_async(
    strategy_id: str,
    tenant_id: str,
    user_id: str,
    run_id: str | None,
    dry_run: bool,
    symbols: list[str],
    timeframe: str,
    risk_config: dict,
) -> dict:
    global _pool
    import asyncpg'''

content = content.replace(import_orig, import_new)

pool_orig = '''    try:
        pool = await asyncpg.create_pool(db_url, min_size=1, max_size=3)'''

pool_new = '''    try:
        if _pool is None:
            _pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5)
        pool = _pool'''

content = content.replace(pool_orig, pool_new)

pool_close_orig = '''    finally:
        if pool is not None:
            await pool.close()'''
pool_close_new = '''    finally:
        pass  # Pool is kept alive globally'''
content = content.replace(pool_close_orig, pool_close_new)

# 3. Wrapping the loop in try-except and adding idempotency and local state update
loop_orig = '''        for symbol in tradable_symbols:
            bars = bars_by_symbol.get(symbol, [])
            bars_df = dfs_by_symbol.get(symbol, pd.DataFrame())
            ind = indicators_by_symbol.get(symbol, {})'''

loop_new = '''        for symbol in tradable_symbols:
          try:
            bars = bars_by_symbol.get(symbol, [])
            bars_df = dfs_by_symbol.get(symbol, pd.DataFrame())
            ind = indicators_by_symbol.get(symbol, {})'''
content = content.replace(loop_orig, loop_new)

order_exec_orig = '''            else:
                order_result = executor.place_order(signal)'''
order_exec_new = '''            else:
                client_order_id = f"{str(run_id)[:8]}_{symbol}_{int(bars[-1].timestamp.timestamp())}" if run_id else None
                order_result = executor.place_order(signal, client_order_id)'''
content = content.replace(order_exec_orig, order_exec_new)

update_pos_orig = '''            today_notional += risk_result.order_notional

            if run_id:'''
update_pos_new = '''            today_notional += risk_result.order_notional
            
            # Update local memory so subsequent loop iterations use fresh state
            if order_result.broker_status in ("filled", "partially_filled", "pending", "accepted", "dry_run"):
                side_sign = Decimal("1") if signal.side == OrderSide.buy else Decimal("-1")
                positions[symbol] = current_pos_qty + (signal.quantity * side_sign)

            if run_id:'''
content = content.replace(update_pos_orig, update_pos_new)

# Fix indentation for the rest of the loop
loop_body_pattern = re.compile(r'            if len\(bars\) < 20:.*?(?=        final_result = \{)', re.DOTALL)
match = loop_body_pattern.search(content)
if match:
    body = match.group(0)
    indented_body = body.replace('\n            ', '\n                ')
    indented_body += '''          except Exception as e_sym:
                logger.exception(f"Symbol {symbol} failed: {e_sym}")
                if log: log.error(f"{symbol} failed: {e_sym}")
                results.append({"symbol": symbol, "action": "error", "reason": str(e_sym)})

'''
    content = content[:match.start()] + indented_body + content[match.end():]

# 4. Entry point loop
entry_orig = '''    return asyncio.run(_execute_async('''
entry_new = '''    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(_execute_async('''
content = content.replace(entry_orig, entry_new)

with open('app/worker/tasks.py', 'w') as f:
    f.write(content)
print('tasks.py rewritten successfully')
