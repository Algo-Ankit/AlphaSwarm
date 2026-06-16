"""
Billing API — Razorpay recurring subscriptions for the Quant Tier (UPI AutoPay /
e-mandate). India-first; replaces the RBI-restricted Stripe flow.

  POST /v1/billing/subscribe   (auth)  → Razorpay subscription + hosted auth URL
  POST /v1/billing/webhook     (public, HMAC-verified) → subscription lifecycle
  GET  /v1/billing/subscription (auth) → current tenant subscription status

Live agent deployment is gated on `subscription_status` (see app/api/routes.py).
The webhook is the single source of truth that flips that status.
"""

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, get_current_user, get_db_pool
from app.db.repositories.users import TenantRepo
from app.services import billing

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/billing", tags=["billing"])


class SubscribeResponse(BaseModel):
    subscription_id: str
    # Razorpay hosted page where the user authorizes the UPI AutoPay mandate.
    authorization_url: str | None
    status: str | None


class SubscriptionResponse(BaseModel):
    plan: str
    subscription_status: str
    is_active: bool
    current_period_end: str | None


@router.post("/subscribe", response_model=SubscribeResponse)
async def create_subscription(
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> SubscribeResponse:
    """Start a Quant Tier recurring subscription for the current tenant."""
    repo = TenantRepo(pool)
    tenant = await repo.get_by_id(current_user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    try:
        result = billing.create_subscription(
            tenant_id=str(current_user.tenant_id),
            customer_email=current_user.email,
        )
    except billing.BillingNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        logger.exception("Razorpay subscription creation failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not create subscription with Razorpay",
        ) from exc

    # Persist the subscription id immediately so the webhook can map it back even
    # before the user finishes authorizing the mandate.
    await repo.update_subscription(
        current_user.tenant_id,
        status=result.get("status") or "created",
        razorpay_subscription_id=result["id"],
    )

    return SubscribeResponse(
        subscription_id=result["id"],
        authorization_url=result.get("short_url"),
        status=result.get("status"),
    )


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


def _epoch_to_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def _subscription_entity(event: dict) -> dict:
    """Pull the subscription entity out of a Razorpay webhook payload."""
    return event.get("payload", {}).get("subscription", {}).get("entity", {})


async def _resolve_tenant_id(
    repo: TenantRepo,
    *,
    notes_tenant: str | None,
    subscription_id: str | None,
    customer_id: str | None,
) -> UUID | None:
    """Map a Razorpay subscription back to a tenant: notes → sub id → customer id."""
    if notes_tenant:
        try:
            return UUID(notes_tenant)
        except ValueError:
            pass
    if subscription_id:
        row = await repo.get_by_razorpay_subscription(subscription_id)
        if row:
            return row["id"]
    if customer_id:
        row = await repo.get_by_razorpay_customer(customer_id)
        if row:
            return row["id"]
    return None


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def razorpay_webhook(
    request: Request,
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> dict:
    """
    Handle Razorpay subscription lifecycle events. The raw body is HMAC-verified
    against X-Razorpay-Signature; forged/tampered payloads are rejected with 400.
    Unknown event types are acknowledged (200) and ignored so Razorpay does not
    retry them.

    Handled events:
      subscription.activated / .charged → active (unlocks live trading)
      subscription.authenticated        → mandate set up (not yet charged)
      subscription.pending              → a charge failed, retrying
      subscription.halted               → retries exhausted → revoke live access
      subscription.cancelled / .completed / .expired → end subscription
    """
    payload = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")

    try:
        billing.verify_webhook_signature(payload, signature)
    except billing.BillingNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON body")

    event_type = event.get("event", "")
    entity = _subscription_entity(event)
    if not entity:
        return {"received": True}

    repo = TenantRepo(pool)
    sub_id = entity.get("id")
    customer_id = entity.get("customer_id")
    notes_tenant = (entity.get("notes") or {}).get("tenant_id")
    period_end = _epoch_to_dt(entity.get("current_end"))

    tenant_id = await _resolve_tenant_id(
        repo,
        notes_tenant=notes_tenant,
        subscription_id=sub_id,
        customer_id=customer_id,
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
        logger.info("Quant Tier active for tenant %s (%s)", tenant_id, event_type)

    elif event_type == "subscription.authenticated":
        # Mandate authorized but not yet charged — record it, no live access yet.
        await repo.update_subscription(
            tenant_id,
            status="authenticated",
            razorpay_subscription_id=sub_id,
            razorpay_customer_id=customer_id,
        )

    elif event_type == "subscription.pending":
        await repo.update_subscription(tenant_id, status="pending")

    elif event_type == "subscription.halted":
        # Recurring charge retries exhausted — revoke live access immediately.
        await repo.update_subscription(tenant_id, status="halted")
        logger.info("Subscription halted for tenant %s — live access revoked", tenant_id)

    elif event_type in (
        "subscription.cancelled",
        "subscription.completed",
        "subscription.expired",
    ):
        new_status = event_type.split(".", 1)[1]  # cancelled | completed | expired
        await repo.update_subscription(
            tenant_id,
            status=new_status,
            plan="founding_member",
        )
        logger.info("Subscription %s for tenant %s — reverted to paper-only", new_status, tenant_id)

    return {"received": True}
