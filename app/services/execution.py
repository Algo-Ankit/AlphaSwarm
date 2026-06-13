"""
Execution services — synchronous, Celery-compatible.
One executor per strategy run. Do not share across threads.

Broker selection is exchange-driven (see app/domain/broker_routing.py). Use
get_executor(broker, ...) rather than instantiating a concrete executor, so a
strategy on NSE/BSE never silently routes to a US broker.
"""
import logging
from decimal import Decimal
from typing import Protocol

from app.domain.models import OrderIntent, OrderResult, OrderSide, OrderType

logger = logging.getLogger(__name__)


class BrokerExecutor(Protocol):
    """Minimal contract every broker executor must satisfy."""

    def place_order(self, order: OrderIntent, client_order_id: str | None = None) -> OrderResult: ...
    def get_positions(self) -> dict[str, Decimal]: ...
    def get_account(self) -> dict: ...
    def cancel_order(self, order_id: str) -> None: ...


def bracket_order_class(symbol: str, stop_loss_price, take_profit_price) -> str | None:
    """
    Decide the Alpaca order_class for broker-side exit legs (which survive a server
    crash). Returns "bracket", "oto", or None to skip broker legs.

    - None  → crypto (Alpaca has no bracket/OTO for crypto) or no legs requested.
    - "oto" → exactly one leg (BRACKET requires BOTH; a single leg must be OTO).
    - "bracket" → both stop-loss and take-profit legs.
    """
    is_crypto = "/" in symbol or "-" in symbol
    has_sl = stop_loss_price is not None
    has_tp = take_profit_price is not None
    if is_crypto or not (has_sl or has_tp):
        return None
    return "bracket" if (has_sl and has_tp) else "oto"


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

        # Broker-side exit legs (bracket/OTO) so stop-loss / take-profit survive a
        # server or worker crash. Skipped for crypto (unsupported by Alpaca).
        leg_class = bracket_order_class(order.symbol, order.stop_loss_price, order.take_profit_price)
        if leg_class is None and (order.stop_loss_price is not None or order.take_profit_price is not None):
            logger.warning(
                "Exit legs requested for %s but not supported (crypto) — placing plain order without "
                "broker-side stop/take.", order.symbol,
            )
        if leg_class is not None:
            from alpaca.trading.enums import OrderClass
            from alpaca.trading.requests import TakeProfitRequest, StopLossRequest
            req_kwargs["order_class"] = OrderClass.BRACKET if leg_class == "bracket" else OrderClass.OTO
            # Round to the penny — Alpaca rejects sub-penny prices on US equities ≥ $1.
            if order.take_profit_price is not None:
                req_kwargs["take_profit"] = TakeProfitRequest(limit_price=str(round(float(order.take_profit_price), 2)))
            if order.stop_loss_price is not None:
                req_kwargs["stop_loss"] = StopLossRequest(stop_price=str(round(float(order.stop_loss_price), 2)))

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


class UpstoxExecutor:
    """
    Indian-market (NSE/BSE) executor — placeholder.

    Live Indian execution requires the Upstox SDK + OAuth flow, which is not wired
    yet. This class exists so exchange-driven routing fails LOUDLY and clearly for
    NSE/BSE live trading instead of silently sending Indian orders to a US broker.
    Paper/dry-run never reaches here (the worker builds no executor in dry_run).
    """

    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        self._paper = paper

    def _not_implemented(self):
        raise NotImplementedError(
            "Live trading on Indian markets (NSE/BSE) via Upstox is not yet available. "
            "Paper-trade and backtest this strategy now; live Upstox execution is on the roadmap."
        )

    def place_order(self, order: OrderIntent, client_order_id: str | None = None) -> OrderResult:
        self._not_implemented()

    def get_positions(self) -> dict[str, Decimal]:
        return {}

    def get_account(self) -> dict:
        self._not_implemented()

    def cancel_order(self, order_id: str) -> None:
        self._not_implemented()


def get_executor(broker: str, *, api_key: str, secret_key: str, paper: bool = True) -> BrokerExecutor:
    """
    Factory: return the executor for a broker key (see broker_routing.broker_for_exchange).
    Raises ValueError for an unknown broker so misconfiguration fails fast.
    """
    name = (broker or "alpaca").lower()
    if name == "alpaca":
        return AlpacaExecutor(api_key=api_key, secret_key=secret_key, paper=paper)
    if name == "upstox":
        return UpstoxExecutor(api_key=api_key, secret_key=secret_key, paper=paper)
    raise ValueError(f"Unsupported broker '{broker}'. Supported: alpaca, upstox.")
