"""
Minimal /admin command for the bot itself (quick stats from inside Telegram).
The fuller Admin Dashboard is the separate Flask app: admin_dashboard.py
"""
from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import func

from database import SessionLocal
from models import User, UserRole, SubscriptionTier
import config


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    if tg_user.id not in config.ADMIN_TELEGRAM_IDS:
        await update.message.reply_text("This command is restricted to admins.")
        return

    session = SessionLocal()
    try:
        total = session.query(func.count(User.id)).scalar()
        registered = session.query(func.count(User.id)).filter_by(registration_complete=True).scalar()
        premium = session.query(func.count(User.id)).filter_by(subscription_tier=SubscriptionTier.PREMIUM).scalar()

        by_role = dict(
            session.query(User.role, func.count(User.id))
            .filter(User.role.isnot(None))
            .group_by(User.role)
            .all()
        )

        lines = [
            "📊 *AI Football OS — Stats*",
            "",
            f"Total users: {total}",
            f"Completed registration: {registered}",
            f"Premium: {premium}",
            "",
            "*By role:*",
        ]
        for role in UserRole:
            count = by_role.get(role, 0)
            lines.append(f"  {role.value.title()}: {count}")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    finally:
        session.close()
