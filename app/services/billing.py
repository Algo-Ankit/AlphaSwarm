"""
Razorpay billing service — Quant Tier recurring subscriptions (UPI AutoPay /
e-mandate). India-first: Stripe is RBI-restricted for recurring INR mandates, so
we use Razorpay's Subscriptions API.

Thin wrapper around the Razorpay SDK so API routes never touch `razorpay.*`
directly. Two responsibilities:
  1. Create a recurring Subscription for the Quant Tier (returns a hosted
     authorization short_url where the customer approves the UPI AutoPay mandate).
  2. Verify incoming webhook signatures (HMAC-SHA256) to prevent forgery.

The actual DB writes (flipping `subscription_status` on a tenant) live in the
webhook route, which owns the asyncpg pool. This module is pure Razorpay I/O.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Razorpay subscription statuses that unlock LIVE trading. Only 'active' confirms
# a successful charge under an authorized mandate. (Full lifecycle: created →
# authenticated → active → {pending → halted | cancelled | completed | expired}.)
ACTIVE_SUBSCRIPTION_STATUSES = frozenset({"active"})

# Plan name a tenant is moved to once they hold an active subscription.
QUANT_TIER_PLAN = "quant"


class BillingNotConfigured(RuntimeError):
    """Raised when a billing operation is attempted without Razorpay configured."""


def _client():
    """Return an authenticated Razorpay client, or raise if not configured."""
    settings = get_settings()
    if not (settings.razorpay_key_id and settings.razorpay_key_secret):
        raise BillingNotConfigured(
            "Razorpay is not configured — set RAZORPAY_KEY_ID and "
            "RAZORPAY_KEY_SECRET to enable billing."
        )
    import razorpay

    return razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))


def create_subscription(
    *,
    tenant_id: str,
    customer_email: str,
    customer_notify: bool = True,
) -> dict:
    """
    Create a Razorpay recurring Subscription for the Quant Tier.

    `tenant_id` is stashed in the subscription `notes` so the webhook can map the
    subscription back to our tenant. Returns the subscription id and the hosted
    `short_url` the frontend redirects the user to, where they authorize the UPI
    AutoPay / e-mandate.
    """
    settings = get_settings()
    client = _client()
    if not settings.razorpay_plan_quant:
        raise BillingNotConfigured(
            "RAZORPAY_PLAN_QUANT is not set — configure the Quant Tier plan ID."
        )

    subscription = client.subscription.create(
        {
            "plan_id": settings.razorpay_plan_quant,
            "total_count": settings.razorpay_subscription_total_count,
            "customer_notify": 1 if customer_notify else 0,
            "notes": {"tenant_id": tenant_id, "email": customer_email},
        }
    )
    return {
        "id": subscription["id"],
        "short_url": subscription.get("short_url"),
        "status": subscription.get("status"),
    }


def cancel_subscription(subscription_id: str, *, cancel_at_cycle_end: bool = False) -> dict:
    """Cancel a Razorpay subscription (immediately by default)."""
    client = _client()
    return client.subscription.cancel(
        subscription_id, {"cancel_at_cycle_end": 1 if cancel_at_cycle_end else 0}
    )


def verify_webhook_signature(payload: bytes, signature: str) -> None:
    """
    Verify a Razorpay webhook signature using the HMAC-SHA256 standard.

    Razorpay signs the *raw* request body with the dashboard webhook secret:
        expected = HMAC_SHA256(secret, raw_body).hexdigest()
    and sends it in the `X-Razorpay-Signature` header. We recompute and compare
    in constant time. Raises ValueError on any mismatch (forged/tampered payload).
    """
    settings = get_settings()
    if not (settings.razorpay_key_id and settings.razorpay_key_secret):
        raise BillingNotConfigured("Razorpay is not configured — cannot verify webhooks.")
    if not settings.razorpay_webhook_secret:
        raise BillingNotConfigured(
            "RAZORPAY_WEBHOOK_SECRET is not set — cannot verify webhook signatures."
        )
    if not signature:
        raise ValueError("Missing X-Razorpay-Signature header")

    expected = hmac.new(
        settings.razorpay_webhook_secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise ValueError("Invalid Razorpay webhook signature")


def is_active_status(status: str | None) -> bool:
    return (status or "").lower() in ACTIVE_SUBSCRIPTION_STATUSES
