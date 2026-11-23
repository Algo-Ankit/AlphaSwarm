"""
Swarm Tax monthly billing.

Charges every active strategy_subscription 1% of its allocated_capital on the 1st of
each month (the "Swarm Tax"). Revenue is split 50 / 50 between the platform and the
strategy creator and recorded in the creator_balances ledger.

Charge flow:
  1. Try Stripe (USD) if the subscriber's tenant has a stripe_customer_id with a
     saved card.
  2. Fall back to Razorpay (INR) if a razorpay_customer_id is present.
  3. If neither gateway has a stored method, mark the subscription as 'exempt'
     (paper / no card on file) — a non-blocking state.

Idempotency: the task skips subscriptions whose last_billed_at is within the last
30 days, so it is safe to re-run after a partial failure.
"""

import asyncio
import logging
from decimal import Decimal

from app.core.celery_app import celery_app
from app.core.config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()


def _get_pool():
    import asyncpg

    return asyncpg.create_pool(
        _settings.database_url.replace("postgresql+asyncpg://", "postgresql://"),
        min_size=1,
        max_size=3,
    )


@celery_app.task(name="app.worker.billing_tasks.charge_swarm_tax")
def charge_swarm_tax() -> None:
    asyncio.run(_charge_swarm_tax_async())


async def _charge_swarm_tax_async() -> None:
    from app.domain.broker_routing import currency_for_exchange

    pool = await _get_pool()
    try:
        subs = await pool.fetch(
            """
            SELECT
                ss.id,
                ss.subscriber_tenant_id,
                ss.allocated_capital,
                ps.creator_tenant_id,
                s.exchange,
                t.stripe_customer_id,
                t.razorpay_customer_id
            FROM strategy_subscriptions ss
            JOIN public_strategies ps ON ps.id = ss.public_strategy_id
            JOIN strategies s ON s.id = ps.strategy_id
            JOIN tenants t ON t.id = ss.subscriber_tenant_id
            WHERE ss.is_active
              AND (
                  ss.last_billed_at IS NULL
                  OR ss.last_billed_at < now() - INTERVAL '30 days'
              )
            """
        )
        if not subs:
            logger.info("charge_swarm_tax: no subscriptions due")
            return

        logger.info("charge_swarm_tax: processing %d subscription(s)", len(subs))

        for row in subs:
            sub_id = row["id"]
            creator_tenant_id = row["creator_tenant_id"]
            allocated = Decimal(str(row["allocated_capital"]))
            strategy_currency = currency_for_exchange(row.get("exchange") or "NASDAQ")

            swarm_tax = (allocated * Decimal("0.01")).quantize(Decimal("0.01"))
            if swarm_tax < Decimal("0.02"):
                # Below $0.02 / ₹0.02, a 50/50 split rounds creator_share to 0.00,
                # which would violate creator_balances CHECK (amount > 0).
                await pool.execute(
                    """
                    UPDATE strategy_subscriptions
                    SET last_billed_at = now(), fee_status = 'exempt', updated_at = now()
                    WHERE id = $1
                    """,
                    sub_id,
                )
                continue

            # When Stripe collects, it always charges USD; record the ledger in USD
            # so creator_balances.currency matches the actual collected currency.
            from app.domain.broker_routing import convert_amount

            billed_currency = (
                "USD"
                if (row["stripe_customer_id"] and strategy_currency != "USD")
                else strategy_currency
            )
            ledger_tax = convert_amount(swarm_tax, strategy_currency, billed_currency).quantize(
                Decimal("0.01")
            )
            creator_share = (ledger_tax / 2).quantize(Decimal("0.01"))
            platform_share = ledger_tax - creator_share

            try:
                fee_status = _attempt_charge(
                    sub_id=str(sub_id),
                    amount_usd=float(swarm_tax),
                    stripe_customer_id=row["stripe_customer_id"],
                    razorpay_customer_id=row["razorpay_customer_id"],
                    currency=strategy_currency,
                )
            except Exception as exc:
                logger.warning("charge_swarm_tax: billing failed sub=%s: %s", sub_id, exc)
                # Deliberately do NOT bump last_billed_at: nothing was collected,
                # so the subscription stays due and a re-run retries it instead of
                # silently writing the month off.
                await pool.execute(
                    """
                    UPDATE strategy_subscriptions
                    SET fee_status = 'failed', updated_at = now()
                    WHERE id = $1
                    """,
                    sub_id,
                )
                continue

            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """
                        UPDATE strategy_subscriptions
                        SET last_billed_at = now(), fee_status = $2, updated_at = now()
                        WHERE id = $1
                        """,
                        sub_id,
                        fee_status,
                    )
                    if fee_status == "charged" and creator_share > 0 and platform_share > 0:
                        await conn.execute(
                            """
                            INSERT INTO creator_balances
                                (creator_tenant_id, subscription_id, amount, currency, credit_type)
                            VALUES ($1, $2, $3, $4, 'creator_share')
                            """,
                            creator_tenant_id,
                            sub_id,
                            float(creator_share),
                            billed_currency,
                        )
                        await conn.execute(
                            """
                            INSERT INTO creator_balances
                                (creator_tenant_id, subscription_id, amount, currency, credit_type)
                            VALUES ($1, $2, $3, $4, 'platform_share')
                            """,
                            creator_tenant_id,
                            sub_id,
                            float(platform_share),
                            billed_currency,
                        )

            logger.info(
                "charge_swarm_tax: sub=%s tax=%.2f %s status=%s creator=%.2f platform=%.2f",
                sub_id,
                ledger_tax,
                billed_currency,
                fee_status,
                creator_share,
                platform_share,
            )
    finally:
        await pool.close()


def _attempt_charge(
    sub_id: str,
    amount_usd: float,
    stripe_customer_id: str | None,
    razorpay_customer_id: str | None,
    *,
    currency: str = "USD",
) -> str:
    """
    Charge the subscriber's saved payment method.

    Converts the strategy-denominated tax (`amount_usd` in `currency`) into USD cents
    for Stripe or INR paise for Razorpay via `broker_routing.convert_amount`.

    Returns the resulting fee_status:
      'charged'  — money actually collected (Stripe off-session PaymentIntent).
      'invoiced' — a Razorpay order was created that the customer must still pay.
                   NOT revenue yet: the creator ledger must NOT be credited until
                   a payment webhook confirms collection.
      'exempt'   — no gateway with a saved method (paper user, no card on file).

    Raises on gateway errors so the caller can log and mark 'failed'.
    """
    from app.domain.broker_routing import convert_amount
    from app.services.billing import BillingNotConfigured

    raw_amt = Decimal(str(amount_usd))
    usd_amt = convert_amount(raw_amt, currency, "USD")
    inr_amt = convert_amount(raw_amt, currency, "INR")

    amount_cents = round(float(usd_amt) * 100)
    amount_paise = round(float(inr_amt) * 100)
    if amount_cents <= 0 and amount_paise <= 0:
        return "exempt"

    if stripe_customer_id and amount_cents > 0:
        try:
            from app.services.billing import _stripe_client  # type: ignore[attr-defined]

            stripe = _stripe_client()
            methods = stripe.PaymentMethod.list(customer=stripe_customer_id, type="card")
            if not methods.data:
                # Customer exists but has no saved card — fall through to exempt.
                pass
            else:
                pm = methods.data[0]
                stripe.PaymentIntent.create(
                    amount=amount_cents,
                    currency="usd",
                    customer=stripe_customer_id,
                    payment_method=pm.id,
                    confirm=True,
                    description=f"AlphaSwarm Swarm Tax — subscription {sub_id}",
                    metadata={"subscription_id": sub_id, "fee_type": "swarm_tax"},
                    off_session=True,
                )
                return "charged"
        except BillingNotConfigured:
            pass  # Stripe not configured — try Razorpay next.

    if razorpay_customer_id and amount_paise > 0:
        try:
            from app.services.billing import _razorpay_client  # type: ignore[attr-defined]

            client = _razorpay_client()
            client.order.create(
                {
                    "amount": amount_paise,
                    "currency": "INR",
                    "payment_capture": 1,
                    "notes": {"subscription_id": sub_id, "fee_type": "swarm_tax"},
                }
            )
            return "invoiced"
        except BillingNotConfigured:
            pass

    return "exempt"  # No configured gateway with a saved method.
