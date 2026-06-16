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
            # Preserve up to 4 decimals (FIX-API standard). round(x, 2) truncates
            # sub-dollar/penny-stock stops & takes to zero precision, mispricing legs
            # on instruments quoted in sub-penny increments.
            if order.take_profit_price is not None:
                tp_str = f"{float(order.take_profit_price):.4f}".rstrip('0').rstrip('.')
                req_kwargs["take_profit"] = TakeProfitRequest(limit_price=tp_str)
            if order.stop_loss_price is not None:
                sl_str = f"{float(order.stop_loss_price):.4f}".rstrip('0').rstrip('.')
                req_kwargs["stop_loss"] = StopLossRequest(stop_price=sl_str)

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

        # Quantity the broker ACTUALLY filled (may be < requested on a partial fill).
        # Preserved separately so downstream position sizing never assumes we got
        # the full requested size. None when the broker hasn't reported a qty yet.
        filled_quantity = None
        if getattr(result, "filled_qty", None) is not None:
            try:
                filled_quantity = Decimal(str(result.filled_qty))
            except Exception:
                pass

        # Normalize status to standard internal strings.
        # IMPORTANT: 'partially_filled' is kept DISTINCT from 'filled'. Collapsing
        # the two (the old behaviour) silently overstated the position by the
        # unfilled remainder — a fund-destroying sizing bug. Callers must inspect
        # filled_quantity / is_complete_fill before treating an order as done.
        status_val = result.status.value if hasattr(result.status, "value") else str(result.status)
        if status_val in ("accepted_for_bidding", "pending_new", "accepted", "new"):
            normalized_status = "pending"
        elif status_val == "filled":
            normalized_status = "filled"
        elif status_val == "partially_filled":
            normalized_status = "partially_filled"
        else:
            normalized_status = status_val

        return OrderResult(
            order_id=str(result.id),
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            filled_quantity=filled_quantity,
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


# ── Upstox instrument-key resolution ──────────────────────────────────────────
# Upstox places orders by instrument_key (e.g. "NSE_EQ|INE002A01018"), not by
# trading symbol. We resolve symbol → instrument_key from Upstox's published
# instrument master, cached process-wide (it changes at most daily).
_UPSTOX_INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/{exchange}.json.gz"
# exchange (NSE/BSE) → {TRADING_SYMBOL: instrument_key}
_UPSTOX_INSTRUMENT_CACHE: dict[str, dict[str, str]] = {}


def _load_upstox_instruments(exchange: str) -> dict[str, str]:
    """Fetch + cache the {trading_symbol: instrument_key} map for an exchange's equity segment."""
    exch = exchange.upper()
    if exch in _UPSTOX_INSTRUMENT_CACHE:
        return _UPSTOX_INSTRUMENT_CACHE[exch]

    import gzip
    import json

    import httpx

    url = _UPSTOX_INSTRUMENTS_URL.format(exchange=exch)
    try:
        resp = httpx.get(url, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()
        raw = gzip.decompress(resp.content)
        instruments = json.loads(raw)
    except Exception as exc:
        raise RuntimeError(f"Could not load Upstox instrument master for {exch}: {exc}") from exc

    eq_segment = f"{exch}_EQ"
    mapping: dict[str, str] = {}
    for inst in instruments:
        if inst.get("segment") == eq_segment and inst.get("trading_symbol"):
            mapping[inst["trading_symbol"].upper()] = inst["instrument_key"]
    _UPSTOX_INSTRUMENT_CACHE[exch] = mapping
    return mapping


class UpstoxExecutor:
    """
    Live NSE/BSE executor via the official upstox-python-sdk (OAuth access token).

    Paper/dry-run never reaches here — the worker only builds an executor for live
    runs, and the risk gate (verify_order_intent) runs in the worker BEFORE
    place_order is called. As a defensive backstop, place_order refuses to send a
    paper-flagged order to the live broker (Upstox has no paper environment).
    """

    # Upstox order product codes: D = delivery (CNC), I = intraday (MIS).
    def __init__(self, access_token: str, *, paper: bool = False, product: str = "D"):
        if not access_token:
            raise ValueError(
                "Upstox live trading requires an OAuth access token. Connect Upstox "
                "in Settings → Broker Connections (the access token may have expired — re-login)."
            )
        import upstox_client

        self._paper = paper
        self._product = product
        config = upstox_client.Configuration()
        config.access_token = access_token
        self._api_client = upstox_client.ApiClient(config)
        self._order_api = upstox_client.OrderApi(self._api_client)
        self._portfolio_api = upstox_client.PortfolioApi(self._api_client)
        self._user_api = upstox_client.UserApi(self._api_client)
        self._api_version = "v2"

    def _instrument_key(self, order: OrderIntent) -> str:
        # Allow callers to pass a pre-resolved instrument_key directly.
        if "|" in order.symbol:
            return order.symbol
        mapping = _load_upstox_instruments(order.exchange or "NSE")
        key = mapping.get(order.symbol.upper())
        if not key:
            raise RuntimeError(
                f"No Upstox instrument found for {order.symbol} on {order.exchange}. "
                "Confirm the trading symbol is correct for this exchange."
            )
        return key

    def place_order(self, order: OrderIntent, client_order_id: str | None = None) -> OrderResult:
        import upstox_client
        from upstox_client.rest import ApiException

        # Defensive risk backstop: a paper order must never reach the live broker.
        # The authoritative gate (verify_order_intent) already ran in the worker.
        if order.is_paper:
            raise RuntimeError(
                "Refusing to route a paper-flagged order to live Upstox (no paper environment). "
                "This indicates a risk-gate bypass — order rejected."
            )

        # NSE/BSE cash equity is whole-share only; verify_order_intent enforces this
        # upstream, but Upstox also requires an integer quantity.
        quantity = int(order.quantity)
        if quantity <= 0:
            raise ValueError(f"Upstox order quantity must be a positive integer, got {order.quantity}")

        is_limit = order.order_type == OrderType.limit
        price = float(order.limit_price) if (is_limit and order.limit_price is not None) else 0.0

        body = upstox_client.PlaceOrderRequest(
            quantity=quantity,
            product=self._product,
            validity="DAY",
            price=price,
            tag=(client_order_id or "alphaswarm")[:20],
            instrument_token=self._instrument_key(order),
            order_type="LIMIT" if is_limit else "MARKET",
            transaction_type="BUY" if order.side == OrderSide.buy else "SELL",
            disclosed_quantity=0,
            trigger_price=0.0,
            is_amo=False,
        )

        try:
            resp = self._order_api.place_order(body, api_version=self._api_version)
        except ApiException as exc:
            raise RuntimeError(f"Upstox order submission failed for {order.symbol}: {exc}") from exc

        order_id = getattr(getattr(resp, "data", None), "order_id", None)

        # Upstox returns an order id on acceptance; fills are reported
        # asynchronously (poll get_positions / order book). Treat as pending.
        return OrderResult(
            order_id=str(order_id) if order_id else None,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            filled_quantity=None,
            fill_price=None,
            estimated_price=order.estimated_price,
            broker_status="pending",
            is_paper=False,
        )

    def get_positions(self) -> dict[str, Decimal]:
        from upstox_client.rest import ApiException

        try:
            resp = self._portfolio_api.get_positions(api_version=self._api_version)
        except ApiException as exc:
            raise RuntimeError(f"Upstox get_positions failed: {exc}") from exc

        positions: dict[str, Decimal] = {}
        for p in (getattr(resp, "data", None) or []):
            symbol = getattr(p, "trading_symbol", None) or getattr(p, "tradingsymbol", None)
            qty = getattr(p, "quantity", None)
            if symbol is not None and qty is not None:
                positions[str(symbol).upper()] = Decimal(str(qty))
        return positions

    def get_account(self) -> dict:
        from upstox_client.rest import ApiException

        try:
            resp = self._user_api.get_user_fund_margin(api_version=self._api_version)
        except ApiException as exc:
            raise RuntimeError(f"Upstox get_user_fund_margin failed: {exc}") from exc

        data = getattr(resp, "data", None) or {}
        # Upstox returns a dict keyed by segment ('equity', 'commodity').
        equity_seg = data.get("equity") if isinstance(data, dict) else None
        available = getattr(equity_seg, "available_margin", None) if equity_seg is not None else None
        if available is None and isinstance(equity_seg, dict):
            available = equity_seg.get("available_margin")
        cash = str(available) if available is not None else "0"
        return {
            "equity": cash,
            "cash": cash,
            "portfolio_value": cash,
            "buying_power": cash,
        }

    def cancel_order(self, order_id: str) -> None:
        from upstox_client.rest import ApiException

        try:
            self._order_api.cancel_order(order_id, api_version=self._api_version)
        except ApiException as exc:
            raise RuntimeError(f"Upstox cancel_order failed for {order_id}: {exc}") from exc


def get_executor(
    broker: str,
    *,
    api_key: str,
    secret_key: str,
    paper: bool = True,
    access_token: str | None = None,
) -> BrokerExecutor:
    """
    Factory: return the executor for a broker key (see broker_routing.broker_for_exchange).
    Raises ValueError for an unknown broker so misconfiguration fails fast.

    `access_token` is required for OAuth brokers (Upstox); `api_key`/`secret_key`
    are used by static-key brokers (Alpaca).
    """
    name = (broker or "alpaca").lower()
    if name == "alpaca":
        return AlpacaExecutor(api_key=api_key, secret_key=secret_key, paper=paper)
    if name == "upstox":
        return UpstoxExecutor(access_token=access_token or "", paper=paper)
    raise ValueError(f"Unsupported broker '{broker}'. Supported: alpaca, upstox.")
