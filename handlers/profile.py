"""View-your-profile handler. Editing individual fields is a good Phase-2
add-on; Phase 1 covers create + view."""
from telegram import Update
from telegram.ext import ContextTypes

from database import SessionLocal
from models import User, UserRole
import keyboards


def _format_profile(user: User) -> str:
    lines = [f"👤 *{user.display_name()}*", f"Role: {user.role.value.title()}"]
    tier = "⭐ Premium" if user.is_premium() else "Free"
    lines.append(f"Plan: {tier}")

    if user.role == UserRole.PLAYER and user.player_profile:
        p = user.player_profile
        lines += [
            "",
            f"Position: {p.position or '—'}",
            f"Age: {p.age or '—'}",
            f"Dominant foot: {p.dominant_foot.value.title() if p.dominant_foot else '—'}",
            f"Club: {p.current_club or '—'}",
        ]
    elif user.role == UserRole.COACH and user.coach_profile:
        c = user.coach_profile
        lines += [
            "",
            f"License: {c.license_level or '—'}",
            f"Experience: {c.years_experience if c.years_experience is not None else '—'} years",
            f"Club: {c.current_club or '—'}",
        ]
    elif user.role == UserRole.ACADEMY and user.academy_profile:
        a = user.academy_profile
        lines += [
            "",
            f"Location: {a.location or '—'}",
            f"Founded: {a.founded_year or '—'}",
            f"Contact: {a.contact_email or '—'}",
        ]

    return "\n".join(lines)


async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    tg_user = update.effective_user

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=tg_user.id).first()
        if not user or not user.registration_complete:
            text = "You haven't registered yet. Send /start to set up your profile."
            if query:
                await query.edit_message_text(text)
            else:
                await update.message.reply_text(text)
            return

        text = _format_profile(user)
        markup = keyboards.back_to_menu_keyboard()
        if query:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)
    finally:
        session.close()
