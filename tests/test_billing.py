"""
Razorpay billing: live-access gate + HMAC-SHA256 webhook signature verification.
Pure logic — no Razorpay SDK / network.
Runnable with pytest OR directly:  python tests/test_billing.py
"""

import hashlib
import hmac

import pytest

from app.services import billing


def test_active_status_unlocks_live():
    assert billing.is_active_status("active") is True


def test_non_active_statuses_block_live():
    # Razorpay lifecycle: only 'active' grants live access.
    for s in (
        "created",
        "authenticated",
        "pending",
        "halted",
        "cancelled",
        "completed",
        "expired",
        "inactive",
        None,
        "",
    ):
        assert billing.is_active_status(s) is False


def test_active_status_is_case_insensitive():
    assert billing.is_active_status("ACTIVE") is True


def test_subscribe_requires_razorpay_configured(monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("RAZORPAY_KEY_ID", "")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "")
    with pytest.raises(billing.BillingNotConfigured):
        billing.create_subscription(
            tenant_id="00000000-0000-0000-0000-000000000000",
            customer_email="user@example.com",
        )
    get_settings.cache_clear()


def _configure(monkeypatch, webhook_secret="whsec_test"):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_abc")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret123")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", webhook_secret)


def test_valid_webhook_signature_passes(monkeypatch):
    _configure(monkeypatch)
    body = b'{"event":"subscription.charged"}'
    sig = hmac.new(b"whsec_test", body, hashlib.sha256).hexdigest()
    # Should not raise.
    billing.verify_webhook_signature(body, sig)
    from app.core.config import get_settings

    get_settings.cache_clear()


def test_forged_webhook_signature_rejected(monkeypatch):
    _configure(monkeypatch)
    body = b'{"event":"subscription.charged"}'
    with pytest.raises(ValueError):
        billing.verify_webhook_signature(body, "deadbeef")
    from app.core.config import get_settings

    get_settings.cache_clear()


def test_tampered_body_rejected(monkeypatch):
    _configure(monkeypatch)
    body = b'{"event":"subscription.charged"}'
    sig = hmac.new(b"whsec_test", body, hashlib.sha256).hexdigest()
    tampered = b'{"event":"subscription.activated"}'
    with pytest.raises(ValueError):
        billing.verify_webhook_signature(tampered, sig)
    from app.core.config import get_settings

    get_settings.cache_clear()


def test_missing_signature_rejected(monkeypatch):
    _configure(monkeypatch)
    with pytest.raises(ValueError):
        billing.verify_webhook_signature(b"{}", "")
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
