"""
Billing API — dual-gateway Quant Tier subscriptions.

  POST /v1/billing/checkout         (auth) → routes by currency:
                                              USD → Stripe Checkout
                                              INR → Razorpay subscription
  POST /v1/billing/webhook/stripe   (public, signature-verified)
  POST /v1/billing/webhook/razorpay (public, HMAC-verified)
  GET  /v1/billing/subscription     (auth) → current tenant subscription status

Both webhooks update the universal `subscription_status` on `tenants`, which is
what the live-deployment gate (app/api/routes.py) checks.
"""

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_current_user, get_db_pool
from app.db.repositories.users import TenantRepo
from app.services import billing

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    # Currency selects the gateway: USD → Stripe (Global), INR → Razorpay (India).
    currency: str = Field(default="USD", pattern="^(USD|INR|usd|inr)$")


class CheckoutResponse(BaseModel):
    gateway: str  # "stripe" | "razorpay"
    # URL to redirect the user to (Stripe Checkout page or Razorpay hosted auth).
    checkout_url: str
    reference_id: str  # Stripe session id or Razorpay subscription id


class SubscriptionResponse(BaseModel):
    plan: str
    subscription_status: str
    is_active: bool
    current_period_end: str | None


# ── Checkout (currency-routed) ────────────────────────────────────────────────


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> CheckoutResponse:
    """Start a Quant Tier checkout, routed to Stripe (USD) or Razorpay (INR)."""
    repo = TenantRepo(pool)
    tenant = await repo.get_by_id(current_user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    gateway = billing.gateway_for_currency(body.currency)

    try:
        if gateway == "stripe":
            result = billing.create_stripe_checkout_session(
                tenant_id=str(current_user.tenant_id),
                customer_email=current_user.email,
                stripe_customer_id=tenant.get("stripe_customer_id"),
            )
            checkout_url, reference_id = result["url"], result["id"]
        else:  # razorpay
            result = billing.create_razorpay_subscription(
                tenant_id=str(current_user.tenant_id),
                customer_email=current_user.email,
            )
            checkout_url, reference_id = result.get("short_url"), result["id"]
            # Record the subscription id up front so the webhook can map it back
            # even before the user finishes authorizing the mandate.
            await repo.update_subscription(
                current_user.tenant_id,
                status=result.get("status") or "created",
                razorpay_subscription_id=reference_id,
            )
    except billing.BillingNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        logger.exception("%s checkout creation failed", gateway)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not create checkout with {gateway}",
        ) from exc

    if not checkout_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{gateway} did not return a checkout URL",
        )

    return CheckoutResponse(gateway=gateway, checkout_url=checkout_url, reference_id=reference_id)


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> SubscriptionResponse:
    repo = TenantRepo(pool)
    tenant = await repo.get_by_id(current_user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    sub_status = tenant.get("subscription_status") or "inactive"
    cpe = tenant.get("subscription_current_period_end")
    return SubscriptionResponse(
        plan=tenant["plan"],
        subscription_status=sub_status,
        is_active=billing.is_active_status(sub_status),
        current_period_end=cpe.isoformat() if isinstance(cpe, datetime) else None,
    )


# ── Shared helpers ────────────────────────────────────────────────────────────


def _epoch_to_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError):
        return None


async def _resolve_tenant_id(
    repo: TenantRepo,
    *,
    metadata_tenant: str | None = None,
    stripe_customer_id: str | None = None,
    razorpay_subscription_id: str | None = None,
    razorpay_customer_id: str | None = None,
) -> UUID | None:
    """Map a gateway object back to a tenant: metadata → stored gateway ids."""
    if metadata_tenant:
        try:
            return UUID(metadata_tenant)
        except ValueError:
            pass
    if stripe_customer_id:
        row = await repo.get_by_stripe_customer(stripe_customer_id)
        if row:
            return row["id"]
    if razorpay_subscription_id:
        row = await repo.get_by_razorpay_subscription(razorpay_subscription_id)
        if row:
            return row["id"]
    if razorpay_customer_id:
        row = await repo.get_by_razorpay_customer(razorpay_customer_id)
        if row:
            return row["id"]
    return None


# ── Stripe webhook (USD / Global) ─────────────────────────────────────────────


@router.post("/webhook/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> dict:
    """
    Stripe subscription lifecycle → universal subscription_status.
    Signature-verified; forged payloads rejected with 400. Unknown events are
    acknowledged (200) and ignored.
    """
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")

    try:
        event = billing.parse_stripe_webhook_event(payload, signature)
    except billing.BillingNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    event_type = event["type"]
    obj = event["data"]["object"]
    repo = TenantRepo(pool)

    if event_type == "checkout.session.completed":
        tenant_id = await _resolve_tenant_id(
            repo,
            metadata_tenant=(
                obj.get("client_reference_id") or (obj.get("metadata") or {}).get("tenant_id")
            ),
            stripe_customer_id=obj.get("customer"),
        )
        if tenant_id:
            await repo.update_subscription(
                tenant_id,
                status="active",
                plan=billing.QUANT_TIER_PLAN,
                stripe_customer_id=obj.get("customer"),
                stripe_subscription_id=obj.get("subscription"),
            )
            logger.info("Stripe: Quant Tier activated for tenant %s", tenant_id)

    elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
        tenant_id = await _resolve_tenant_id(
            repo,
            metadata_tenant=(obj.get("metadata") or {}).get("tenant_id"),
            stripe_customer_id=obj.get("customer"),
        )
        if tenant_id:
            sub_status = obj.get("status", "inactive")
            plan = billing.QUANT_TIER_PLAN if billing.is_active_status(sub_status) else None
            await repo.update_subscription(
                tenant_id,
                status=sub_status,
                plan=plan,
                stripe_customer_id=obj.get("customer"),
                stripe_subscription_id=obj.get("id"),
                current_period_end=_epoch_to_dt(obj.get("current_period_end")),
            )

    elif event_type == "customer.subscription.deleted":
        tenant_id = await _resolve_tenant_id(
            repo,
            metadata_tenant=(obj.get("metadata") or {}).get("tenant_id"),
            stripe_customer_id=obj.get("customer"),
        )
        if tenant_id:
            await repo.update_subscription(tenant_id, status="canceled", plan="founding_member")
            logger.info("Stripe: subscription canceled for tenant %s", tenant_id)

    elif event_type == "invoice.payment_failed":
        tenant_id = await _resolve_tenant_id(repo, stripe_customer_id=obj.get("customer"))
        if tenant_id:
            await repo.update_subscription(tenant_id, status="past_due")

    return {"received": True}


# ── Razorpay webhook (INR / India) ────────────────────────────────────────────


def _razorpay_subscription_entity(event: dict) -> dict:
    return event.get("payload", {}).get("subscription", {}).get("entity", {})


@router.post("/webhook/razorpay", status_code=status.HTTP_200_OK)
async def razorpay_webhook(
    request: Request,
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> dict:
    """
    Razorpay subscription lifecycle → universal subscription_status.
    The raw body is HMAC-verified against X-Razorpay-Signature; forged payloads
    rejected with 400. Unknown events acknowledged (200) and ignored.

    Handled: subscription.activated/.charged → active (unlock); .authenticated
    (mandate set up); .pending (retrying); .halted (revoke); .cancelled/
    .completed/.expired (end subscription).
    """
    payload = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")

    try:
        billing.verify_razorpay_webhook_signature(payload, signature)
    except billing.BillingNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON body")

    event_type = event.get("event", "")
    entity = _razorpay_subscription_entity(event)
    if not entity:
        return {"received": True}

    repo = TenantRepo(pool)
    sub_id = entity.get("id")
    customer_id = entity.get("customer_id")
    notes_tenant = (entity.get("notes") or {}).get("tenant_id")
    period_end = _epoch_to_dt(entity.get("current_end"))

    tenant_id = await _resolve_tenant_id(
        repo,
        metadata_tenant=notes_tenant,
        razorpay_subscription_id=sub_id,
        razorpay_customer_id=customer_id,
    )
    if not tenant_id:
        logger.warning("Razorpay webhook %s: could not resolve tenant (sub=%s)", event_type, sub_id)
        return {"received": True}

    if event_type in ("subscription.activated", "subscription.charged"):
        await repo.update_subscription(
            tenant_id,
            status="active",
            plan=billing.QUANT_TIER_PLAN,
            razorpay_subscription_id=sub_id,
            razorpay_customer_id=customer_id,
            current_period_end=period_end,
        )
        logger.info("Razorpay: Quant Tier active for tenant %s (%s)", tenant_id, event_type)

    elif event_type == "subscription.authenticated":
        await repo.update_subscription(
            tenant_id,
            status="authenticated",
            razorpay_subscription_id=sub_id,
            razorpay_customer_id=customer_id,
        )

    elif event_type == "subscription.pending":
        await repo.update_subscription(tenant_id, status="pending")

    elif event_type == "subscription.halted":
        await repo.update_subscription(tenant_id, status="halted")
        logger.info("Razorpay: subscription halted for tenant %s — live access revoked", tenant_id)

    elif event_type in (
        "subscription.cancelled",
        "subscription.completed",
        "subscription.expired",
    ):
        new_status = event_type.split(".", 1)[1]  # cancelled | completed | expired
        await repo.update_subscription(tenant_id, status=new_status, plan="founding_member")
        logger.info("Razorpay: subscription %s for tenant %s", new_status, tenant_id)

    return {"received": True}
