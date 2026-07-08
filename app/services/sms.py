"""
Transactional SMS dispatch (Twilio).

Mirrors ``services/email.py``: when Twilio is not configured (local dev / CI /
admin testing) every send degrades to a single ``logger.info`` line that
INCLUDES the message body — so during development you can read the OTP straight
out of the server log and sign in without any SMS gateway or real phone.

Sends are best-effort and never raise into the caller's request.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def send_sms_sync(to_phone: str, body: str) -> bool:
    """
    Blocking SMS dispatch. Returns True if accepted or stubbed; never raises.

    In stub mode the body is logged verbatim — this is intentional so a
    developer/admin can retrieve a login OTP without a live SMS provider. Do NOT
    enable debug logging with a real provider in production.
    """
    settings = get_settings()
    sid = settings.twilio_account_sid
    token = settings.twilio_auth_token
    from_number = settings.twilio_from_number

    if not (sid and token and from_number):
        logger.info("[sms stub] to=%s body=%r (Twilio not configured)", to_phone, body)
        return True

    try:
        from twilio.rest import Client

        Client(sid, token).messages.create(to=to_phone, from_=from_number, body=body)
        return True
    except Exception as exc:  # pragma: no cover - network/SDK errors
        logger.warning("Twilio send failed for %s: %s", to_phone, exc)
        return False


async def send_sms(to_phone: str, body: str) -> bool:
    """Async wrapper — runs the blocking SDK in a worker thread."""
    return await asyncio.to_thread(send_sms_sync, to_phone, body)


async def send_login_otp_sms(to_phone: str, code: str) -> bool:
    body = f"{code} is your AlphaSwarm login code. It expires in 10 minutes. Do not share it."
    return await send_sms(to_phone, body)
