"""
Coaching Modes — Phase 2.

Lets a premium user switch the AI Coach's persona. The active mode is
persisted on User.active_coach_mode and read by handlers/ai_chat.py to pick
the right system prompt from config.COACH_MODE_PROMPTS.
"""
from telegram import Update
from telegram.ext import ContextTypes

from database import SessionLocal
from models import User, CoachMode
from handlers.subscription import require_premium
from handlers.safe_text import md
import keyboards


async def show_modes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user or not await require_premium(update, user):
            return

        await query.edit_message_text(
            "🧠 *Coaching Modes*\n\n"
            "Choose the lens the AI Coach uses for your conversations. It stays "
            "active until you switch it again.",
            parse_mode="Markdown",
            reply_markup=keyboards.coaching_mode_keyboard(active=user.active_coach_mode.value),
        )
    finally:
        session.close()


async def set_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    mode_value = query.data.split(":")[1]

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user or not await require_premium(update, user):
            return

        user.active_coach_mode = CoachMode(mode_value)
        session.commit()
        await query.answer(f"Switched to {mode_value.title()} Coach")
        await query.edit_message_text(
            f"✅ Coaching mode set to *{md(mode_value.title())} Coach*.\n\n"
            "Just send a message any time to chat — the AI will respond from this angle.",
            parse_mode="Markdown",
            reply_markup=keyboards.coaching_mode_keyboard(active=mode_value),
        )
    finally:
        session.close()
