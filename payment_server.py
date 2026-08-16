"""
Public-facing payment server — separate from the bot process and from the
(basic-auth-protected) admin dashboard, because Paystack needs to reach this
without any auth.

Run:
    python payment_server.py
Then either:
  - point PUBLIC_BASE_URL (in .env) at wherever this is reachable, and
    register {PUBLIC_BASE_URL}/paystack/webhook in your Paystack dashboard
    under Settings -> API Keys & Webhooks, OR
  - skip the webhook entirely and rely on the bot's "✅ I've Paid" button,
    which verifies directly with Paystack (see handlers/payments.py).

Both paths call the same subscription.mark_user_premium().
"""
import logging
from datetime import datetime, timezone

from flask import Flask, request, jsonify

from database import SessionLocal, init_db
from models import Payment, PaymentStatus, User
from handlers.subscription import mark_user_premium
from payments import paystack
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/paystack/webhook", methods=["POST"])
def paystack_webhook():
    signature = request.headers.get("X-Paystack-Signature", "")
    raw_body = request.get_data()

    if not paystack.verify_webhook_signature(raw_body, signature):
        logger.warning("Rejected webhook with invalid signature")
        return jsonify({"status": "invalid signature"}), 401

    event = request.get_json(silent=True) or {}
    if event.get("event") != "charge.success":
        return jsonify({"status": "ignored"}), 200

    reference = event.get("data", {}).get("reference")
    if not reference:
        return jsonify({"status": "no reference"}), 400

    # Defense in depth: don't just trust the webhook payload — re-verify
    # directly with Paystack's API before crediting the account.
    try:
        result = paystack.verify_transaction_sync(reference)
    except Exception:
        logger.exception("Failed to verify transaction %s", reference)
        return jsonify({"status": "verify failed"}), 502

    if result.get("data", {}).get("status") != "success":
        return jsonify({"status": "not successful"}), 200

    session = SessionLocal()
    try:
        payment = session.query(Payment).filter_by(reference=reference).first()
        if not payment:
            logger.warning("Webhook for unknown reference %s", reference)
            return jsonify({"status": "unknown reference"}), 404

        if payment.status != PaymentStatus.SUCCESS:
            payment.status = PaymentStatus.SUCCESS
            payment.verified_at = datetime.now(timezone.utc).replace(tzinfo=None)
            user = session.query(User).filter_by(id=payment.user_id).first()
            mark_user_premium(session, user, days=config.PREMIUM_DURATION_DAYS)
            logger.info("Upgraded user %s to Premium via webhook (ref %s)", user.telegram_id, reference)

        return jsonify({"status": "ok"}), 200
    finally:
        session.close()


@app.route("/paystack/callback", methods=["GET"])
def paystack_callback():
    """Browser redirect target after payment. Purely informational — the bot
    itself confirms the upgrade via webhook or the 'I've Paid' button."""
    return (
        "<html><body style='font-family:sans-serif; text-align:center; padding:4rem;'>"
        "<h2>✅ Payment received</h2>"
        "<p>Head back to Telegram and tap <b>\"I've Paid — Refresh\"</b> "
        "on the payment message to confirm your upgrade.</p>"
        "</body></html>",
        200,
    )


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5001, debug=False)
