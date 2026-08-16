"""
Marketplace — Phase 7 (bot side: browsing + applying).

Posting opportunities is Coach/Academy-only and lives in the Coach
Dashboard (richer form, applicant management) — consistent with the
pattern used for match reports, notes, and finance. This module is the
player/coach-facing browse-and-apply side, which fits Telegram well (quick,
on the go).

No opportunity is visible here unless its poster explicitly opened it, and
no applicant is ever visible to a poster unless they explicitly applied —
there's no passive "browse people" surface anywhere in this feature.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
)
import logging

from database import SessionLocal
from models import User, Opportunity, OpportunityApplication, ListingType, ListingStatus, ApplicationStatus
from handlers.safe_text import md

logger = logging.getLogger(__name__)

ASK_NOTE = range(1)[0]

TYPE_LABELS = {
    "trial": "⚽ Trial",
    "job": "💼 Job",
    "scholarship": "🎓 Scholarship",
    "internship": "📋 Internship",
    "sponsorship": "🤝 Sponsorship",
}


def _filter_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(label, callback_data=f"mkt:filter:{value}")] for value, label in TYPE_LABELS.items()]
    rows.append([InlineKeyboardButton("📋 All Opportunities", callback_data="mkt:filter:all")])
    rows.append([InlineKeyboardButton("📥 My Applications", callback_data="mkt:myapps")])
    rows.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


async def show_marketplace_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    text = (
        "🧩 *Marketplace*\n\n"
        "Trials, coaching jobs, scholarships, internships, and teams looking for sponsors — "
        "posted by coaches and academies on the platform. Pick a category to browse."
    )
    if query:
        await query.answer()
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=_filter_keyboard())
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=_filter_keyboard())


async def show_opportunities(update: Update, context: ContextTypes.DEFAULT_TYPE, listing_type: str):
    query = update.callback_query
    await query.answer()

    session = SessionLocal()
    try:
        q = session.query(Opportunity).filter_by(status=ListingStatus.OPEN)
        if listing_type != "all":
            q = q.filter_by(listing_type=ListingType(listing_type))
        opportunities = q.order_by(Opportunity.created_at.desc()).limit(15).all()

        if not opportunities:
            await query.edit_message_text(
                "No open opportunities in this category right now — check back soon.",
                reply_markup=_filter_keyboard(),
            )
            return

        rows = [
            [InlineKeyboardButton(f"{TYPE_LABELS.get(o.listing_type.value, '')} {md(o.title)} — {md(o.team.name)}",
                                   callback_data=f"mkt:view:{o.id}")]
            for o in opportunities
        ]
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="mkt:home")])
        label = TYPE_LABELS.get(listing_type, "All Opportunities")
        await query.edit_message_text(f"🧩 {label} — open listings:", reply_markup=InlineKeyboardMarkup(rows))
    finally:
        session.close()


async def show_opportunity_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, opportunity_id: int):
    query = update.callback_query
    await query.answer()
    tg_user = update.effective_user

    session = SessionLocal()
    try:
        opp = session.query(Opportunity).filter_by(id=opportunity_id).first()
        if not opp:
            await query.edit_message_text("Couldn't find that listing.")
            return

        user = session.query(User).filter_by(telegram_id=tg_user.id).first()
        already_applied = (
            session.query(OpportunityApplication)
            .filter_by(opportunity_id=opportunity_id, applicant_user_id=user.id).first()
            if user else None
        )

        lines = [
            f"{TYPE_LABELS.get(opp.listing_type.value, '')} *{md(opp.title)}*",
            f"Posted by: {md(opp.team.name)}",
        ]
        if opp.location:
            lines.append(f"Location: {md(opp.location)}")
        if opp.age_min or opp.age_max:
            lines.append(f"Age range: {opp.age_min or '?'}–{opp.age_max or '?'}")
        if opp.deadline:
            lines.append(f"Deadline: {opp.deadline.strftime('%d %b %Y')}")
        lines.append(f"\n{md(opp.description)}")

        rows = []
        if opp.status != ListingStatus.OPEN:
            lines.append("\n_This listing is now closed._")
        elif already_applied:
            lines.append(f"\n_You've already applied — status: {already_applied.status.value}._")
        else:
            rows.append([InlineKeyboardButton("✋ Apply", callback_data=f"mkt:apply:{opportunity_id}")])
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data=f"mkt:filter:{opp.listing_type.value}")])

        await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
    finally:
        session.close()


async def apply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    opportunity_id = int(query.data.split(":")[2])

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user or not user.registration_complete:
            await query.edit_message_text("Send /start first to set up your profile.")
            return ConversationHandler.END

        opp = session.query(Opportunity).filter_by(id=opportunity_id).first()
        if not opp or opp.status != ListingStatus.OPEN:
            await query.edit_message_text("This listing isn't open anymore.")
            return ConversationHandler.END

        dupe = session.query(OpportunityApplication).filter_by(
            opportunity_id=opportunity_id, applicant_user_id=user.id
        ).first()
        if dupe:
            await query.edit_message_text("You've already applied to this one.")
            return ConversationHandler.END

        context.user_data["applying_to"] = opportunity_id
        await query.edit_message_text(
            f"Applying to *{md(opp.title)}* ({md(opp.team.name)}).\n\n"
            "Add a short note for them (why you're a fit, availability, etc.) — or send \"-\" to skip.",
            parse_mode="Markdown",
        )
        return ASK_NOTE
    finally:
        session.close()


async def apply_note_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    opportunity_id = context.user_data.pop("applying_to", None)
    if not opportunity_id:
        await update.message.reply_text("Something went wrong — please try applying again from the listing.")
        return ConversationHandler.END

    note = update.message.text.strip()
    note = None if note == "-" else note

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        opp = session.query(Opportunity).filter_by(id=opportunity_id).first()
        if not opp:
            await update.message.reply_text("That listing no longer exists.")
            return ConversationHandler.END

        session.add(OpportunityApplication(opportunity_id=opportunity_id, applicant_user_id=user.id, note=note))
        session.commit()

        await update.message.reply_text(f"✅ Application sent for *{md(opp.title)}*!", parse_mode="Markdown")

        # Notify the poster directly -- this happens inside the bot process,
        # so a normal context.bot call works (no cross-process notification needed here).
        poster = opp.team.owner
        try:
            await context.bot.send_message(
                chat_id=poster.telegram_id,
                text=f"📥 New application for *{md(opp.title)}* from {md(user.display_name())}"
                     + (f"\n\nNote: {md(note)}" if note else "") + "\n\nReview it in your Coach Dashboard.",
                parse_mode="Markdown",
            )
        except Exception:
            logger.warning("Failed to notify poster (telegram_id=%s) of new application to opportunity %s",
                            poster.telegram_id, opp.id, exc_info=True)
            # best-effort; the application itself is already saved
    finally:
        session.close()
    return ConversationHandler.END


async def show_my_applications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user:
            await query.edit_message_text("Send /start first.")
            return

        apps = (
            session.query(OpportunityApplication).filter_by(applicant_user_id=user.id)
            .order_by(OpportunityApplication.applied_at.desc()).limit(15).all()
        )
        if not apps:
            await query.edit_message_text("You haven't applied to anything yet.", reply_markup=_filter_keyboard())
            return

        status_emoji = {"pending": "⏳", "reviewed": "👀", "accepted": "✅", "rejected": "❌"}
        lines = ["📥 *Your applications:*\n"]
        for a in apps:
            lines.append(f"{status_emoji.get(a.status.value, '')} {md(a.opportunity.title)} — {md(a.opportunity.team.name)} ({md(a.status.value)})")

        rows = [[InlineKeyboardButton("⬅️ Back", callback_data="mkt:home")]]
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
    finally:
        session.close()


def build_apply_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(apply_start, pattern=r"^mkt:apply:")],
        states={ASK_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, apply_note_received)]},
        fallbacks=[],
        name="marketplace_apply",
        persistent=False,
    )


async def marketplace_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Routes non-conversation marketplace callbacks. 'mkt:apply:' is
    handled separately by its own ConversationHandler, registered earlier."""
    query = update.callback_query
    parts = query.data.split(":")
    action = parts[1]

    if action == "home":
        await show_marketplace_home(update, context)
    elif action == "filter":
        await show_opportunities(update, context, parts[2])
    elif action == "view":
        await show_opportunity_detail(update, context, int(parts[2]))
    elif action == "myapps":
        await show_my_applications(update, context)
    else:
        await query.answer()
