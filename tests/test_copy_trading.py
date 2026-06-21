"""
Copy-trade position sizing tests (pure logic — no DB / broker needed).
Runnable with pytest OR directly:  python tests/test_copy_trading.py
"""

from decimal import Decimal

from app.services.execution import copy_order_quantity


def test_proportional_scaling():
    # Subscriber allocates the SAME capital base as the creator → same quantity.
    qty = copy_order_quantity(
        signal_quantity=Decimal("10"),
        creator_capital_base=Decimal("10000"),
        allocated_capital=Decimal("10000"),
        price=Decimal("100"),
        whole_shares=False,
    )
    assert qty == Decimal("10")


def test_half_allocation_halves_quantity():
    qty = copy_order_quantity(
        signal_quantity=Decimal("10"),
        creator_capital_base=Decimal("10000"),
        allocated_capital=Decimal("5000"),
        price=Decimal("100"),
        whole_shares=False,
    )
    assert qty == Decimal("5")


def test_capital_clamp_caps_notional():
    # Scale would imply 100 shares * $100 = $10k, but the subscriber only allocated
    # $1k — the order must be clamped to stay within allocated capital (and leave
    # headroom for the risk gate's gap-inflated cap price).
    qty = copy_order_quantity(
        signal_quantity=Decimal("100"),
        creator_capital_base=Decimal("1000"),
        allocated_capital=Decimal("1000"),
        price=Decimal("100"),
        whole_shares=False,
    )
    # max_qty = 1000 / (100 * 1.03) ≈ 9.70 — never the unclamped 100.
    assert qty <= Decimal("1000") / (Decimal("100") * Decimal("1.03"))
    assert qty * Decimal("100") * Decimal("1.03") <= Decimal("1000")


def test_whole_shares_floored():
    # NSE/BSE forbid fractional equity — quantity must floor to an integer.
    qty = copy_order_quantity(
        signal_quantity=Decimal("7"),
        creator_capital_base=Decimal("10000"),
        allocated_capital=Decimal("5000"),  # scale 0.5 → 3.5 shares
        price=Decimal("100"),
        whole_shares=True,
    )
    assert qty == Decimal("3")
    assert qty == qty.to_integral_value()


def test_zero_when_allocation_too_small():
    # Allocation can't afford even one whole share → no order.
    qty = copy_order_quantity(
        signal_quantity=Decimal("10"),
        creator_capital_base=Decimal("10000"),
        allocated_capital=Decimal("50"),
        price=Decimal("100"),
        whole_shares=True,
    )
    assert qty == Decimal("0")


def test_zero_guards_on_bad_inputs():
    base = dict(
        signal_quantity=Decimal("10"),
        creator_capital_base=Decimal("10000"),
        allocated_capital=Decimal("5000"),
        price=Decimal("100"),
        whole_shares=False,
    )
    for bad in ("creator_capital_base", "allocated_capital", "price", "signal_quantity"):
        assert copy_order_quantity(**{**base, bad: Decimal("0")}) == Decimal("0")


if __name__ == "__main__":
    import sys

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    sys.exit(1 if failed else 0)
