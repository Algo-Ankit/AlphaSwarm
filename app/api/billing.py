"""
Billing API — Stripe Checkout + webhook for the Quant Tier subscription.

  POST /v1/billing/checkout  (auth)  → Stripe Checkout Session URL
  POST /v1/billing/webhook   (public, signature-verified) → subscription lifecycle
  GET  /v1/billing/subscription (auth) → current tenant subscription status

Live agent deployment is gated on `subscription_status` (see app/api/routes.py).
The webhook is the single source of truth that flips that status.
"""

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


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class SubscriptionResponse(BaseModel):
    plan: str
    subscription_status: str
    is_active: bool
    current_period_end: str | None


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    current_user: CurrentUser = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> CheckoutResponse:
    """Start a Quant Tier subscription checkout for the current tenant."""
    repo = TenantRepo(pool)
    tenant = await repo.get_by_id(current_user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    try:
        result = billing.create_checkout_session(
            tenant_id=str(current_user.tenant_id),
            customer_email=current_user.email,
            stripe_customer_id=tenant.get("stripe_customer_id"),
        )
    except billing.BillingNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        logger.exception("Stripe checkout session creation failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not create checkout session with Stripe",
        ) from exc

    return CheckoutResponse(checkout_url=result["url"], session_id=result["id"])


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


async def _resolve_tenant_id(
    repo: TenantRepo, *, metadata_tenant: str | None, customer_id: str | None
) -> UUID | None:
    """Map a Stripe object back to a tenant via metadata first, then customer id."""
    if metadata_tenant:
        try:
            return UUID(metadata_tenant)
        except ValueError:
            pass
    if customer_id:
        row = await repo.get_by_stripe_customer(customer_id)
        if row:
            return row["id"]
    return None


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> dict:
    """
    Handle Stripe subscription lifecycle events. Signature-verified; unverified
    payloads are rejected with 400. Unknown event types are acknowledged (200)
    and ignored so Stripe does not retry them.
    """
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")

    try:
        event = billing.parse_webhook_event(payload, signature)
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
            customer_id=obj.get("customer"),
        )
        if tenant_id:
            await repo.update_subscription(
                tenant_id,
                status="active",
                plan=billing.QUANT_TIER_PLAN,
                stripe_customer_id=obj.get("customer"),
                stripe_subscription_id=obj.get("subscription"),
            )
            logger.info("Quant Tier activated for tenant %s", tenant_id)

    elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
        tenant_id = await _resolve_tenant_id(
            repo,
            metadata_tenant=(obj.get("metadata") or {}).get("tenant_id"),
            customer_id=obj.get("customer"),
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
            customer_id=obj.get("customer"),
        )
        if tenant_id:
            # Subscription ended — revoke live access, drop back to free plan.
            await repo.update_subscription(
                tenant_id,
                status="canceled",
                plan="founding_member",
            )
            logger.info("Subscription canceled for tenant %s — reverted to paper-only", tenant_id)

    elif event_type == "invoice.payment_failed":
        tenant_id = await _resolve_tenant_id(
            repo,
            metadata_tenant=None,
            customer_id=obj.get("customer"),
        )
        if tenant_id:
            await repo.update_subscription(tenant_id, status="past_due")

    return {"received": True}
