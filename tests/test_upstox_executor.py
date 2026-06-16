"""
UpstoxExecutor guard tests — focus on the risk/safety backstops, not live I/O.
The Upstox SDK is stubbed so these run without upstox-python-sdk installed.

Runnable with pytest OR directly:  python tests/test_upstox_executor.py
"""

import sys
import types
from decimal import Decimal

import pytest

from app.domain.models import OrderIntent, OrderSide, OrderType


def _install_fake_upstox():
    """Install a minimal fake `upstox_client` package so the executor imports."""
    if "upstox_client" in sys.modules:
        return

    mod = types.ModuleType("upstox_client")

    class Configuration:
        def __init__(self):
            self.access_token = None

    class ApiClient:
        def __init__(self, config):
            self.config = config

    class _Api:
        def __init__(self, *a, **k):
            pass

    class PlaceOrderRequest:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    mod.Configuration = Configuration
    mod.ApiClient = ApiClient
    mod.OrderApi = _Api
    mod.PortfolioApi = _Api
    mod.UserApi = _Api
    mod.PlaceOrderRequest = PlaceOrderRequest

    rest = types.ModuleType("upstox_client.rest")

    class ApiException(Exception):
        pass

    rest.ApiException = ApiException
    mod.rest = rest
    sys.modules["upstox_client"] = mod
    sys.modules["upstox_client.rest"] = rest


def _make_order(is_paper: bool) -> OrderIntent:
    return OrderIntent(
        strategy_id="s1",
        symbol="RELIANCE",
        exchange="NSE",
        side=OrderSide.buy,
        quantity=Decimal("10"),
        order_type=OrderType.market,
        estimated_price=Decimal("2900"),
        is_paper=is_paper,
    )


def test_requires_access_token():
    _install_fake_upstox()
    from app.services.execution import UpstoxExecutor

    with pytest.raises(ValueError):
        UpstoxExecutor(access_token="")


def test_refuses_paper_order_to_live_broker():
    # A paper-flagged order must never be routed to the live Upstox API.
    _install_fake_upstox()
    from app.services.execution import UpstoxExecutor

    ex = UpstoxExecutor(access_token="tok")
    with pytest.raises(RuntimeError, match="paper"):
        ex.place_order(_make_order(is_paper=True))


def test_factory_routes_upstox_with_token():
    _install_fake_upstox()
    from app.services.execution import UpstoxExecutor, get_executor

    ex = get_executor("upstox", api_key="", secret_key="", paper=False, access_token="tok")
    assert isinstance(ex, UpstoxExecutor)


def test_preresolved_instrument_key_passes_through():
    _install_fake_upstox()
    from app.services.execution import UpstoxExecutor

    ex = UpstoxExecutor(access_token="tok")
    order = _make_order(is_paper=False)
    order.symbol = "NSE_EQ|INE002A01018"
    # When the symbol already is an instrument_key, no network lookup happens.
    assert ex._instrument_key(order) == "NSE_EQ|INE002A01018"


if __name__ == "__main__":
    import traceback

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed} passed")
