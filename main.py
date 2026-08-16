"""
AI Football OS — Telegram Bot
Phase 1: Foundation (auth, profiles, AI chat, subscription scaffolding, admin)
Phase 2: Premium AI Coach (dev plans, goals, habit check-ins, coaching modes,
         performance reports, real Paystack payments)
Phase 3: Coach Dashboard & Club Management (roster, attendance, broadcast in
         the bot; training sessions, notes, medical, matches, finance, and
         equipment in the companion web dashboard)
Phase 4: AI Video Analysis (frame-based Claude vision review of training/
         match/penalty/free-kick/goalkeeping clips)
Phase 5: AI Scout (talent reports, player comparison, and external prospect
         tracking, synthesized from notes/medical/attendance/video/plans)
Phase 6: Learning Academy (AI-generated courses with quizzes, progress
         tracking, and Premium certificates)
Phase 7: Marketplace (trials/jobs/scholarships/internships/sponsorship
         opportunity board, and a team-to-team equipment marketplace)

Run:
    cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, PAYSTACK_SECRET_KEY
    pip install -r requirements.txt
    python main.py

Also run these as separate processes (see README.md):
    python payment_server.py    # Paystack webhook (production payments)
    python coach_dashboard.py   # web Coach Dashboard

System dependency for Phase 4: ffmpeg + ffprobe must be on PATH
(e.g. `apt install ffmpeg`). Not a pip package, so it's not in requirements.txt.
"""
import logging

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters
)

import config
from database import init_db, seed_academy_curriculum
from handlers.start import build_registration_handler
from handlers.goals import build_addgoal_handler
from handlers.checkin import build_checkin_handler
from handlers.payments import build_payment_handler
from handlers.video import build_video_handler
from handlers.marketplace import build_apply_handler
from handlers import (
    menu, profile, subscription, ai_chat, admin, goals, coaching_modes, payments,
    team, attendance, broadcast, video, academy, marketplace,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def build_application():
    if not config.BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and fill it in."
        )

    app = ApplicationBuilder().token(config.BOT_TOKEN).build()

    # --- Conversations (each owns its own entry points; order matters where
    #     entry-point patterns could otherwise collide with a generic router) ---
    app.add_handler(build_registration_handler())      # /start
    app.add_handler(build_checkin_handler())            # /checkin, premium:checkin
    app.add_handler(build_addgoal_handler())            # /addgoal
    app.add_handler(build_payment_handler())            # sub:upgrade_start
    app.add_handler(build_video_handler())               # /analyzevideo, premium:video
    app.add_handler(build_apply_handler())                # mkt:apply: (marketplace application note)

    # --- Simple commands ---
    app.add_handler(CommandHandler("menu", menu.show_menu))
    app.add_handler(CommandHandler("help", menu.show_help))
    app.add_handler(CommandHandler("profile", profile.show_profile))
    app.add_handler(CommandHandler("status", subscription.status_command))
    app.add_handler(CommandHandler("ask", ai_chat.ask_command))
    app.add_handler(CommandHandler("admin", admin.admin_stats))

    # --- Phase 3: Coach / Academy commands ---
    app.add_handler(CommandHandler("createteam", team.createteam_command))
    app.add_handler(CommandHandler("addplayer", team.addplayer_command))
    app.add_handler(CommandHandler("roster", team.roster_command))
    app.add_handler(CommandHandler("dashboard", team.dashboard_command))
    app.add_handler(CommandHandler("attendance", attendance.attendance_command))
    app.add_handler(CommandHandler("broadcast", broadcast.broadcast_command))
    app.add_handler(CommandHandler("videos", video.list_analyses))
    app.add_handler(CommandHandler("academy", academy.show_academy_home))
    app.add_handler(CommandHandler("marketplace", marketplace.show_marketplace_home))

    # --- Menu / submenu routing ---
    app.add_handler(CallbackQueryHandler(menu.menu_router, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(menu.premium_router, pattern=r"^premium:"))
    app.add_handler(CallbackQueryHandler(menu.coach_router, pattern=r"^coach:"))

    # --- Phase 2 feature callbacks not owned by a conversation ---
    app.add_handler(CallbackQueryHandler(goals.mark_goal_done, pattern=r"^goal:done:"))
    app.add_handler(CallbackQueryHandler(coaching_modes.set_mode, pattern=r"^mode:"))
    app.add_handler(CallbackQueryHandler(payments.refresh_status, pattern=r"^pay:refresh:"))

    # --- Phase 3 feature callbacks not owned by a conversation ---
    app.add_handler(CallbackQueryHandler(team.remove_player, pattern=r"^roster:remove:"))
    app.add_handler(CallbackQueryHandler(attendance.toggle_attendance, pattern=r"^att:toggle:"))
    app.add_handler(CallbackQueryHandler(video.view_analysis, pattern=r"^video:view:"))
    app.add_handler(CallbackQueryHandler(academy.academy_router, pattern=r"^acad:"))
    app.add_handler(CallbackQueryHandler(marketplace.marketplace_router, pattern=r"^mkt:"))

    # --- Free text -> AI Coach (must be last: catch-all) ---
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_chat.handle_free_text))

    # --- Global error handler: without this, an unhandled exception in any
    #     handler above is only logged internally by PTB and the user gets
    #     no reply at all -- a silent hang from their side. This guarantees
    #     they always hear back, and we always get a full traceback logged. ---
    app.add_error_handler(global_error_handler)

    return app


async def global_error_handler(update: object, context) -> None:
    """Last-resort safety net. Logs the full exception for developers and,
    if there's a chat to reply to, tells the user something went wrong
    instead of leaving them staring at an unresponsive bot. Never raises
    itself -- a broken error handler would defeat the whole point."""
    logger.error("Unhandled exception while processing an update", exc_info=context.error)

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Something went wrong while processing that. Please try again, "
                "or send /menu to start over."
            )
        except Exception:
            logger.exception("Failed to notify user after an unhandled exception")


def main():
    logger.info("Initializing database...")
    init_db()
    logger.info("Seeding Learning Academy curriculum...")
    seed_academy_curriculum()

    logger.info("Starting AI Football OS bot (Phase 1-7)...")
    app = build_application()
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
