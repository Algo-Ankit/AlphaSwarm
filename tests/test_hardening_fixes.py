"""
Regression tests for the security/billing hardening pass (July 2026).

Covers:
  1. Alpaca base_url allowlist (SSRF guard) — creds must only ever be sent to
     *.alpaca.markets over https.
  2. Swarm Tax charge semantics — _attempt_charge returns a STATUS, and a
     Razorpay order (money not yet collected) must never read as 'charged'.
  3. Leaderboard fee cap — management_fee_bps > 2000 (20%) is rejected.
  4. Login timing equalizer — burns a bcrypt verify without raising.
"""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

# ── 1. Alpaca base_url SSRF guard ──────────────────────────────────────────────


def test_alpaca_url_accepts_official_hosts():
    from app.api.brokers import _validate_alpaca_url

    _validate_alpaca_url("https://paper-api.alpaca.markets")
    _validate_alpaca_url("https://api.alpaca.markets")
    _validate_alpaca_url("https://alpaca.markets")


@pytest.mark.parametrize(
    "url",
    [
        "http://paper-api.alpaca.markets",  # plaintext — creds in the clear
        "https://evil.example.com",  # arbitrary host — credential exfil
        "https://alpaca.markets.evil.com",  # suffix-spoofed domain
        "https://internal-service:8080",  # SSRF into private network
        "https://xalpaca.markets",  # not a subdomain, prefix trick
    ],
)
def test_alpaca_url_rejects_non_alpaca_hosts(url):
    from app.api.brokers import _validate_alpaca_url

    with pytest.raises(HTTPException):
        _validate_alpaca_url(url)


# ── 2. Swarm Tax charge status semantics ───────────────────────────────────────


def test_attempt_charge_no_gateway_is_exempt():
    from app.worker.billing_tasks import _attempt_charge

    status = _attempt_charge(
        sub_id="sub-1", amount_usd=10.0, stripe_customer_id=None, razorpay_customer_id=None
    )
    assert status == "exempt"


def test_attempt_charge_zero_amount_is_exempt():
    from app.worker.billing_tasks import _attempt_charge

    status = _attempt_charge(
        sub_id="sub-1", amount_usd=0.0, stripe_customer_id="cus_x", razorpay_customer_id="cust_y"
    )
    assert status == "exempt"


def test_attempt_charge_razorpay_order_is_invoiced_not_charged(monkeypatch):
    """A Razorpay order.create issues an order the customer must still pay —
    reporting it as 'charged' credited the creator ledger with phantom revenue."""
    from app.services import billing
    from app.worker import billing_tasks

    class _FakeOrderApi:
        def create(self, payload):
            assert payload["currency"] == "INR"
            return {"id": "order_fake"}

    class _FakeClient:
        order = _FakeOrderApi()

    monkeypatch.setattr(billing, "_razorpay_client", lambda: _FakeClient())

    status = billing_tasks._attempt_charge(
        sub_id="sub-1", amount_usd=10.0, stripe_customer_id=None, razorpay_customer_id="cust_y"
    )
    assert status == "invoiced"  # NOT 'charged' — no money has moved yet


# ── 3. Leaderboard management-fee cap ──────────────────────────────────────────


def test_publish_fee_capped_at_20_percent():
    from app.api.social import PublishRequest

    ok = PublishRequest(strategy_id="x", title="My Strategy", management_fee_bps=2_000)
    assert ok.management_fee_bps == 2_000

    with pytest.raises(ValidationError):
        PublishRequest(strategy_id="x", title="My Strategy", management_fee_bps=2_001)


# ── 4. Login timing equalizer ──────────────────────────────────────────────────


def test_equalize_login_timing_never_raises():
    from app.services.auth import equalize_login_timing

    equalize_login_timing("any-password")
    equalize_login_timing("")


# ── 5. OAuth state tokens (broker-identity login CSRF guard) ──────────────────


def test_state_token_round_trip():
    from app.services.auth import create_state_token, verify_state_token

    token = create_state_token("upstox-login")
    assert verify_state_token(token, "upstox-login")


def test_state_token_rejects_wrong_purpose():
    """A state minted for one flow must not authorize another."""
    from app.services.auth import create_state_token, verify_state_token

    token = create_state_token("upstox-login")
    assert not verify_state_token(token, "zerodha-login")


def test_state_token_rejects_garbage_and_forgeries():
    import jwt as pyjwt

    from app.services.auth import verify_state_token

    assert not verify_state_token("not-a-jwt", "upstox-login")
    forged = pyjwt.encode(
        {"purpose": "upstox-login", "type": "oauth_state"}, "wrong-key", algorithm="HS256"
    )
    assert not verify_state_token(forged, "upstox-login")


def test_state_token_rejects_expired():
    from app.services.auth import create_state_token, verify_state_token

    token = create_state_token("upstox-login", ttl_seconds=-10)
    assert not verify_state_token(token, "upstox-login")


def test_access_token_is_not_a_valid_state():
    """type='access' JWTs must never pass the oauth_state check (token confusion)."""
    from app.services.auth import create_access_token, verify_state_token

    access = create_access_token(user_id="u", tenant_id="t", email="a@b.c", role="owner")
    assert not verify_state_token(access, "upstox-login")
