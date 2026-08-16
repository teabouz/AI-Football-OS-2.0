"""
Cross-process Telegram notifications — Phase 7.

Most of the bot's notifications happen naturally inside the bot process
(e.g. handlers/marketplace.py can just `await context.bot.send_message(...)`
directly). But some marketplace actions happen in coach_dashboard.py, a
separate Flask process with no running bot instance to call methods on —
e.g. a coach accepting an application, or expressing interest in equipment,
both done from the web dashboard.

Rather than spin up a second async Bot connection inside a sync Flask
route, this just calls Telegram's HTTP API directly with `requests` — the
same pattern already used for Paystack's sync verification in
payments/paystack.py. Best-effort: a failed notification (e.g. the user
blocked the bot) shouldn't break the action that triggered it.
"""
import logging

import requests

import config

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


def send_telegram_message(chat_id: int, text: str) -> bool:
    """Best-effort send. Returns True on success, False on any failure
    (logged, never raised) — a notification failing should never break the
    coach's action that triggered it."""
    if not config.BOT_TOKEN:
        logger.warning("Cannot send notification: TELEGRAM_BOT_TOKEN not configured")
        return False
    try:
        resp = requests.post(
            f"{TELEGRAM_API_BASE}/bot{config.BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("Telegram notification failed (%s): %s", resp.status_code, resp.text[:200])
            return False
        return True
    except requests.RequestException:
        logger.exception("Telegram notification request failed")
        return False
