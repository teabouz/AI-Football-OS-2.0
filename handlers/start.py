"""
/start and the registration conversation.

Flow:
  /start -> if unknown user: welcome + role picker (Player/Coach/Academy)
         -> role picker sets up a short, role-specific Q&A
         -> on completion: profile is saved and the main menu is shown
         -> if already registered: /start just shows the main menu
"""
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters
)

from database import SessionLocal
from models import User, UserRole, PlayerProfile, CoachProfile, AcademyProfile, DominantFoot
import keyboards

logger = logging.getLogger(__name__)

# Conversation states
(
    CHOOSING_ROLE,
    PLAYER_NAME, PLAYER_AGE, PLAYER_POSITION, PLAYER_FOOT, PLAYER_CLUB,
    COACH_NAME, COACH_LICENSE, COACH_EXPERIENCE, COACH_CLUB,
    ACADEMY_NAME, ACADEMY_LOCATION, ACADEMY_YEAR, ACADEMY_EMAIL,
) = range(14)


def get_or_create_user(session, tg_user) -> User:
    user = session.query(User).filter_by(telegram_id=tg_user.id).first()
    if user is None:
        user = User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            language_code=tg_user.language_code,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    try:
        user = get_or_create_user(session, update.effective_user)
        user.last_active_at = datetime.utcnow()
        session.commit()

        if user.registration_complete:
            await update.message.reply_text(
                f"Welcome back, {user.display_name()}! ⚽\n\nWhat would you like to do?",
                reply_markup=keyboards.main_menu_keyboard(),
            )
            return ConversationHandler.END

        await update.message.reply_text(
            "🏆 *Welcome to AI Football OS!*\n\n"
            "I'm your AI-powered football companion — part coach, part academy, "
            "part career guide. Let's set up your profile first.\n\n"
            "Who are you?",
            parse_mode="Markdown",
            reply_markup=keyboards.role_selection_keyboard(),
        )
        return CHOOSING_ROLE
    finally:
        session.close()


async def role_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    role = query.data.split(":")[1]  # "player" | "coach" | "academy"
    context.user_data["role"] = role
    context.user_data["profile"] = {}

    if role == "player":
        await query.edit_message_text("Great! ⚽ What's your full name?")
        return PLAYER_NAME
    elif role == "coach":
        await query.edit_message_text("Great! 📋 What's your full name?")
        return COACH_NAME
    else:
        await query.edit_message_text("Great! 🏫 What's your academy's name?")
        return ACADEMY_NAME


# ---------- Player onboarding ----------

async def player_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["profile"]["full_name"] = update.message.text.strip()
    await update.message.reply_text("How old are you? (just the number)")
    return PLAYER_AGE


async def player_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit() or not (5 <= int(text) <= 60):
        await update.message.reply_text("Please send a valid age as a number, e.g. 17")
        return PLAYER_AGE
    context.user_data["profile"]["age"] = int(text)
    await update.message.reply_text(
        "What's your position? (e.g. Right Winger, Central Midfielder, Goalkeeper)"
    )
    return PLAYER_POSITION


async def player_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["profile"]["position"] = update.message.text.strip()
    await update.message.reply_text(
        "What's your dominant foot?", reply_markup=keyboards.dominant_foot_keyboard()
    )
    return PLAYER_FOOT


async def player_foot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    foot = query.data.split(":")[1]  # left | right | both
    context.user_data["profile"]["dominant_foot"] = foot
    await query.edit_message_text("What club or team do you currently play for? (or send \"-\" if none)")
    return PLAYER_CLUB


async def player_club(update: Update, context: ContextTypes.DEFAULT_TYPE):
    club = update.message.text.strip()
    context.user_data["profile"]["current_club"] = None if club == "-" else club
    return await finish_registration(update, context, UserRole.PLAYER)


# ---------- Coach onboarding ----------

async def coach_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["profile"]["full_name"] = update.message.text.strip()
    await update.message.reply_text(
        "What's your coaching license level? (e.g. UEFA B, CAF C, None yet)"
    )
    return COACH_LICENSE


async def coach_license(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["profile"]["license_level"] = update.message.text.strip()
    await update.message.reply_text("How many years of coaching experience do you have?")
    return COACH_EXPERIENCE


async def coach_experience(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("Please send a number, e.g. 3")
        return COACH_EXPERIENCE
    context.user_data["profile"]["years_experience"] = int(text)
    await update.message.reply_text("What club or academy are you currently with? (or \"-\" if none)")
    return COACH_CLUB


async def coach_club(update: Update, context: ContextTypes.DEFAULT_TYPE):
    club = update.message.text.strip()
    context.user_data["profile"]["current_club"] = None if club == "-" else club
    return await finish_registration(update, context, UserRole.COACH)


# ---------- Academy onboarding ----------

async def academy_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["profile"]["academy_name"] = update.message.text.strip()
    await update.message.reply_text("Where is the academy located? (city, country)")
    return ACADEMY_LOCATION


async def academy_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["profile"]["location"] = update.message.text.strip()
    await update.message.reply_text("What year was it founded? (or \"-\" if unsure)")
    return ACADEMY_YEAR


async def academy_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text != "-" and not text.isdigit():
        await update.message.reply_text("Please send a year (e.g. 2019) or \"-\"")
        return ACADEMY_YEAR
    context.user_data["profile"]["founded_year"] = None if text == "-" else int(text)
    await update.message.reply_text("Best contact email for the academy?")
    return ACADEMY_EMAIL


async def academy_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["profile"]["contact_email"] = update.message.text.strip()
    return await finish_registration(update, context, UserRole.ACADEMY)


# ---------- Shared finish step ----------

async def finish_registration(update: Update, context: ContextTypes.DEFAULT_TYPE, role: UserRole):
    session = SessionLocal()
    try:
        user = get_or_create_user(session, update.effective_user)
        user.role = role
        user.registration_complete = True
        profile_data = context.user_data.get("profile", {})

        if role == UserRole.PLAYER:
            foot_value = profile_data.get("dominant_foot")
            profile = PlayerProfile(
                user_id=user.id,
                full_name=profile_data.get("full_name"),
                age=profile_data.get("age"),
                position=profile_data.get("position"),
                dominant_foot=DominantFoot(foot_value) if foot_value else None,
                current_club=profile_data.get("current_club"),
            )
        elif role == UserRole.COACH:
            profile = CoachProfile(
                user_id=user.id,
                full_name=profile_data.get("full_name"),
                license_level=profile_data.get("license_level"),
                years_experience=profile_data.get("years_experience"),
                current_club=profile_data.get("current_club"),
            )
        else:
            profile = AcademyProfile(
                user_id=user.id,
                academy_name=profile_data.get("academy_name"),
                location=profile_data.get("location"),
                founded_year=profile_data.get("founded_year"),
                contact_email=profile_data.get("contact_email"),
            )

        session.add(profile)
        session.commit()

        target = update.message or update.callback_query.message
        await target.reply_text(
            "✅ *Profile created!* Welcome to the team.\n\n"
            "Here's what I can do for you:",
            parse_mode="Markdown",
            reply_markup=keyboards.main_menu_keyboard(),
        )
    finally:
        session.close()
        context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Registration cancelled. Send /start any time to begin again.")
    return ConversationHandler.END


def build_registration_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_ROLE: [CallbackQueryHandler(role_chosen, pattern=r"^role:")],
            PLAYER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, player_name)],
            PLAYER_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, player_age)],
            PLAYER_POSITION: [MessageHandler(filters.TEXT & ~filters.COMMAND, player_position)],
            PLAYER_FOOT: [CallbackQueryHandler(player_foot, pattern=r"^foot:")],
            PLAYER_CLUB: [MessageHandler(filters.TEXT & ~filters.COMMAND, player_club)],
            COACH_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, coach_name)],
            COACH_LICENSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, coach_license)],
            COACH_EXPERIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, coach_experience)],
            COACH_CLUB: [MessageHandler(filters.TEXT & ~filters.COMMAND, coach_club)],
            ACADEMY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, academy_name)],
            ACADEMY_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, academy_location)],
            ACADEMY_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, academy_year)],
            ACADEMY_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, academy_email)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="registration",
        persistent=False,
    )
