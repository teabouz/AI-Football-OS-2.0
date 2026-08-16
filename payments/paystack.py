"""
Thin wrapper around the Paystack Transactions API.
Docs: https://paystack.com/docs/payments/accept-payments/

Two verification paths are supported, matching how real deployments work:
  1. Webhook (payment_server.py) — Paystack calls us on charge.success.
     Fast, but needs a public URL, so it's the production path.
  2. Manual "I've paid" refresh (handlers/payments.py) — the bot calls
     Paystack's verify endpoint directly. Works with zero infra, so it's the
     good default for local dev / early testing, and also a solid fallback
     if a webhook delivery is ever missed.

Both paths end up calling the same DB update in handlers/subscription.py:
mark_user_premium().
"""
import hashlib
import hmac
import uuid

import httpx
import requests

import config

PAYSTACK_BASE_URL = "https://api.paystack.co"


def new_reference(telegram_id: int) -> str:
    """Unique, traceable transaction reference: tg<id>_<random>."""
    return f"tg{telegram_id}_{uuid.uuid4().hex[:10]}"


async def initialize_transaction(email: str, amount_kobo: int, reference: str) -> dict:
    """Create a Paystack transaction and return its data (incl. authorization_url)."""
    headers = {
        "Authorization": f"Bearer {config.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "email": email,
        "amount": amount_kobo,
        "reference": reference,
        "currency": "NGN",
        "callback_url": f"{config.PUBLIC_BASE_URL}/paystack/callback",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{PAYSTACK_BASE_URL}/transaction/initialize", json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def verify_transaction(reference: str) -> dict:
    """Async verify — used from Telegram bot handlers."""
    headers = {"Authorization": f"Bearer {config.PAYSTACK_SECRET_KEY}"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}", headers=headers)
        resp.raise_for_status()
        return resp.json()


def verify_transaction_sync(reference: str) -> dict:
    """Sync verify — used from the Flask webhook server."""
    headers = {"Authorization": f"Bearer {config.PAYSTACK_SECRET_KEY}"}
    resp = requests.get(f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}", headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def verify_webhook_signature(raw_body: bytes, signature_header: str) -> bool:
    """Paystack signs webhook payloads with HMAC-SHA512 of the raw body,
    using your secret key. Always check this before trusting a webhook."""
    if not signature_header or not config.PAYSTACK_SECRET_KEY:
        return False
    computed = hmac.new(
        config.PAYSTACK_SECRET_KEY.encode("utf-8"), raw_body, hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(computed, signature_header)
