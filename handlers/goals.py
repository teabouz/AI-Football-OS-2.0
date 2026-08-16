"""
Goal Tracking + Weekly/Monthly/Season Objectives — Phase 2.

/addgoal <title> starts a short flow to pick a timeframe, then saves it.
The goals list shows active goals with a "Mark Done" button per goal.
"""
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler
)

from database import SessionLocal
from models import User, Goal, GoalStatus, GoalTimeframe
from handlers.subscription import require_premium
from handlers.safe_text import md
import keyboards

ASK_TIMEFRAME = range(1)[0]


async def list_goals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_user = update.effective_user

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=tg_user.id).first()
        if not user or not await require_premium(update, user):
            return

        active = (
            session.query(Goal)
            .filter_by(user_id=user.id, status=GoalStatus.ACTIVE)
            .order_by(Goal.created_at.desc())
            .all()
        )

        if not active:
            text = (
                "🎯 *My Goals*\n\nNo active goals yet.\n\n"
                "Add one with:\n`/addgoal Improve first touch under pressure`"
            )
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=_back_keyboard())
            return

        text = "🎯 *My Goals*\n\n" + "\n".join(
            f"• [{g.timeframe.value}] {g.title}" for g in active
        )
        text += "\n\nAdd another with `/addgoal <title>`. Tap a button below to mark one done."

        rows = [
            [InlineKeyboardButton(f"✅ Done: {g.title[:30]}", callback_data=f"goal:done:{g.id}")]
            for g in active[:10]  # keep the keyboard manageable
        ]
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="menu:premium_hub")])

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))
    finally:
        session.close()


async def addgoal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /addgoal <your goal>\ne.g. /addgoal Improve weak-foot passing accuracy")
        return ConversationHandler.END

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user or not await require_premium(update, user):
            return ConversationHandler.END
    finally:
        session.close()

    context.user_data["pending_goal_title"] = " ".join(context.args).strip()
    await update.message.reply_text(
        "What timeframe is this goal for?", reply_markup=keyboards.goal_timeframe_keyboard()
    )
    return ASK_TIMEFRAME


async def timeframe_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    timeframe = query.data.split(":")[1]  # weekly | monthly | season
    title = context.user_data.pop("pending_goal_title", None)

    if not title:
        await query.edit_message_text("Something went wrong — please try /addgoal again.")
        return ConversationHandler.END

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        goal = Goal(user_id=user.id, title=title, timeframe=GoalTimeframe(timeframe))
        session.add(goal)
        session.commit()
        await query.edit_message_text(
            f"✅ Goal added: *{md(title)}* ({md(timeframe)})\n\nView all goals from 🏆 Premium Coaching → 🎯 My Goals.",
            parse_mode="Markdown",
        )
    finally:
        session.close()
    return ConversationHandler.END


async def mark_goal_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    goal_id = int(query.data.split(":")[2])

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user:
            await query.answer()
            return

        # Never trust an ID from callback_data alone -- a user can forge a
        # callback payload. Scope the goal to the caller's own account.
        goal = session.query(Goal).filter_by(id=goal_id, user_id=user.id).first()
        if not goal:
            await query.answer("Couldn't find that goal.", show_alert=True)
            return

        await query.answer("Marked as done! 🎉")
        goal.status = GoalStatus.COMPLETED
        goal.completed_at = datetime.utcnow()
        session.commit()
        # Re-render the list
        await list_goals(update, context)
    finally:
        session.close()


def _back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="menu:premium_hub")]])


def build_addgoal_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("addgoal", addgoal_command)],
        states={
            ASK_TIMEFRAME: [CallbackQueryHandler(timeframe_chosen, pattern=r"^goaltf:")],
        },
        fallbacks=[],
        name="add_goal",
        persistent=False,
    )
