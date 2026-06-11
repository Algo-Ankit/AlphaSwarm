"""
Alpaca execution service — synchronous, Celery-compatible.
One AlpacaExecutor per strategy run. Do not share across threads.
"""
import logging
from decimal import Decimal

from app.domain.models import OrderIntent, OrderResult, OrderSide, OrderType

logger = logging.getLogger(__name__)


class AlpacaExecutor:

    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        from alpaca.trading.client import TradingClient
        self._client = TradingClient(api_key, secret_key, paper=paper)
        self._paper = paper

    def place_order(self, order: OrderIntent, client_order_id: str | None = None) -> OrderResult:
        import time
        from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

        side = AlpacaSide.BUY if order.side == OrderSide.buy else AlpacaSide.SELL
        tif = TimeInForce.GTC if "-" in order.symbol else TimeInForce.DAY
        
        # Format as string to preserve precision up to 9 decimals, avoiding Python float math errors
        qty_str = f"{order.quantity:.9f}".rstrip('0').rstrip('.')

        req_kwargs = {
            "symbol": order.symbol,
            "qty": qty_str,
            "side": side,
            "time_in_force": tif,
        }
        if client_order_id:
            req_kwargs["client_order_id"] = client_order_id[:48]

        if order.order_type == OrderType.market:
            req = MarketOrderRequest(**req_kwargs)
        else:
            if order.limit_price is None:
                raise ValueError("limit_price required for limit orders")
            limit_str = f"{order.limit_price:.9f}".rstrip('0').rstrip('.')
            req = LimitOrderRequest(**req_kwargs, limit_price=limit_str)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = self._client.submit_order(req)
                break
            except Exception as exc:
                if "429" in str(exc) and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                # If it's a conflict (409) for client_order_id, it means we already placed it.
                # Unfortunately Alpaca SDK might just throw a generic APIError, but let's re-raise.
                raise RuntimeError(f"Alpaca order submission failed for {order.symbol}: {exc}") from exc

        fill_price = None
        if result.filled_avg_price is not None:
            try:
                fill_price = Decimal(str(result.filled_avg_price))
            except Exception:
                pass

        # Normalize status to standard internal strings
        status_val = result.status.value if hasattr(result.status, "value") else str(result.status)
        if status_val in ("accepted_for_bidding", "pending_new", "accepted", "new"):
            normalized_status = "pending"
        elif status_val in ("filled", "partially_filled"):
            normalized_status = "filled"
        else:
            normalized_status = status_val

        return OrderResult(
            order_id=str(result.id),
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            fill_price=fill_price,
            estimated_price=order.estimated_price,
            broker_status=normalized_status,
            is_paper=self._paper,
        )

    def get_positions(self) -> dict[str, Decimal]:
        return {p.symbol: Decimal(str(p.qty)) for p in self._client.get_all_positions()}

    def get_account(self) -> dict:
        a = self._client.get_account()
        return {
            "equity": str(a.equity),
            "cash": str(a.cash),
            "portfolio_value": str(a.portfolio_value),
            "buying_power": str(a.buying_power),
        }

    def cancel_order(self, order_id: str) -> None:
        self._client.cancel_order_by_id(order_id)
