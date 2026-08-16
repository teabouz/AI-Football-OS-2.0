"""
Phase 2 payment flow.

  [⭐ Upgrade to Premium] -> (collect email if we don't have one yet)
                          -> create a Payment row + Paystack transaction
                          -> send a "Pay Now" link button
                          -> user pays in their browser
                          -> two ways the bot finds out:
                               a) payment_server.py webhook (production)
                               b) user taps "✅ I've Paid" -> we verify directly
"""
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
)

from database import SessionLocal
from models import User, Payment, PaymentStatus
from payments import paystack
from handlers.subscription import mark_user_premium
import config
import keyboards

logger = logging.getLogger(__name__)

ASK_EMAIL = range(1)[0]


def _looks_like_email(text: str) -> bool:
    return "@" in text and "." in text.split("@")[-1] and " " not in text


async def upgrade_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not config.PAYSTACK_SECRET_KEY:
        await query.edit_message_text(
            "💳 Payments aren't configured on this bot yet (missing PAYSTACK_SECRET_KEY). "
            "Contact the bot owner to be upgraded manually in the meantime.",
            reply_markup=keyboards.back_to_menu_keyboard(),
        )
        return ConversationHandler.END

    session = SessionLocal()
    try:
        tg_user = update.effective_user
        user = session.query(User).filter_by(telegram_id=tg_user.id).first()
        if not user or not user.registration_complete:
            await query.edit_message_text("Send /start first to set up your profile.")
            return ConversationHandler.END

        if user.email:
            await _create_and_send_payment_link(query.message, context, user.id, user.email)
            return ConversationHandler.END

        await query.edit_message_text(
            "📧 Quick step first — what email should we send your payment receipt to?"
        )
        return ASK_EMAIL
    finally:
        session.close()


async def receive_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    if not _looks_like_email(email):
        await update.message.reply_text("That doesn't look like a valid email — try again (e.g. you@example.com):")
        return ASK_EMAIL

    session = SessionLocal()
    try:
        tg_user = update.effective_user
        user = session.query(User).filter_by(telegram_id=tg_user.id).first()
        user.email = email
        session.commit()
        await _create_and_send_payment_link(update.message, context, user.id, email)
    finally:
        session.close()
    return ConversationHandler.END


async def _create_and_send_payment_link(message, context, user_id: int, email: str):
    session = SessionLocal()
    try:
        reference = paystack.new_reference(telegram_id=message.chat.id)
        session.add(Payment(
            user_id=user_id,
            reference=reference,
            amount_kobo=config.PREMIUM_PRICE_KOBO,
            currency="NGN",
            status=PaymentStatus.PENDING,
        ))
        session.commit()

        try:
            result = await paystack.initialize_transaction(
                email=email, amount_kobo=config.PREMIUM_PRICE_KOBO, reference=reference
            )
        except Exception:
            logger.exception("Paystack initialize_transaction failed for reference=%s", reference)
            await message.reply_text(
                "⚠️ Couldn't reach Paystack just now. Please try again shortly."
            )
            return

        auth_url = result.get("data", {}).get("authorization_url")
        if not auth_url:
            await message.reply_text("⚠️ Paystack didn't return a payment link. Please try again.")
            return

        naira = config.PREMIUM_PRICE_KOBO / 100
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💳 Pay ₦{naira:,.0f} with Paystack", url=auth_url)],
            [InlineKeyboardButton("✅ I've Paid — Refresh", callback_data=f"pay:refresh:{reference}")],
            [InlineKeyboardButton("⬅️ Back to Menu", callback_data="menu:main")],
        ])
        await message.reply_text(
            "Tap below to pay securely via Paystack. Once it's done, come back and tap "
            "*\"I've Paid\"* and I'll confirm your upgrade.",
            parse_mode="Markdown",
            reply_markup=markup,
        )
    finally:
        session.close()


async def refresh_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    reference = query.data.split(":", 2)[2]

    session = SessionLocal()
    try:
        caller = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        payment = session.query(Payment).filter_by(reference=reference).first()
        # The reference has high entropy and is only ever shown privately to
        # the paying user, so this is defense-in-depth rather than a
        # practically-exploited hole -- but never credit premium to whoever
        # happens to hold a reference without confirming it's actually theirs.
        if not payment or not caller or payment.user_id != caller.id:
            await query.edit_message_text("Couldn't find that payment. Please start again from the menu.")
            return

        if payment.status == PaymentStatus.SUCCESS:
            await query.edit_message_text(
                "⭐ You're already Premium — enjoy! Open the menu any time with /menu.",
                reply_markup=keyboards.back_to_menu_keyboard(),
            )
            return

        try:
            result = await paystack.verify_transaction(reference)
        except Exception:
            logger.exception("Paystack verify_transaction failed for reference=%s", reference)
            await query.answer("Couldn't reach Paystack — try again in a moment.", show_alert=True)
            return

        data = result.get("data", {})
        if data.get("status") == "success":
            from datetime import datetime
            payment.status = PaymentStatus.SUCCESS
            payment.verified_at = datetime.utcnow()
            user = session.query(User).filter_by(id=payment.user_id).first()
            mark_user_premium(session, user, days=config.PREMIUM_DURATION_DAYS)
            await query.edit_message_text(
                f"🎉 Payment confirmed — you're Premium for the next {config.PREMIUM_DURATION_DAYS} days!\n\n"
                "Open /menu to explore your Development Plan, Goals, Daily Check-in, and more.",
            )
        else:
            await query.answer("No successful payment found yet for this reference. Pay first, then tap refresh.", show_alert=True)
    finally:
        session.close()


def build_payment_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(upgrade_start, pattern=r"^sub:upgrade_start$")],
        states={
            ASK_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_email)],
        },
        fallbacks=[],
        name="payment_upgrade",
        persistent=False,
    )
