"""
Communication — Phase 3.

/broadcast <message> sends a message from the coach/academy to every roster
player who is also a registered bot user (guest entries have no Telegram
account to message, obviously). Simple and direct — no read receipts or
threading, just "get the word out."
"""
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError

from database import SessionLocal
from models import User, TeamMembership
from handlers.access import require_coach_or_academy
from handlers.team import get_or_none_team


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user or not await require_coach_or_academy(update, user):
            return

        if not context.args:
            await update.message.reply_text("Usage: /broadcast <message>\ne.g. /broadcast Training moved to 5pm today")
            return

        team = await get_or_none_team(session, user)
        if not team:
            await update.message.reply_text("Create a team first: /createteam <name>")
            return

        message_text = " ".join(context.args).strip()
        recipients = [
            m.player_user for m in team.members
            if m.active and m.player_user_id and m.player_user
        ]

        if not recipients:
            await update.message.reply_text(
                "No roster players are registered on the bot yet — guest entries can't receive Telegram messages."
            )
            return

        sent, failed = 0, 0
        for player in recipients:
            try:
                await context.bot.send_message(
                    chat_id=player.telegram_id,
                    text=f"📣 Message from {team.name} ({user.display_name()}):\n\n{message_text}",
                )
                sent += 1
            except TelegramError:
                # Covers blocked bot (Forbidden), bad chat (BadRequest), and
                # transient delivery failures (TimedOut, NetworkError, ...).
                # Bug found in audit: this previously only caught Forbidden/
                # BadRequest, so a single transient network error partway
                # through the roster would abort the whole broadcast and
                # silently skip every remaining player.
                failed += 1

        summary = f"📣 Sent to {sent}/{len(recipients)} player(s)."
        if failed:
            summary += f" {failed} couldn't be reached (they may have blocked the bot)."
        await update.message.reply_text(summary)
    finally:
        session.close()
