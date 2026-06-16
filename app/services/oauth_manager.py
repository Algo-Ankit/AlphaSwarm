"""
OAuth Manager for Indian & US broker integrations.

Upstox  — Standard OAuth2 authorization-code flow (platform-level client_id).
Zerodha — Kite Connect request-token flow (user-level api_key, redirect to Zerodha).
AngelOne — Credential-based TOTP API login (no redirect; user enters clientcode + mpin + totp).

The 401-retry helper wraps any executor call: on HTTP 401 it refreshes the
access token via refresh_fn, updates the DB, then retries once.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)


# ── Upstox OAuth2 ─────────────────────────────────────────────────────────────
_UPSTOX_AUTH_URL  = "https://api.upstox.com/v2/login/authorization/dialog"
_UPSTOX_TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"


def upstox_login_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{_UPSTOX_AUTH_URL}?{urlencode(params)}"


async def upstox_exchange_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> dict:
    """Exchange authorization code → {access_token, refresh_token, expires_in}."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            _UPSTOX_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )
    if resp.status_code != 200:
        raise ValueError(f"Upstox token exchange failed: HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    return {
        "access_token": data["access_token"],
        # Upstox may return extended_token as a long-lived refresh token
        "refresh_token": data.get("extended_token") or data.get("refresh_token", ""),
        "expires_in": int(data.get("expires_in", 86400)),
    }


async def upstox_refresh_access_token(
    client_id: str,
    client_secret: str,
    extended_token: str,
) -> dict:
    """Refresh an expired Upstox access token."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            _UPSTOX_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": extended_token,
            },
            headers={"Accept": "application/json"},
        )
    if resp.status_code != 200:
        raise ValueError(f"Upstox token refresh failed: HTTP {resp.status_code}")
    data = resp.json()
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("extended_token", extended_token),
        "expires_in": int(data.get("expires_in", 86400)),
    }


# ── Zerodha Kite Connect ──────────────────────────────────────────────────────
_ZERODHA_LOGIN_BASE = "https://kite.zerodha.com/connect/login"
_ZERODHA_TOKEN_URL  = "https://api.kite.trade/session/token"


def zerodha_login_url(api_key: str) -> str:
    return f"{_ZERODHA_LOGIN_BASE}?v=3&api_key={api_key}"


async def zerodha_exchange_code(api_key: str, api_secret: str, request_token: str) -> dict:
    """Exchange request_token for access_token (Zerodha SHA-256 checksum auth)."""
    raw = api_key + request_token + api_secret
    checksum = hashlib.sha256(raw.encode()).hexdigest()

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            _ZERODHA_TOKEN_URL,
            data={"api_key": api_key, "request_token": request_token, "checksum": checksum},
            headers={"X-Kite-Version": "3"},
        )
    if resp.status_code != 200:
        raise ValueError(f"Zerodha token exchange failed: HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json().get("data", {})
    return {
        "access_token": data.get("access_token", ""),
        "refresh_token": "",   # Zerodha tokens expire EOD; no server-side refresh
        "expires_in": 86400,
    }


# ── AngelOne (credential-based, no OAuth redirect) ────────────────────────────
_ANGELONE_LOGIN_URL = (
    "https://apiconnect.angelbroking.com/rest/auth/angelbroking/user/v1/loginByPassword"
)


async def angelone_login(client_id: str, password: str, totp: str) -> dict:
    """Login to AngelOne with clientcode + mpin + TOTP. Returns JWT tokens."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-UserType": "USER",
        "X-SourceID": "WEB",
        "X-ClientLocalIP": "127.0.0.1",
        "X-ClientPublicIP": "127.0.0.1",
        "X-MACAddress": "fe80::1",
        "X-PrivateKey": client_id,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            _ANGELONE_LOGIN_URL,
            json={"clientcode": client_id, "password": password, "totp": totp},
            headers=headers,
        )
    if resp.status_code != 200:
        raise ValueError(f"AngelOne login failed: HTTP {resp.status_code}: {resp.text[:200]}")
    body = resp.json()
    if not body.get("status"):
        raise ValueError(f"AngelOne login rejected: {body.get('message', 'Unknown error')}")
    data = body.get("data", {})
    return {
        "access_token": data.get("jwtToken", ""),
        "refresh_token": data.get("refreshToken", ""),
        "expires_in": 86400,
    }


# ── Shared helpers ─────────────────────────────────────────────────────────────

def token_expires_at(expires_in: int) -> datetime:
    """Return UTC datetime when a token with the given TTL (seconds) expires."""
    # Subtract 60s as safety margin
    return datetime.now(timezone.utc) + timedelta(seconds=max(0, expires_in - 60))


async def retry_on_401(executor_fn, refresh_fn):
    """
    Call executor_fn(); on 401/AuthorizationError call refresh_fn() to get a new
    access token, then retry once.

    executor_fn: async () → result
    refresh_fn:  async () → str  (the new access token, already persisted to DB)
    """
    try:
        return await executor_fn()
    except Exception as exc:
        msg = str(exc).lower()
        if "401" not in msg and "unauthorized" not in msg and "forbidden" not in msg:
            raise
        logger.info("Got 401 — refreshing broker token and retrying")
        try:
            await refresh_fn()
        except Exception as re:
            raise ValueError(f"Token refresh failed: {re}") from re
        return await executor_fn()
