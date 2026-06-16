"""
Billing gate logic + Stripe service guards (pure logic — no Stripe SDK / network).
Runnable with pytest OR directly:  python tests/test_billing.py
"""

import pytest

from app.services import billing


def test_active_statuses_unlock_live():
    assert billing.is_active_status("active") is True
    assert billing.is_active_status("trialing") is True


def test_inactive_statuses_block_live():
    for s in ("inactive", "past_due", "canceled", "incomplete", None, ""):
        assert billing.is_active_status(s) is False


def test_active_status_is_case_insensitive():
    assert billing.is_active_status("ACTIVE") is True
    assert billing.is_active_status("Trialing") is True


def test_checkout_requires_stripe_configured(monkeypatch):
    # With no STRIPE_SECRET_KEY, attempting checkout must fail loudly, not silently.
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("STRIPE_SECRET_KEY", "")
    with pytest.raises(billing.BillingNotConfigured):
        billing.create_checkout_session(
            tenant_id="00000000-0000-0000-0000-000000000000",
            customer_email="user@example.com",
        )
    get_settings.cache_clear()


def test_webhook_requires_stripe_configured(monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("STRIPE_SECRET_KEY", "")
    with pytest.raises(billing.BillingNotConfigured):
        billing.parse_webhook_event(b"{}", "sig")
    get_settings.cache_clear()


if __name__ == "__main__":
    import traceback

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            # crude monkeypatch shim for direct-run mode
            if "monkeypatch" in fn.__code__.co_varnames:
                continue
            fn()
            print(f"PASS  {fn.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed} passed")
