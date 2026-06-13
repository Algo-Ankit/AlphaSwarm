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
