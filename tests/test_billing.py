"""
Dual-gateway billing: currency routing, live-access gate, and webhook signature
verification for both Stripe and Razorpay. Pure logic — no SDK / network.
Runnable with pytest OR directly:  python tests/test_billing.py
"""

import hashlib
import hmac

import pytest

from app.services import billing

# ── Currency → gateway routing ────────────────────────────────────────────────


def test_usd_routes_to_stripe():
    assert billing.gateway_for_currency("USD") == "stripe"
    assert billing.gateway_for_currency("usd") == "stripe"


def test_inr_routes_to_razorpay():
    assert billing.gateway_for_currency("INR") == "razorpay"
    assert billing.gateway_for_currency("inr") == "razorpay"


def test_unsupported_currency_raises():
    with pytest.raises(ValueError):
        billing.gateway_for_currency("EUR")


# ── Universal live-access gate ────────────────────────────────────────────────


def test_active_statuses_unlock_live():
    # Stripe uses active/trialing; Razorpay uses active — all unlock live trading.
    assert billing.is_active_status("active") is True
    assert billing.is_active_status("trialing") is True
    assert billing.is_active_status("ACTIVE") is True


def test_non_active_statuses_block_live():
    for s in (
        "created",
        "authenticated",
        "pending",
        "halted",
        "past_due",
        "cancelled",
        "canceled",
        "completed",
        "expired",
        "inactive",
        None,
        "",
    ):
        assert billing.is_active_status(s) is False


# ── Gateway-not-configured guards ─────────────────────────────────────────────


def test_stripe_checkout_requires_config(monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("STRIPE_SECRET_KEY", "")
    with pytest.raises(billing.BillingNotConfigured):
        billing.create_stripe_checkout_session(
            tenant_id="00000000-0000-0000-0000-000000000000",
            customer_email="user@example.com",
        )
    get_settings.cache_clear()


def test_stripe_webhook_requires_config(monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("STRIPE_SECRET_KEY", "")
    with pytest.raises(billing.BillingNotConfigured):
        billing.parse_stripe_webhook_event(b"{}", "sig")
    get_settings.cache_clear()


def test_razorpay_subscribe_requires_config(monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("RAZORPAY_KEY_ID", "")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "")
    with pytest.raises(billing.BillingNotConfigured):
        billing.create_razorpay_subscription(
            tenant_id="00000000-0000-0000-0000-000000000000",
            customer_email="user@example.com",
        )
    get_settings.cache_clear()


# ── Razorpay HMAC-SHA256 webhook verification ─────────────────────────────────


def _configure_razorpay(monkeypatch, webhook_secret="whsec_test"):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_abc")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret123")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", webhook_secret)


def test_valid_razorpay_signature_passes(monkeypatch):
    _configure_razorpay(monkeypatch)
    body = b'{"event":"subscription.charged"}'
    sig = hmac.new(b"whsec_test", body, hashlib.sha256).hexdigest()
    billing.verify_razorpay_webhook_signature(body, sig)  # should not raise
    from app.core.config import get_settings

    get_settings.cache_clear()


def test_forged_razorpay_signature_rejected(monkeypatch):
    _configure_razorpay(monkeypatch)
    with pytest.raises(ValueError):
        billing.verify_razorpay_webhook_signature(b'{"event":"subscription.charged"}', "deadbeef")
    from app.core.config import get_settings

    get_settings.cache_clear()


def test_tampered_razorpay_body_rejected(monkeypatch):
    _configure_razorpay(monkeypatch)
    body = b'{"event":"subscription.charged"}'
    sig = hmac.new(b"whsec_test", body, hashlib.sha256).hexdigest()
    with pytest.raises(ValueError):
        billing.verify_razorpay_webhook_signature(b'{"event":"subscription.activated"}', sig)
    from app.core.config import get_settings

    get_settings.cache_clear()


def test_missing_razorpay_signature_rejected(monkeypatch):
    _configure_razorpay(monkeypatch)
    with pytest.raises(ValueError):
        billing.verify_razorpay_webhook_signature(b"{}", "")
    from app.core.config import get_settings

    get_settings.cache_clear()


if __name__ == "__main__":
    import traceback

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            if "monkeypatch" in fn.__code__.co_varnames:
                continue
            fn()
            print(f"PASS  {fn.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed} passed")
