"""
Executor bracket/OTO routing tests (pure logic — no Alpaca SDK needed).
Runnable with pytest OR directly:  python tests/test_execution.py
"""

from decimal import Decimal

from app.services.execution import bracket_order_class


def test_both_legs_is_bracket():
    assert bracket_order_class("AAPL", Decimal("95"), Decimal("110")) == "bracket"


def test_single_leg_is_oto():
    # Alpaca BRACKET requires BOTH legs; one leg must be OTO or it's rejected.
    assert bracket_order_class("AAPL", Decimal("95"), None) == "oto"
    assert bracket_order_class("AAPL", None, Decimal("110")) == "oto"


def test_no_legs_is_none():
    assert bracket_order_class("AAPL", None, None) is None


def test_crypto_skips_legs():
    # Alpaca has no bracket/OTO for crypto regardless of requested legs.
    assert bracket_order_class("BTC/USD", Decimal("90"), Decimal("110")) is None
    assert bracket_order_class("BTC-USD", Decimal("90"), None) is None


def test_get_executor_returns_zerodha_and_angelone():
    from app.services.execution import AngelOneExecutor, ZerodhaExecutor, get_executor

    z = get_executor("zerodha", api_key="k", secret_key="s", access_token="tok")
    assert isinstance(z, ZerodhaExecutor)

    a = get_executor("angelone", api_key="k", secret_key="s", access_token="tok")
    assert isinstance(a, AngelOneExecutor)


def test_indian_executors_require_access_token():
    import pytest
    from app.services.execution import AngelOneExecutor, ZerodhaExecutor

    with pytest.raises(ValueError, match="requires an active session token"):
        AngelOneExecutor(api_key="k", access_token="")

    with pytest.raises(ValueError, match="requires an OAuth access token"):
        ZerodhaExecutor(api_key="k", access_token="")


def test_indian_executors_reject_paper_orders():
    import pytest
    from app.domain.models import OrderIntent, OrderSide, OrderType
    from app.services.execution import AngelOneExecutor, ZerodhaExecutor

    order = OrderIntent(
        strategy_id="strat-1",
        symbol="RELIANCE",
        exchange="NSE",
        side=OrderSide.buy,
        quantity=Decimal("10"),
        order_type=OrderType.market,
        estimated_price=Decimal("2500"),
        is_paper=True,
    )

    a = AngelOneExecutor(api_key="k", access_token="tok")
    with pytest.raises(RuntimeError, match="Refusing to route a paper-flagged order"):
        a.place_order(order)

    z = ZerodhaExecutor(api_key="k", access_token="tok")
    with pytest.raises(RuntimeError, match="Refusing to route a paper-flagged order"):
        z.place_order(order)


def test_brokers_for_exchange_supports_indian_multi_broker():
    from app.domain.broker_routing import broker_for_exchange, brokers_for_exchange

    assert broker_for_exchange("NSE") == "upstox"
    assert brokers_for_exchange("NSE") == ("upstox", "zerodha", "angelone")
    assert brokers_for_exchange("BSE") == ("upstox", "zerodha", "angelone")
    assert brokers_for_exchange("NASDAQ") == ("alpaca",)
    assert brokers_for_exchange("CRYPTO") == ("alpaca",)


def test_strategy_risk_config_json_dump_serializes_decimal():
    import json

    from app.domain.models import StrategyRiskConfig

    cfg = StrategyRiskConfig(
        max_order_notional=Decimal("2500.50"),
        max_daily_notional=Decimal("10000"),
        paper_trading_only=False,
    )
    dumped = cfg.model_dump(mode="json")
    serialized = json.dumps(dumped)
    parsed = json.loads(serialized)
    assert parsed["paper_trading_only"] is False
    assert parsed["max_order_notional"] == 2500.5


def test_should_run_for_timeframe_cadence_and_daily_dedup():
    from datetime import datetime, timezone

    from app.worker.beat_tasks import _should_run_for_timeframe

    # 15m only triggers on multiples of 15
    assert _should_run_for_timeframe("15m", datetime(2026, 11, 20, 10, 15, tzinfo=timezone.utc))
    assert not _should_run_for_timeframe("15m", datetime(2026, 11, 20, 10, 16, tzinfo=timezone.utc))

    # 4h only triggers at minute == 0 and hour % 4 == 0
    assert _should_run_for_timeframe("4h", datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc))
    assert not _should_run_for_timeframe("4h", datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc))
    assert not _should_run_for_timeframe("4h", datetime(2026, 11, 20, 8, 5, tzinfo=timezone.utc))

    # 1d runs at most once per exchange local trading day
    now_ist_day1 = datetime(2026, 11, 20, 5, 0, tzinfo=timezone.utc)  # 10:30 IST Nov 20
    earlier_same_ist_day = datetime(2026, 11, 20, 4, 0, tzinfo=timezone.utc)  # 09:30 IST Nov 20
    prev_ist_day = datetime(2026, 11, 19, 9, 0, tzinfo=timezone.utc)  # 14:30 IST Nov 19

    assert _should_run_for_timeframe("1d", now_ist_day1, last_run_at=None, exchange="NSE")
    assert not _should_run_for_timeframe(
        "1d", now_ist_day1, last_run_at=earlier_same_ist_day, exchange="NSE"
    )
    assert _should_run_for_timeframe("1d", now_ist_day1, last_run_at=prev_ist_day, exchange="NSE")


def test_indian_executors_resolve_tokens_and_strip_suffix():
    from unittest.mock import MagicMock, patch

    from app.domain.models import OrderIntent, OrderSide, OrderType
    from app.services.execution import AngelOneExecutor, ZerodhaExecutor

    order = OrderIntent(
        strategy_id="strat-1",
        symbol="RELIANCE.NS",
        exchange="NSE",
        side=OrderSide.buy,
        quantity=Decimal("5"),
        order_type=OrderType.market,
        estimated_price=Decimal("2500"),
        is_paper=False,
    )

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"status": True, "data": {"orderid": "AO-123"}}
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_resp

    with (
        patch(
            "app.services.execution._load_angelone_instruments",
            return_value={"RELIANCE": ("RELIANCE-EQ", "2885")},
        ),
        patch("httpx.Client", return_value=mock_client),
    ):
        ao = AngelOneExecutor(api_key="smart-api-key", access_token="jwt-tok")
        res = ao.place_order(order)
        assert res.order_id == "AO-123"
        _, kwargs = mock_client.post.call_args
        assert kwargs["headers"]["X-PrivateKey"] == "smart-api-key"
        assert kwargs["json"]["tradingsymbol"] == "RELIANCE-EQ"
        assert kwargs["json"]["symboltoken"] == "2885"

    mock_z_resp = MagicMock()
    mock_z_resp.json.return_value = {"status": "success", "data": {"order_id": "Z-456"}}
    mock_z_client = MagicMock()
    mock_z_client.__enter__.return_value = mock_z_client
    mock_z_client.post.return_value = mock_z_resp

    with patch("httpx.Client", return_value=mock_z_client):
        z = ZerodhaExecutor(api_key="kite-key", access_token="kite-tok")
        z_res = z.place_order(order)
        assert z_res.order_id == "Z-456"
        _, z_kwargs = mock_z_client.post.call_args
        assert z_kwargs["data"]["tradingsymbol"] == "RELIANCE"


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
    print(f"\n{passed}/{len(fns)} passed")
    raise SystemExit(0 if passed == len(fns) else 1)
