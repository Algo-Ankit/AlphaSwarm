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

    def place_order(
        self, order: OrderIntent, client_order_id: str | None = None
    ) -> OrderResult: ...
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

        from alpaca.trading.enums import OrderSide as AlpacaSide
        from alpaca.trading.enums import TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

        side = AlpacaSide.BUY if order.side == OrderSide.buy else AlpacaSide.SELL
        tif = TimeInForce.GTC if "-" in order.symbol else TimeInForce.DAY

        # Format as string to preserve precision up to 9 decimals, avoiding Python float math errors
        qty_str = f"{order.quantity:.9f}".rstrip("0").rstrip(".")

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
        leg_class = bracket_order_class(
            order.symbol, order.stop_loss_price, order.take_profit_price
        )
        if leg_class is None and (
            order.stop_loss_price is not None or order.take_profit_price is not None
        ):
            logger.warning(
                "Exit legs requested for %s but not supported (crypto) — placing plain order without "
                "broker-side stop/take.",
                order.symbol,
            )
        if leg_class is not None:
            from alpaca.trading.enums import OrderClass
            from alpaca.trading.requests import StopLossRequest, TakeProfitRequest

            req_kwargs["order_class"] = (
                OrderClass.BRACKET if leg_class == "bracket" else OrderClass.OTO
            )
            # Preserve up to 4 decimals (FIX-API standard). round(x, 2) truncates
            # sub-dollar/penny-stock stops & takes to zero precision, mispricing legs
            # on instruments quoted in sub-penny increments.
            if order.take_profit_price is not None:
                tp_str = f"{float(order.take_profit_price):.4f}".rstrip("0").rstrip(".")
                req_kwargs["take_profit"] = TakeProfitRequest(limit_price=tp_str)
            if order.stop_loss_price is not None:
                sl_str = f"{float(order.stop_loss_price):.4f}".rstrip("0").rstrip(".")
                req_kwargs["stop_loss"] = StopLossRequest(stop_price=sl_str)

        if order.order_type == OrderType.market:
            req = MarketOrderRequest(**req_kwargs)
        else:
            if order.limit_price is None:
                raise ValueError("limit_price required for limit orders")
            limit_str = f"{order.limit_price:.9f}".rstrip("0").rstrip(".")
            req = LimitOrderRequest(**req_kwargs, limit_price=limit_str)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = self._client.submit_order(req)
                break
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                if status_code == 429 and attempt < max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                if status_code == 409 and client_order_id:
                    try:
                        result = self._client.get_order_by_client_id(req_kwargs["client_order_id"])
                        break
                    except Exception as _get_exc:
                        raise RuntimeError(f"Alpaca order 409 conflict, but failed to fetch: {_get_exc}") from exc
                raise RuntimeError(
                    f"Alpaca order submission failed for {order.symbol}: {exc}"
                ) from exc

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


# ── Indian equity symbol / instrument-key helpers ──────────────────────────────
# Strategies store Yahoo Finance suffixes (e.g. RELIANCE.NS / TCS.BO) so market
# data & backtesting work seamlessly, while Indian brokers expect bare symbols
# (Zerodha: RELIANCE, Angel One: RELIANCE-EQ, Upstox: NSE_EQ|INE002A01018).
def _strip_indian_suffix(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if s.endswith(".NS") or s.endswith(".BO"):
        return s[:-3]
    return s


# Upstox places orders by instrument_key (e.g. "NSE_EQ|INE002A01018"), not by
# trading symbol. We resolve symbol → instrument_key from Upstox's published
# instrument master, cached process-wide (it changes at most daily).
_UPSTOX_INSTRUMENTS_URL = (
    "https://assets.upstox.com/market-quote/instruments/exchange/{exchange}.json.gz"
)
# exchange (NSE/BSE) → {TRADING_SYMBOL: instrument_key}
_UPSTOX_INSTRUMENT_CACHE: dict[str, dict[str, str]] = {}

# Angel One SmartAPI places orders by (tradingsymbol, numeric symboltoken).
_ANGELONE_SCRIP_MASTER_URL = (
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
)
# exchange (NSE/BSE) → {CLEAN_SYMBOL: (tradingsymbol, token)}
_ANGELONE_INSTRUMENT_CACHE: dict[str, dict[str, tuple[str, str]]] = {}


def _load_angelone_instruments(exchange: str) -> dict[str, tuple[str, str]]:
    """Fetch + cache {clean_symbol: (tradingsymbol, token)} from Angel One Scrip Master."""
    exch = (exchange or "NSE").upper()
    if exch in _ANGELONE_INSTRUMENT_CACHE:
        return _ANGELONE_INSTRUMENT_CACHE[exch]

    import httpx

    try:
        resp = httpx.get(_ANGELONE_SCRIP_MASTER_URL, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()
        instruments = resp.json()
    except Exception as exc:
        raise RuntimeError(f"Could not load Angel One scrip master for {exch}: {exc}") from exc

    by_exch: dict[str, dict[str, tuple[str, str]]] = {"NSE": {}, "BSE": {}}
    for inst in instruments:
        exch_seg = (inst.get("exch_seg") or "").upper()
        if exch_seg not in by_exch:
            continue
        tsym = (inst.get("symbol") or "").upper()
        name = (inst.get("name") or "").upper()
        token = str(inst.get("token") or "").strip()
        if not tsym or not token:
            continue
        # Prefer EQ series entries when indexing bare equity names
        if tsym.endswith("-EQ") or name not in by_exch[exch_seg]:
            clean = tsym[:-3] if tsym.endswith("-EQ") else (name or tsym)
            by_exch[exch_seg][clean] = (tsym, token)
            by_exch[exch_seg][tsym] = (tsym, token)

    _ANGELONE_INSTRUMENT_CACHE.update(by_exch)
    return _ANGELONE_INSTRUMENT_CACHE.get(exch, {})


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
        clean_sym = _strip_indian_suffix(order.symbol)
        key = mapping.get(clean_sym)
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
            raise ValueError(
                f"Upstox order quantity must be a positive integer, got {order.quantity}"
            )

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

        order_id = None
        try:
            resp = self._order_api.place_order(body, api_version=self._api_version)
            order_id = getattr(getattr(resp, "data", None), "order_id", None)
        except ApiException as exc:
            if getattr(exc, "status", None) in (502, 503, 504, 408):
                import time
                time.sleep(1.0)
                try:
                    book_resp = self._order_api.get_order_book(api_version=self._api_version)
                    orders = getattr(book_resp, "data", None) or []
                    tag_to_find = body.tag
                    placed_order = next((o for o in orders if getattr(o, "tag", None) == tag_to_find), None)
                    if placed_order:
                        order_id = getattr(placed_order, "order_id", None)
                    else:
                        raise RuntimeError(f"Upstox 502 error, order not found in book: {exc}") from exc
                except Exception as _get_exc:
                    raise RuntimeError(f"Upstox 502 error, failed to check order book: {_get_exc}") from exc
            else:
                raise RuntimeError(f"Upstox order submission failed for {order.symbol}: {exc}") from exc

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
        for p in getattr(resp, "data", None) or []:
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
        available = (
            getattr(equity_seg, "available_margin", None) if equity_seg is not None else None
        )
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


class AngelOneExecutor:
    """
    Live NSE/BSE executor via Angel One SmartAPI (100% free API for retail quants).

    Paper/dry-run never reaches here — the worker only builds an executor for live
    runs, and the risk gate (verify_order_intent) runs in the worker BEFORE
    place_order is called. Refuses paper orders defensively.
    """

    def __init__(
        self,
        api_key: str,
        access_token: str,
        *,
        paper: bool = False,
        product: str = "DELIVERY",
        base_url: str = "https://apiconnect.angelone.in",
    ):
        if not access_token:
            raise ValueError(
                "Angel One trading requires an active session token. Connect Angel One "
                "in Settings → Broker Connections."
            )
        self._api_key = api_key
        self._access_token = access_token
        self._paper = paper
        self._product = product
        self._base_url = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "fe80::1",
            "X-PrivateKey": self._api_key,
        }

    def _resolve_instrument(self, order: OrderIntent) -> tuple[str, str]:
        """Resolve symbol to Angel One (tradingsymbol, numeric symboltoken)."""
        raw = order.symbol.strip().upper()
        if "|" in raw:
            tsym, token = raw.split("|", 1)
            return tsym, token.strip()
        clean = _strip_indian_suffix(raw)
        clean_base = clean[:-3] if clean.endswith("-EQ") else clean
        mapping = _load_angelone_instruments(order.exchange or "NSE")
        resolved = mapping.get(clean) or mapping.get(clean_base)
        if not resolved:
            raise RuntimeError(
                f"No Angel One instrument token found for {order.symbol} on {order.exchange}. "
                "Confirm the trading symbol is valid for NSE/BSE."
            )
        return resolved

    def place_order(self, order: OrderIntent, client_order_id: str | None = None) -> OrderResult:
        import httpx

        if order.is_paper:
            raise RuntimeError(
                "Refusing to route a paper-flagged order to live Angel One. Risk-gate bypass rejected."
            )

        quantity = int(order.quantity)
        if quantity <= 0:
            raise ValueError(f"Angel One order quantity must be positive integer, got {order.quantity}")

        tradingsymbol, symboltoken = self._resolve_instrument(order)
        is_limit = order.order_type == OrderType.limit
        price = float(order.limit_price) if (is_limit and order.limit_price is not None) else 0.0

        payload = {
            "variety": "NORMAL",
            "tradingsymbol": tradingsymbol,
            "symboltoken": symboltoken,
            "transactiontype": "BUY" if order.side == OrderSide.buy else "SELL",
            "exchange": (order.exchange or "NSE").upper(),
            "ordertype": "LIMIT" if is_limit else "MARKET",
            "producttype": self._product,
            "duration": "DAY",
            "price": str(price),
            "squareoff": "0",
            "stoploss": "0",
            "quantity": str(quantity),
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    f"{self._base_url}/rest/secure/angelbroking/order/v1/placeOrder",
                    headers=self._headers(),
                    json=payload,
                )
                data = resp.json()
                if not data.get("status") and data.get("message"):
                    raise RuntimeError(f"Angel One order rejected: {data.get('message')}")
                order_id = data.get("data", {}).get("orderid")
        except Exception as exc:
            raise RuntimeError(f"Angel One order placement failed for {order.symbol}: {exc}") from exc

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
        import httpx

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    f"{self._base_url}/rest/secure/angelbroking/order/v1/getPosition",
                    headers=self._headers(),
                )
                data = resp.json()
        except Exception as exc:
            raise RuntimeError(f"Angel One get_positions failed: {exc}") from exc

        positions: dict[str, Decimal] = {}
        items = data.get("data", []) or []
        for p in items:
            sym = p.get("tradingsymbol") or p.get("symbolname")
            qty = p.get("netqty") or p.get("quantity")
            if sym is not None and qty is not None:
                clean_sym = str(sym).upper().replace("-EQ", "")
                positions[clean_sym] = Decimal(str(qty))
        return positions

    def get_account(self) -> dict:
        import httpx

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    f"{self._base_url}/rest/secure/angelbroking/user/v1/getRMS",
                    headers=self._headers(),
                )
                data = resp.json()
        except Exception as exc:
            raise RuntimeError(f"Angel One get_account failed: {exc}") from exc

        funds = data.get("data", {}) or {}
        available = funds.get("net") or funds.get("availablecash") or funds.get("availablemargin") or "0"
        cash = str(available)
        return {
            "equity": cash,
            "cash": cash,
            "portfolio_value": cash,
            "buying_power": cash,
        }

    def cancel_order(self, order_id: str) -> None:
        import httpx

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    f"{self._base_url}/rest/secure/angelbroking/order/v1/cancelOrder",
                    headers=self._headers(),
                    json={"variety": "NORMAL", "orderid": order_id},
                )
                data = resp.json()
                if not data.get("status") and data.get("message"):
                    raise RuntimeError(f"Angel One cancel failed: {data.get('message')}")
        except Exception as exc:
            raise RuntimeError(f"Angel One cancel_order failed for {order_id}: {exc}") from exc


class ZerodhaExecutor:
    """
    Live NSE/BSE executor via Zerodha Kite Connect API.

    Paper/dry-run never reaches here — the risk gate (verify_order_intent) runs in the
    worker BEFORE place_order is called. Refuses paper orders defensively.
    """

    def __init__(
        self,
        api_key: str,
        access_token: str,
        *,
        paper: bool = False,
        product: str = "CNC",
        base_url: str = "https://api.kite.trade",
    ):
        if not access_token:
            raise ValueError(
                "Zerodha Kite live trading requires an OAuth access token. Connect Zerodha "
                "in Settings → Broker Connections."
            )
        self._api_key = api_key
        self._access_token = access_token
        self._paper = paper
        self._product = product
        self._base_url = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "X-Kite-Version": "3",
            "Authorization": f"token {self._api_key}:{self._access_token}",
        }

    def place_order(self, order: OrderIntent, client_order_id: str | None = None) -> OrderResult:
        import httpx

        if order.is_paper:
            raise RuntimeError(
                "Refusing to route a paper-flagged order to live Zerodha. Risk-gate bypass rejected."
            )

        quantity = int(order.quantity)
        if quantity <= 0:
            raise ValueError(f"Zerodha order quantity must be positive integer, got {order.quantity}")

        is_limit = order.order_type == OrderType.limit
        price = float(order.limit_price) if (is_limit and order.limit_price is not None) else 0.0

        payload = {
            "tradingsymbol": _strip_indian_suffix(order.symbol),
            "exchange": (order.exchange or "NSE").upper(),
            "transaction_type": "BUY" if order.side == OrderSide.buy else "SELL",
            "order_type": "LIMIT" if is_limit else "MARKET",
            "quantity": quantity,
            "product": self._product,
            "validity": "DAY",
            "price": price if is_limit else 0,
            "tag": (client_order_id or "alphaswarm")[:20],
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    f"{self._base_url}/orders/regular",
                    headers=self._headers(),
                    data=payload,
                )
                data = resp.json()
                if data.get("status") == "error":
                    raise RuntimeError(f"Zerodha order rejected: {data.get('message')}")
                order_id = data.get("data", {}).get("order_id")
        except Exception as exc:
            raise RuntimeError(f"Zerodha order placement failed for {order.symbol}: {exc}") from exc

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
        import httpx

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    f"{self._base_url}/portfolio/positions",
                    headers=self._headers(),
                )
                data = resp.json()
        except Exception as exc:
            raise RuntimeError(f"Zerodha get_positions failed: {exc}") from exc

        positions: dict[str, Decimal] = {}
        net_positions = data.get("data", {}).get("net", []) or []
        for p in net_positions:
            sym = p.get("tradingsymbol")
            qty = p.get("quantity")
            if sym is not None and qty is not None:
                positions[str(sym).upper()] = Decimal(str(qty))
        return positions

    def get_account(self) -> dict:
        import httpx

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    f"{self._base_url}/user/margins",
                    headers=self._headers(),
                )
                data = resp.json()
        except Exception as exc:
            raise RuntimeError(f"Zerodha get_account failed: {exc}") from exc

        equity = data.get("data", {}).get("equity", {}) or {}
        available = equity.get("available", {}).get("live_balance", 0)
        cash = str(available)
        return {
            "equity": cash,
            "cash": cash,
            "portfolio_value": cash,
            "buying_power": cash,
        }

    def cancel_order(self, order_id: str) -> None:
        import httpx

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.delete(
                    f"{self._base_url}/orders/regular/{order_id}",
                    headers=self._headers(),
                )
                data = resp.json()
                if data.get("status") == "error":
                    raise RuntimeError(f"Zerodha cancel failed: {data.get('message')}")
        except Exception as exc:
            raise RuntimeError(f"Zerodha cancel_order failed for {order_id}: {exc}") from exc


# ── Social copy-trading: signal fan-out ───────────────────────────────────────
# When a published strategy generates a signal, the same signal is replicated to
# every subscriber copying it, sized proportionally to the capital each subscriber
# allocated. Each copied order runs through the SAME risk gate (verify_order_intent)
# as a first-party order and executes in the subscriber's OWN broker account — the
# platform never holds funds or co-mingles positions.

# Mirrors risk.GAP_SAFETY_MARGIN so copy sizing leaves headroom for the cap price
# the risk gate uses (estimated_price inflated by this margin). Without it a copy
# sized exactly to allocated_capital would be rejected by the order-notional check.
_COPY_SAFETY_MARGIN = Decimal("0.03")


def copy_order_quantity(
    *,
    signal_quantity: Decimal,
    creator_capital_base: Decimal,
    allocated_capital: Decimal,
    price: Decimal,
    whole_shares: bool,
    safety_margin: Decimal = _COPY_SAFETY_MARGIN,
) -> Decimal:
    """
    Proportionally size a copied order for a subscriber.

    The subscriber's order quantity scales with how much capital they allocated
    relative to the creator's per-position capital base:

        qty = signal_quantity * (allocated_capital / creator_capital_base)

    The result is then clamped so a single copied order never deploys more than the
    subscriber's allocated capital (using a gap-inflated cap price to stay inside the
    risk gate's order-notional check), and floored to whole shares for exchanges that
    forbid fractional equity (NSE/BSE). Returns Decimal("0") when no valid order can
    be sized (which the caller skips).
    """
    if creator_capital_base <= 0 or allocated_capital <= 0 or price <= 0 or signal_quantity <= 0:
        return Decimal("0")

    scale = allocated_capital / creator_capital_base
    qty = signal_quantity * scale

    cap_price = price * (Decimal("1") + safety_margin)
    max_qty_by_capital = allocated_capital / cap_price
    if qty > max_qty_by_capital:
        qty = max_qty_by_capital

    if whole_shares:
        qty = Decimal(int(qty))  # floor to a whole share

    return qty if qty > 0 else Decimal("0")


async def fan_out_to_subscribers(
    pool,
    *,
    creator_tenant_id: str,
    strategy_id: str,
    exchange: str,
    signal,
    creator_risk,
    dry_run: bool,
    run_id: str | None = None,
    log=None,
) -> list[dict]:
    """
    Replicate a creator's signal to every active subscriber of the strategy.

    Thread/concurrency safety: each subscriber's order is placed inside its OWN
    transaction guarded by a per-(subscriber, strategy) Postgres advisory lock, so
    two concurrent creator runs can never double-place a copied trade (the same
    TOCTOU defence the creator path uses). Subscribers are processed independently —
    one subscriber's failure (bad broker creds, risk rejection) never affects another.

    Each copy:
      * is sized by copy_order_quantity() from the subscriber's allocated_capital,
      * passes through verify_order_intent() with a risk profile capped to that
        allocation,
      * executes in the subscriber's own broker account (live) or as a dry-run
        (paper, or when the subscriber has no live broker for this exchange).
    """
    from uuid import UUID

    from app.db.repositories.brokers import BrokerRepo
    from app.domain.broker_routing import allows_fractional_shares, brokers_for_exchange
    from app.domain.market_data import MarketState
    from app.domain.market_hours import exchange_timezone, get_session_status
    from app.domain.models import OrderIntent, OrderResult
    from app.domain.risk import verify_order_intent
    from app.services.broker_crypto import decrypt_key
    from app.services.notifications import create_notification
    from app.worker.tasks import _write_order_async

    subs = await pool.fetch(
        """
        SELECT ss.subscriber_tenant_id, ss.subscriber_user_id, ss.allocated_capital
        FROM strategy_subscriptions ss
        JOIN public_strategies ps ON ps.id = ss.public_strategy_id
        WHERE ps.strategy_id = $1
          AND ss.is_active = TRUE
          AND ss.subscriber_tenant_id <> $2
        """,
        UUID(strategy_id),
        UUID(creator_tenant_id),
    )
    if not subs:
        return []

    allowed_brokers = brokers_for_exchange(exchange)
    whole_shares = not allows_fractional_shares(exchange)
    exchange_tz = exchange_timezone(exchange)
    session = get_session_status(exchange)
    creator_base = Decimal(str(creator_risk.max_position_notional * creator_risk.max_open_positions))
    price = Decimal(str(signal.estimated_price))
    symbol = signal.symbol.upper()

    results: list[dict] = []

    for sub in subs:
        sub_tenant = str(sub["subscriber_tenant_id"])
        sub_user = str(sub["subscriber_user_id"]) if sub["subscriber_user_id"] else None
        allocated = Decimal(str(sub["allocated_capital"]))

        try:
            qty = copy_order_quantity(
                signal_quantity=Decimal(str(signal.quantity)),
                creator_capital_base=creator_base,
                allocated_capital=allocated,
                price=price,
                whole_shares=whole_shares,
            )
            if qty <= 0:
                results.append(
                    {
                        "tenant_id": sub_tenant,
                        "action": "skipped",
                        "reason": "allocation too small to size a whole-share order",
                    }
                )
                continue

            # Resolve the subscriber's broker creds for this exchange. Missing creds
            # (or a paper connection) demote the copy to a dry-run rather than failing
            # — a subscriber without the live broker still gets a paper copy.
            broker_rows = await BrokerRepo(pool, UUID(sub_tenant)).get_all()
            broker_row = next(
                (
                    b
                    for name in allowed_brokers
                    for b in broker_rows
                    if b["broker"] == name and b.get("is_active", True)
                ),
                None,
            )
            subscriber_paper = dry_run or broker_row is None or bool(broker_row.get("is_paper"))

            # Scale daily notional so high-turnover strategies don't strand subscribers
            scale = allocated / creator_base if creator_base > 0 else Decimal("0")
            scaled_daily = Decimal(str(creator_risk.max_daily_notional)) * scale

            copy_risk = creator_risk.model_copy(
                update={
                    "max_order_notional": Decimal(str(creator_risk.max_order_notional)) * scale,
                    "max_position_notional": Decimal(str(creator_risk.max_position_notional)) * scale,
                    "max_daily_notional": scaled_daily,
                    "allowed_symbols": sorted(
                        {*(s.upper() for s in creator_risk.allowed_symbols), symbol}
                    ),
                    "paper_trading_only": subscriber_paper,
                }
            )

            copy_signal = OrderIntent(
                strategy_id=strategy_id,
                symbol=symbol,
                exchange=exchange,
                side=signal.side,
                quantity=qty,
                order_type=signal.order_type,
                limit_price=signal.limit_price,
                stop_loss_price=signal.stop_loss_price,
                take_profit_price=signal.take_profit_price,
                estimated_price=price,
                is_paper=subscriber_paper,
            )

            executor = None
            if not subscriber_paper and broker_row is not None:
                access_token = (
                    decrypt_key(broker_row["access_token"])
                    if broker_row.get("access_token")
                    else None
                )
                executor = get_executor(
                    broker_row["broker"],
                    api_key=decrypt_key(broker_row["key_encrypted"])
                    if broker_row.get("key_encrypted")
                    else "",
                    secret_key=decrypt_key(broker_row["secret_encrypted"])
                    if broker_row.get("secret_encrypted")
                    else "",
                    paper=bool(broker_row.get("is_paper")),
                    access_token=access_token,
                )

            async with pool.acquire() as conn:
                async with conn.transaction():
                    # Per-(subscriber, strategy) advisory lock — serialize concurrent
                    # copies so two creator runs can't both pass the caps and double-place.
                    await conn.execute(
                        "SELECT pg_advisory_xact_lock(hashtext($1::text), hashtext($2::text))",
                        sub_tenant,
                        strategy_id,
                    )

                    pos_row = await conn.fetchrow(
                        "SELECT quantity FROM positions WHERE tenant_id = $1 AND strategy_id = $2 AND symbol = $3",
                        UUID(sub_tenant),
                        UUID(strategy_id),
                        symbol,
                    )
                    cur_qty = Decimal(str(pos_row["quantity"])) if pos_row else Decimal("0")
                    cur_pos = float(cur_qty) if cur_qty != 0 else None
                    cur_val = float(abs(cur_qty)) * float(price)

                    open_count = (
                        await conn.fetchval(
                            "SELECT COUNT(*) FROM positions WHERE tenant_id = $1 AND strategy_id = $2 AND quantity <> 0",
                            UUID(sub_tenant),
                            UUID(strategy_id),
                        )
                        or 0
                    )

                    today_row = await conn.fetchrow(
                        """
                        SELECT COALESCE(SUM(estimated_notional), 0) AS total
                        FROM orders
                        WHERE tenant_id = $1 AND strategy_id = $2
                          AND broker_status IN ('filled','open','pending','accepted','partially_filled','dry_run')
                          AND created_at >= (date_trunc('day', now() AT TIME ZONE $3) AT TIME ZONE $3)
                        """,
                        UUID(sub_tenant),
                        UUID(strategy_id),
                        exchange_tz,
                    )
                    today_notional = Decimal(str(today_row["total"])) if today_row else Decimal("0")

                    market_state = MarketState(
                        exchange=exchange,
                        is_open=True if subscriber_paper else session == "open",
                        session_status="paper" if subscriber_paper else session,
                        today_executed_notional=today_notional,
                    )

                    risk_result = verify_order_intent(
                        copy_signal,
                        copy_risk,
                        market_state,
                        current_position=cur_pos,
                        current_position_value=cur_val,
                        open_positions_count=int(open_count),
                    )
                    if not risk_result.approved:
                        results.append(
                            {
                                "tenant_id": sub_tenant,
                                "action": "rejected",
                                "reason": risk_result.reason,
                            }
                        )
                        continue

                    if subscriber_paper:
                        order_result = OrderResult(
                            order_id=None,
                            symbol=symbol,
                            side=copy_signal.side,
                            quantity=qty,
                            fill_price=None,
                            estimated_price=price,
                            broker_status="dry_run",
                            is_paper=True,
                        )
                    else:
                        import asyncio
                        client_order_id = f"cp_{sub_tenant[:8]}_{run_id[:8]}" if run_id else None
                        order_result = await asyncio.to_thread(executor.place_order, copy_signal, client_order_id)

                    await _write_order_async(
                        conn,
                        sub_tenant,
                        strategy_id,
                        None,
                        copy_signal,
                        order_result,
                        "approved",
                        risk_result.reason,
                    )

                    try:
                        await create_notification(
                            conn,
                            tenant_id=sub_tenant,
                            user_id=sub_user,
                            type="trade_executed",
                            title=f"Copied {copy_signal.side.value.upper()} {symbol} × {qty}",
                            body=(
                                f"Copy-trade {order_result.broker_status} @ ~{price} "
                                f"(allocation {allocated})"
                            ),
                            entity_type="strategy",
                            entity_id=strategy_id,
                        )
                    except Exception as _nexc:
                        logger.warning(
                            "copy-trade notification failed for %s: %s", sub_tenant, _nexc
                        )

                    results.append(
                        {
                            "tenant_id": sub_tenant,
                            "action": copy_signal.side.value,
                            "quantity": str(qty),
                            "broker_status": order_result.broker_status,
                        }
                    )

        except Exception as exc:
            logger.warning("copy-trade fan-out to subscriber %s failed: %s", sub_tenant, exc)
            results.append({"tenant_id": sub_tenant, "action": "error", "reason": str(exc)})

    return results


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
    if name == "zerodha":
        return ZerodhaExecutor(api_key=api_key, access_token=access_token or "", paper=paper)
    if name in ("angelone", "angel_one", "angel"):
        return AngelOneExecutor(api_key=api_key, access_token=access_token or "", paper=paper)
    raise ValueError(
        f"Unsupported broker '{broker}'. Supported: alpaca, upstox, zerodha, angelone."
    )
