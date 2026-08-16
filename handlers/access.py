"""Shared access-control helper for Coach Dashboard features (Phase 3),
mirroring the pattern used by subscription.require_premium()."""
from telegram import Update

from models import User, UserRole


async def require_coach_or_academy(update: Update, user: User) -> bool:
    if user and user.role in (UserRole.COACH, UserRole.ACADEMY):
        return True
    text = "🏫 This is for Coach and Academy accounts. Player accounts don't need a roster to manage!"
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(text)
    else:
        await update.message.reply_text(text)
    return False
