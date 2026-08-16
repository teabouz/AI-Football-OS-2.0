"""Routes the persistent main-menu inline keyboard to the right handler."""
from telegram import Update
from telegram.ext import ContextTypes

from database import SessionLocal
from models import User, UserRole
import keyboards
from handlers import profile, subscription, ai_chat, plan, goals, coaching_modes, reports, team, attendance, video, academy, marketplace
from handlers.access import require_coach_or_academy

HELP_TEXT = (
    "🏆 *AI Football OS — Help*\n\n"
    "/start — create or view your profile\n"
    "/menu — open the main menu\n"
    "/ask <question> — ask the AI Coach directly\n"
    "/status — check your subscription & quota\n"
    "/addgoal <goal> — add a goal (Premium)\n"
    "/checkin — log today's sleep, hydration, training & mood (Premium)\n"
    "/analyzevideo — get AI feedback on a training/match clip (Premium)\n"
    "/videos — view your past video analyses (Premium)\n"
    "/academy — browse Learning Academy courses (free lessons & quizzes)\n"
    "/marketplace — browse trials, jobs, scholarships & internships\n"
    "/cancel — cancel a form you're in the middle of\n\n"
    "*Coach / Academy accounts:*\n"
    "/createteam <name> — set up your team\n"
    "/addplayer @username or Name — add to your roster\n"
    "/roster — view your roster\n"
    "/attendance — quick attendance for today's session\n"
    "/broadcast <message> — message your whole roster\n"
    "/dashboard — open the full web Coach Dashboard\n\n"
    "You can also just type a football question any time — no command needed.\n\n"
    "🏆 Premium Coaching (from /menu) unlocks a personalized Development Plan, "
    "Goal Tracking, Daily Check-ins, Coaching Modes, Performance Reports, and AI Video Analysis."
)


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Main menu:", reply_markup=keyboards.main_menu_keyboard())


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(HELP_TEXT, parse_mode="Markdown", reply_markup=keyboards.back_to_menu_keyboard())
    else:
        await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action = query.data.split(":")[1]  # main | ai_chat | profile | subscription | help | premium_hub | coach_hub

    if action == "main":
        await query.answer()
        await query.edit_message_text("Main menu:", reply_markup=keyboards.main_menu_keyboard())
    elif action == "ai_chat":
        await ai_chat.prompt_for_question(update, context)
    elif action == "profile":
        await profile.show_profile(update, context)
    elif action == "subscription":
        await subscription.show_subscription(update, context)
    elif action == "help":
        await show_help(update, context)
    elif action == "premium_hub":
        await show_premium_hub(update, context)
    elif action == "coach_hub":
        await show_coach_hub(update, context)
    elif action == "academy":
        await academy.show_academy_home(update, context)
    elif action == "marketplace":
        await marketplace.show_marketplace_home(update, context)


async def show_premium_hub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user or not user.registration_complete:
            await query.edit_message_text("Send /start first to set up your profile.")
            return
        if not user.is_premium():
            await query.edit_message_text(
                "🏆 *Premium Coaching*\n\n"
                "Unlock your personalized Development Plan, Goal Tracking, Daily "
                "Check-ins with streaks, switchable Coaching Modes (Mindset, "
                "Leadership, Confidence, Recovery), and weekly Performance Reports.",
                parse_mode="Markdown",
                reply_markup=keyboards.subscription_keyboard(),
            )
            return
        await query.edit_message_text(
            "🏆 *Premium Coaching*\n\nWhat would you like to open?",
            parse_mode="Markdown",
            reply_markup=keyboards.premium_hub_keyboard(),
        )
    finally:
        session.close()


async def premium_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Routes the 🏆 Premium Coaching submenu buttons. 'premium:checkin' and
    'premium:video' are intentionally NOT handled here — they're
    ConversationHandler entry points registered separately (and earlier) in
    main.py."""
    query = update.callback_query
    action = query.data.split(":")[1]  # plan | plan_regen | goals | modes | report | videos

    if action == "plan":
        await plan.show_plan(update, context)
    elif action == "plan_regen":
        await plan.regenerate_plan(update, context)
    elif action == "goals":
        await goals.list_goals(update, context)
    elif action == "modes":
        await coaching_modes.show_modes(update, context)
    elif action == "report":
        await reports.generate_report(update, context)
    elif action == "videos":
        await video.list_analyses(update, context)
    else:
        await query.answer()


async def show_coach_hub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user or not user.registration_complete:
            await query.edit_message_text("Send /start first to set up your profile.")
            return
        if not await require_coach_or_academy(update, user):
            return

        team_obj = await team.get_or_none_team(session, user)
        if not team_obj:
            await query.edit_message_text(
                "🏫 *Coach Dashboard*\n\n"
                "You don't have a team yet. Create one with:\n"
                "`/createteam <name>`\n\n"
                "Then come back here for roster, attendance, and your full web dashboard.",
                parse_mode="Markdown",
                reply_markup=keyboards.back_to_menu_keyboard(),
            )
            return

        active_count = sum(1 for m in team_obj.members if m.active)
        await query.edit_message_text(
            f"🏫 *{team_obj.name}*\n{active_count} player(s) on roster.\n\nWhat would you like to do?",
            parse_mode="Markdown",
            reply_markup=keyboards.coach_hub_keyboard(),
        )
    finally:
        session.close()


async def coach_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Routes the 🏫 Coach Dashboard submenu buttons."""
    query = update.callback_query
    action = query.data.split(":")[1]  # roster | attendance | dashboard | scouting | broadcast_info

    if action == "roster":
        await team.roster_command(update, context)
    elif action == "attendance":
        await attendance.attendance_command(update, context)
    elif action == "dashboard":
        await team.dashboard_command(update, context)
    elif action == "scouting":
        await team.dashboard_command(update, context, next_path="/coach/scouting")
    elif action == "broadcast_info":
        await query.answer()
        await query.edit_message_text(
            "📣 To message your whole roster, send:\n\n`/broadcast Your message here`\n\n"
            "e.g. `/broadcast Training moved to 5pm today`\n\n"
            "Only players registered on the bot receive it — guest roster entries don't have a Telegram account to message.",
            parse_mode="Markdown",
            reply_markup=keyboards.back_to_menu_keyboard(),
        )
    else:
        await query.answer()
