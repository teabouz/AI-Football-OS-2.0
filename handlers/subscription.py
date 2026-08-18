"""
Subscription module. Tiers, quota enforcement, and status display live here.
The actual payment flow (collecting email, creating a Paystack transaction,
the "I've Paid" refresh button) lives in handlers/payments.py — this file
just exposes mark_user_premium(), the one function that flow calls once a
payment is confirmed (also reusable by the webhook in payment_server.py).
"""
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import ContextTypes

from database import SessionLocal
from models import User, SubscriptionTier
import config
import keyboards


async def show_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    tg_user = update.effective_user

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=tg_user.id).first()
        if not user:
            text = "Send /start first to create your profile."
        elif user.is_premium():
            expiry = user.subscription_expires_at.strftime("%d %b %Y") if user.subscription_expires_at else "—"
            text = (
                "⭐ *You're on Premium!*\n\n"
                f"Renews/expires: {expiry}\n\n"
                "Unlimited AI Coach questions, plus your Development Plan, Goals, "
                "Daily Check-in, Coaching Modes, and Performance Reports — open "
                "them from /menu → 🏆 Premium Coaching."
            )
        else:
            remaining = max(0, config.FREE_TIER_DAILY_QUESTIONS - user.daily_question_count)
            text = (
                "🆓 *You're on the Free plan*\n\n"
                f"AI Coach questions today: {remaining}/{config.FREE_TIER_DAILY_QUESTIONS} remaining\n\n"
                "*⭐ Premium unlocks:*\n"
                "• Unlimited AI Coach conversations\n"
                "• Personalized training & development plans\n"
                "• Weekly/monthly/season planning\n"
                "• Mindset, recovery & sleep coaching\n"
                "• Priority access to new features\n\n"
                f"Price: ₦{config.PREMIUM_MONTHLY_PRICE_NGN}/month"
            )

        if user and user.is_premium():
            markup = keyboards.back_to_menu_keyboard()
        else:
            markup = keyboards.subscription_keyboard()

        if query:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)
    finally:
        session.close()


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/status — quick text-only version of show_subscription for command users."""
    await show_subscription(update, context)


async def require_premium(update: Update, user: User) -> bool:
    """Shared gate for every Phase 2 feature. Returns True if the user may
    proceed; otherwise sends an upsell message and returns False."""
    if user.is_premium():
        return True
    query = update.callback_query
    text = (
        "🏆 This is a Premium feature.\n\n"
        "Development Plans, Goal Tracking, Daily Check-ins, Coaching Modes, "
        "and Performance Reports are all part of Premium AI Coach."
    )
    if query:
        await query.answer()
        await query.edit_message_text(text, reply_markup=subscription_upsell_keyboard())
    else:
        await update.message.reply_text(text, reply_markup=subscription_upsell_keyboard())
    return False


def subscription_upsell_keyboard():
    return keyboards.subscription_keyboard()


def mark_user_premium(session, user: User, days: int = 30) -> None:
    """Call this from the Phase 2 payment webhook once a payment is confirmed."""
    # Must check is_premium() BEFORE flipping the tier below — otherwise every
    # first-time upgrade sees itself as "already premium" with a None expiry
    # and crashes on `None + timedelta(...)`.
    was_already_premium = user.is_premium()
    base = user.subscription_expires_at if was_already_premium else datetime.now(timezone.utc).replace(tzinfo=None)
    user.subscription_tier = SubscriptionTier.PREMIUM
    user.subscription_expires_at = base + timedelta(days=days)
    session.commit()
