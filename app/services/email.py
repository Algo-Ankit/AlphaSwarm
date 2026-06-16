"""
Transactional email dispatch (SendGrid).

Replaces the old console-print stubs. When ``sendgrid_api_key`` is unset (local
dev / CI) every send degrades gracefully to a single ``logger.info`` line so the
rest of the app behaves identically with or without SendGrid configured.

Sends are best-effort: a delivery failure NEVER propagates into the caller's
request/transaction. Email is a side-channel, not part of the critical path.

The SendGrid SDK is synchronous; ``send_email`` runs it in a thread so it never
blocks the asyncio event loop. Worker (sync) callers can use ``send_email_sync``.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _render_welcome(display_name: str) -> tuple[str, str]:
    subject = "Welcome to AlphaSwarm — verify your account"
    html = f"""
    <h2>Welcome aboard, {display_name}!</h2>
    <p>Your AlphaSwarm account is ready. You can now build strategies, run
    backtests, and paper-trade across global and Indian markets.</p>
    <p>To deploy <strong>live</strong> agents on NSE/BSE or US markets, upgrade to
    the <strong>Quant Tier</strong> from your dashboard.</p>
    <p>Happy trading,<br/>The AlphaSwarm Team</p>
    """
    return subject, html


def _render_rebalance_approval(strategy_name: str, body_text: str) -> tuple[str, str]:
    subject = f"Action required: rebalance approval for “{strategy_name}”"
    html = f"""
    <h2>Rebalance approval required</h2>
    <p>{body_text}</p>
    <p>Your AI co-pilot will <strong>not</strong> execute this rebalance until you
    approve it. Open the AlphaSwarm notification center to review and approve.</p>
    <p>— AlphaSwarm</p>
    """
    return subject, html


def send_email_sync(to_email: str, subject: str, html: str) -> bool:
    """
    Blocking SendGrid dispatch. Returns True if accepted (2xx) or stubbed.
    Never raises — logs and returns False on failure.
    """
    settings = get_settings()
    api_key = settings.sendgrid_api_key

    if not api_key:
        logger.info(
            "[email stub] to=%s subject=%r (SendGrid not configured — set SENDGRID_API_KEY)",
            to_email,
            subject,
        )
        return True

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Content, Email, Mail, To

        message = Mail(
            from_email=Email(settings.email_from, settings.email_from_name),
            to_emails=To(to_email),
            subject=subject,
            html_content=Content("text/html", html),
        )
        resp = SendGridAPIClient(api_key).send(message)
        if 200 <= resp.status_code < 300:
            return True
        logger.warning("SendGrid returned HTTP %s for %s", resp.status_code, to_email)
        return False
    except Exception as exc:  # pragma: no cover - network/SDK errors
        logger.warning("SendGrid send failed for %s: %s", to_email, exc)
        return False


async def send_email(to_email: str, subject: str, html: str) -> bool:
    """Async wrapper — runs the blocking SDK in a worker thread."""
    return await asyncio.to_thread(send_email_sync, to_email, subject, html)


async def send_welcome_email(to_email: str, display_name: str) -> bool:
    subject, html = _render_welcome(display_name)
    return await send_email(to_email, subject, html)


async def send_rebalance_approval_email(to_email: str, strategy_name: str, body_text: str) -> bool:
    subject, html = _render_rebalance_approval(strategy_name, body_text)
    return await send_email(to_email, subject, html)
