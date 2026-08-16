"""
Performance Reports — Phase 2.

Pulls together the last 7 days of goals, check-ins, and AI Coach activity
into a short AI-written narrative report. Generated on demand (not on a
schedule yet — a good Phase 3 add-on: push these automatically every Sunday).
"""
from datetime import date, timedelta

from anthropic import Anthropic, APIError

from telegram import Update
from telegram.ext import ContextTypes

from database import SessionLocal
from models import User, Goal, GoalStatus, DailyCheckin, ChatMessage, PerformanceReport
from handlers.subscription import require_premium
from handlers.safe_text import md
import config
import keyboards

_client = Anthropic(api_key=config.ANTHROPIC_API_KEY) if config.ANTHROPIC_API_KEY else None


async def generate_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_user = update.effective_user

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=tg_user.id).first()
        if not user or not await require_premium(update, user):
            return

        if _client is None:
            await query.edit_message_text("⚠️ AI isn't configured — ANTHROPIC_API_KEY is missing.")
            return

        await query.edit_message_text("⏳ Pulling together your last 7 days...")

        period_end = date.today()
        period_start = period_end - timedelta(days=6)

        completed_goals = (
            session.query(Goal)
            .filter(Goal.user_id == user.id, Goal.status == GoalStatus.COMPLETED,
                    Goal.completed_at >= period_start)
            .all()
        )
        active_goals_count = session.query(Goal).filter_by(user_id=user.id, status=GoalStatus.ACTIVE).count()

        checkins = (
            session.query(DailyCheckin)
            .filter(DailyCheckin.user_id == user.id, DailyCheckin.checkin_date >= period_start)
            .all()
        )
        checkin_days = len(checkins)
        avg_sleep = round(sum(c.sleep_hours or 0 for c in checkins) / checkin_days, 1) if checkin_days else None
        avg_hydration = round(sum((c.hydration_liters or 0) / 10 for c in checkins) / checkin_days, 1) if checkin_days else None
        avg_mood = round(sum(c.mood or 0 for c in checkins) / checkin_days, 1) if checkin_days else None
        training_days = sum(1 for c in checkins if c.training_completed)

        chat_count = (
            session.query(ChatMessage)
            .filter(ChatMessage.user_id == user.id, ChatMessage.role == "user",
                    ChatMessage.created_at >= period_start)
            .count()
        )

        data_summary = (
            f"Period: {period_start.strftime('%d %b')} - {period_end.strftime('%d %b')}\n"
            f"Goals completed this period: {len(completed_goals)} "
            f"({', '.join(g.title for g in completed_goals) or 'none'})\n"
            f"Active goals remaining: {active_goals_count}\n"
            f"Check-ins logged: {checkin_days}/7 days\n"
            f"Training sessions completed: {training_days}/7 days\n"
            f"Average sleep: {avg_sleep if avg_sleep is not None else 'no data'} hours\n"
            f"Average hydration: {avg_hydration if avg_hydration is not None else 'no data'} liters\n"
            f"Average mood: {avg_mood if avg_mood is not None else 'no data'}/5\n"
            f"AI Coach conversations: {chat_count}"
        )

        try:
            response = _client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=450,
                system="You are a football performance coach writing a short weekly report for "
                       "an athlete based on their logged data. Be honest and specific, not generic. "
                       "Structure: 1) a 2-sentence headline summary, 2) what went well, 3) one clear "
                       "area to focus on next week. Plain text, no markdown headers, under 220 words.",
                messages=[{"role": "user", "content": data_summary}],
            )
            report_text = "".join(b.text for b in response.content if b.type == "text").strip()
        except APIError:
            await query.edit_message_text("⚠️ Couldn't generate the report right now. Please try again shortly.")
            return

        session.add(PerformanceReport(
            user_id=user.id, period_start=period_start, period_end=period_end, report_text=report_text
        ))
        session.commit()

        await query.edit_message_text(
            f"📊 *Performance Report* ({period_start.strftime('%d %b')} – {period_end.strftime('%d %b')})\n\n"
            f"{md(report_text)}",
            parse_mode="Markdown",
            reply_markup=keyboards.premium_hub_keyboard(),
        )
    finally:
        session.close()
