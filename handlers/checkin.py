"""
AI Habit Coach — Phase 2.

A short daily check-in (sleep, hydration, training completed, mood) feeds a
streak counter and a brief AI-generated nudge. Deliberately quick to fill in
— habit tools die the moment they become a chore.
"""
from datetime import date, timedelta

from anthropic import Anthropic, APIError

from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters
)

from database import SessionLocal
from models import User, DailyCheckin
from handlers.subscription import require_premium
import config
import keyboards

_client = Anthropic(api_key=config.ANTHROPIC_API_KEY) if config.ANTHROPIC_API_KEY else None

SLEEP, HYDRATION, TRAINING, MOOD = range(4)


async def checkin_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point from both /checkin and the 'Daily Check-in' menu button."""
    query = update.callback_query
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user or not await require_premium(update, user):
            return ConversationHandler.END
    finally:
        session.close()

    context.user_data["checkin"] = {}
    text = "🌙 How many hours did you sleep last night? (just the number)"
    if query:
        await query.answer()
        await query.edit_message_text(text)
    else:
        await update.message.reply_text(text)
    return SLEEP


async def sleep_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        hours = float(text)
        assert 0 <= hours <= 16
    except (ValueError, AssertionError):
        await update.message.reply_text("Please send a number between 0 and 16, e.g. 7.5")
        return SLEEP
    context.user_data["checkin"]["sleep_hours"] = round(hours)
    await update.message.reply_text("💧 How many liters of water did you drink? (e.g. 2)")
    return HYDRATION


async def hydration_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        liters = float(text)
        assert 0 <= liters <= 15
    except (ValueError, AssertionError):
        await update.message.reply_text("Please send a number between 0 and 15, e.g. 2.5")
        return HYDRATION
    context.user_data["checkin"]["hydration_deciliters"] = round(liters * 10)
    await update.message.reply_text(
        "⚽ Did you complete a training session today?", reply_markup=keyboards.yes_no_keyboard("train")
    )
    return TRAINING


async def training_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["checkin"]["training_completed"] = query.data.endswith("yes")
    await query.edit_message_text("🙂 How was your mood today overall?", reply_markup=keyboards.mood_keyboard())
    return MOOD


async def mood_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mood = int(query.data.split(":")[1])
    data = context.user_data.pop("checkin", {})
    data["mood"] = mood

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        existing = session.query(DailyCheckin).filter_by(user_id=user.id, checkin_date=date.today()).first()
        if existing:
            existing.sleep_hours = data.get("sleep_hours")
            existing.hydration_liters = data.get("hydration_deciliters")
            existing.training_completed = data.get("training_completed", False)
            existing.mood = mood
        else:
            session.add(DailyCheckin(
                user_id=user.id,
                checkin_date=date.today(),
                sleep_hours=data.get("sleep_hours"),
                hydration_liters=data.get("hydration_deciliters"),
                training_completed=data.get("training_completed", False),
                mood=mood,
            ))
        session.commit()

        streak = _current_streak(session, user.id)
        nudge = await _generate_nudge(data, streak)

        await query.edit_message_text(
            f"✅ Check-in saved! Current streak: {streak} day{'s' if streak != 1 else ''} 🔥\n\n{nudge}",
            reply_markup=keyboards.premium_hub_keyboard(),
        )
    finally:
        session.close()
    return ConversationHandler.END


def _current_streak(session, user_id: int) -> int:
    checkins = (
        session.query(DailyCheckin)
        .filter_by(user_id=user_id)
        .order_by(DailyCheckin.checkin_date.desc())
        .all()
    )
    dates = {c.checkin_date for c in checkins}
    streak = 0
    cursor = date.today()
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


async def _generate_nudge(data: dict, streak: int) -> str:
    if _client is None:
        return "Keep it up!"
    summary = (
        f"Sleep: {data.get('sleep_hours')}h, Hydration: {data.get('hydration_deciliters', 0) / 10}L, "
        f"Training done: {data.get('training_completed')}, Mood: {data.get('mood')}/5, Streak: {streak} days."
    )
    try:
        response = _client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=100,
            system="You are a brief, warm habit coach for footballers. Respond in 1-2 short "
                   "sentences only — a specific observation plus one small encouragement or tip. "
                   "No greetings, no sign-off.",
            messages=[{"role": "user", "content": summary}],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()
    except APIError:
        return "Keep it up!"


def build_checkin_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("checkin", checkin_entry),
            CallbackQueryHandler(checkin_entry, pattern=r"^premium:checkin$"),
        ],
        states={
            SLEEP: [MessageHandler(filters.TEXT & ~filters.COMMAND, sleep_received)],
            HYDRATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, hydration_received)],
            TRAINING: [CallbackQueryHandler(training_received, pattern=r"^train:")],
            MOOD: [CallbackQueryHandler(mood_received, pattern=r"^mood:")],
        },
        fallbacks=[],
        name="daily_checkin",
        persistent=False,
    )
