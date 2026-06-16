"""
Dual-gateway billing service — Quant Tier subscriptions for both markets:

  • Stripe   → USD / Global (Checkout Session, recurring subscription)
  • Razorpay → INR / India  (Subscriptions API, UPI AutoPay / e-mandate;
               Stripe is RBI-restricted for recurring INR mandates)

Routes never touch `stripe.*` / `razorpay.*` directly — they call the helpers
here. Each gateway:
  1. generates a hosted checkout/authorization URL for the Quant Tier, and
  2. verifies its webhook signatures (Stripe: SDK; Razorpay: HMAC-SHA256).

The universal `subscription_status` column on `tenants` is the single source of
truth; both webhooks write to it. Each gateway is independently optional — its
helpers raise BillingNotConfigured until that gateway's keys are set.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Subscription statuses that unlock LIVE trading, across BOTH gateways.
#   Stripe:   active, trialing
#   Razorpay: active
ACTIVE_SUBSCRIPTION_STATUSES = frozenset({"active", "trialing"})

# Plan name a tenant is moved to once they hold an active subscription.
QUANT_TIER_PLAN = "quant"

# Supported billing currencies → gateway.
GATEWAY_FOR_CURRENCY = {"USD": "stripe", "INR": "razorpay"}


class BillingNotConfigured(RuntimeError):
    """Raised when a billing operation is attempted without its gateway configured."""


def gateway_for_currency(currency: str) -> str:
    """Map a currency code to its payment gateway. Raises ValueError if unsupported."""
    gateway = GATEWAY_FOR_CURRENCY.get((currency or "").upper())
    if not gateway:
        raise ValueError(
            f"Unsupported billing currency {currency!r}. Supported: "
            f"{', '.join(GATEWAY_FOR_CURRENCY)}."
        )
    return gateway


def is_active_status(status: str | None) -> bool:
    return (status or "").lower() in ACTIVE_SUBSCRIPTION_STATUSES


# ══════════════════════════════════════════════════════════════════════════════
# Stripe (USD / Global)
# ══════════════════════════════════════════════════════════════════════════════


def _stripe_client():
    """Return the configured stripe module, or raise if not set up."""
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise BillingNotConfigured(
            "Stripe is not configured — set STRIPE_SECRET_KEY to enable USD billing."
        )
    import stripe

    stripe.api_key = settings.stripe_secret_key
    return stripe


def create_stripe_checkout_session(
    *,
    tenant_id: str,
    customer_email: str,
    stripe_customer_id: str | None = None,
) -> dict:
    """
    Create a Stripe Checkout Session for the Quant Tier subscription (USD).

    `tenant_id` is stashed in client_reference_id + subscription metadata so the
    webhook can map the resulting subscription back to our tenant.
    Returns {"id": session_id, "url": checkout_url}.
    """
    settings = get_settings()
    stripe = _stripe_client()
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
    # Reuse an existing Stripe customer if we've created one; otherwise let
    # Checkout create one from the email.
    if stripe_customer_id:
        kwargs["customer"] = stripe_customer_id
    else:
        kwargs["customer_email"] = customer_email

    session = stripe.checkout.Session.create(**kwargs)
    return {"id": session.id, "url": session.url}


def parse_stripe_webhook_event(payload: bytes, signature: str) -> dict:
    """
    Verify a Stripe webhook signature (SDK, which checks the t=/v1= scheme) and
    return the parsed event dict. Raises ValueError on a bad/forged signature.
    """
    settings = get_settings()
    stripe = _stripe_client()
    if not settings.stripe_webhook_secret:
        raise BillingNotConfigured(
            "STRIPE_WEBHOOK_SECRET is not set — cannot verify Stripe webhook signatures."
        )
    try:
        event = stripe.Webhook.construct_event(payload, signature, settings.stripe_webhook_secret)
    except Exception as exc:  # SignatureVerificationError / ValueError
        raise ValueError(f"Invalid Stripe webhook signature: {exc}") from exc
    return event


# ══════════════════════════════════════════════════════════════════════════════
# Razorpay (INR / India)
# ══════════════════════════════════════════════════════════════════════════════


def _razorpay_client():
    """Return an authenticated Razorpay client, or raise if not configured."""
    settings = get_settings()
    if not (settings.razorpay_key_id and settings.razorpay_key_secret):
        raise BillingNotConfigured(
            "Razorpay is not configured — set RAZORPAY_KEY_ID and "
            "RAZORPAY_KEY_SECRET to enable INR billing."
        )
    import razorpay

    return razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))


def create_razorpay_subscription(
    *,
    tenant_id: str,
    customer_email: str,
    customer_notify: bool = True,
) -> dict:
    """
    Create a Razorpay recurring Subscription for the Quant Tier (INR).

    `tenant_id` is stashed in the subscription `notes` so the webhook can map the
    subscription back to our tenant. Returns the subscription id and the hosted
    `short_url` the frontend redirects the user to, where they authorize the UPI
    AutoPay / e-mandate.
    """
    settings = get_settings()
    client = _razorpay_client()
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


def cancel_razorpay_subscription(
    subscription_id: str, *, cancel_at_cycle_end: bool = False
) -> dict:
    """Cancel a Razorpay subscription (immediately by default)."""
    client = _razorpay_client()
    return client.subscription.cancel(
        subscription_id, {"cancel_at_cycle_end": 1 if cancel_at_cycle_end else 0}
    )


def verify_razorpay_webhook_signature(payload: bytes, signature: str) -> None:
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
