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

    def place_order(self, order: OrderIntent) -> OrderResult:
        from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

        side = AlpacaSide.BUY if order.side == OrderSide.buy else AlpacaSide.SELL

        if order.order_type == OrderType.market:
            req = MarketOrderRequest(
                symbol=order.symbol,
                qty=float(order.quantity),
                side=side,
                time_in_force=TimeInForce.DAY,
            )
        else:
            if order.limit_price is None:
                raise ValueError("limit_price required for limit orders")
            req = LimitOrderRequest(
                symbol=order.symbol,
                qty=float(order.quantity),
                side=side,
                time_in_force=TimeInForce.DAY,
                limit_price=float(order.limit_price),
            )

        try:
            result = self._client.submit_order(req)
        except Exception as exc:
            # Catches APIError (insufficient buying power, pattern-day-trader block, etc.)
            raise RuntimeError(f"Alpaca order submission failed for {order.symbol}: {exc}") from exc

        fill_price = None
        if result.filled_avg_price is not None:
            try:
                fill_price = Decimal(str(result.filled_avg_price))
            except Exception:
                pass

        status_val = result.status.value if hasattr(result.status, "value") else str(result.status)
        return OrderResult(
            order_id=str(result.id),
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            fill_price=fill_price,
            estimated_price=order.estimated_price,
            broker_status=status_val,
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
