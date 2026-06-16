"""
Stripe billing service — Quant Tier subscriptions.

Thin wrapper around the Stripe SDK so API routes never touch `stripe.*` directly.
Two responsibilities:
  1. Create a Checkout Session for the Quant Tier subscription.
  2. Verify + parse incoming webhook events (signature-checked).

The actual DB writes (flipping `subscription_status` on a tenant) live in the
webhook route, which owns the asyncpg pool. This module is pure Stripe I/O.
"""

from __future__ import annotations

import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Stripe subscription statuses that unlock LIVE trading.
ACTIVE_SUBSCRIPTION_STATUSES = frozenset({"active", "trialing"})

# Plan name a tenant is moved to once they hold an active subscription.
QUANT_TIER_PLAN = "quant"


class BillingNotConfigured(RuntimeError):
    """Raised when a billing operation is attempted without Stripe configured."""


def _client():
    """Return the configured stripe module, or raise if not set up."""
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise BillingNotConfigured(
            "Stripe is not configured — set STRIPE_SECRET_KEY to enable billing."
        )
    import stripe

    stripe.api_key = settings.stripe_secret_key
    return stripe


def create_checkout_session(
    *,
    tenant_id: str,
    customer_email: str,
    stripe_customer_id: str | None = None,
) -> dict:
    """
    Create a Stripe Checkout Session for the Quant Tier subscription.

    `tenant_id` is stashed in client_reference_id + subscription metadata so the
    webhook can map the resulting subscription back to our tenant.
    Returns {"id": session_id, "url": checkout_url}.
    """
    settings = get_settings()
    stripe = _client()
    if not settings.stripe_price_quant:
        raise BillingNotConfigured(
            "STRIPE_PRICE_QUANT is not set — configure the Quant Tier price ID."
        )

    kwargs: dict = {
        "mode": "subscription",
        "line_items": [{"price": settings.stripe_price_quant, "quantity": 1}],
        "client_reference_id": tenant_id,
        "success_url": settings.stripe_success_url,
        "cancel_url": settings.stripe_cancel_url,
        "subscription_data": {"metadata": {"tenant_id": tenant_id}},
        "metadata": {"tenant_id": tenant_id},
    }
    # Reuse an existing Stripe customer if we've created one before; otherwise let
    # Checkout create one from the email.
    if stripe_customer_id:
        kwargs["customer"] = stripe_customer_id
    else:
        kwargs["customer_email"] = customer_email

    session = stripe.checkout.Session.create(**kwargs)
    return {"id": session.id, "url": session.url}


def parse_webhook_event(payload: bytes, signature: str) -> dict:
    """
    Verify a webhook signature and return the parsed event dict.
    Raises ValueError on a bad/forged signature.
    """
    settings = get_settings()
    stripe = _client()
    if not settings.stripe_webhook_secret:
        raise BillingNotConfigured(
            "STRIPE_WEBHOOK_SECRET is not set — cannot verify webhook signatures."
        )
    try:
        event = stripe.Webhook.construct_event(payload, signature, settings.stripe_webhook_secret)
    except Exception as exc:  # SignatureVerificationError / ValueError
        raise ValueError(f"Invalid Stripe webhook signature: {exc}") from exc
    return event


def is_active_status(status: str | None) -> bool:
    return (status or "").lower() in ACTIVE_SUBSCRIPTION_STATUSES
