"""
Quick Attendance — Phase 3.

Designed for standing on the pitch with a phone: /attendance creates (or
reuses) today's TrainingSession and shows the roster as a tap-to-toggle
checklist. Each tap writes straight to the DB, so nothing is lost if the
coach gets pulled away mid-session. Session planning and evaluation (the
richer, form-friendly parts of a training session) live in the web Coach
Dashboard — this is deliberately just the fast roll-call.
"""
from datetime import date

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import SessionLocal
from models import User, TrainingSession, AttendanceRecord, TeamMembership, Team
from handlers.access import require_coach_or_academy
from handlers.team import get_or_none_team


async def attendance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user or not await require_coach_or_academy(update, user):
            return

        team = await get_or_none_team(session, user)
        if not team:
            text = "Create a team first: /createteam <name>"
            await _send(update, query, text)
            return

        members = [m for m in team.members if m.active]
        if not members:
            await _send(update, query, "No players on the roster yet. Add one with /addplayer")
            return

        train_session = (
            session.query(TrainingSession)
            .filter_by(team_id=team.id, session_date=date.today())
            .first()
        )
        if not train_session:
            train_session = TrainingSession(team_id=team.id, session_date=date.today())
            session.add(train_session)
            session.commit()
            session.refresh(train_session)
            for m in members:
                session.add(AttendanceRecord(session_id=train_session.id, membership_id=m.id, present=False))
            session.commit()

        text, markup = _render(session, train_session, members)
        await _send(update, query, text, markup)
    finally:
        session.close()


async def toggle_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    record_id = int(query.data.split(":")[2])

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user or not await require_coach_or_academy(update, user):
            return

        # Callback data is client-controlled. Only allow the owner of the
        # underlying team to mutate this attendance record.
        record = (
            session.query(AttendanceRecord)
            .join(TrainingSession, AttendanceRecord.session_id == TrainingSession.id)
            .join(Team, TrainingSession.team_id == Team.id)
            .filter(AttendanceRecord.id == record_id, Team.owner_user_id == user.id)
            .first()
        )
        if not record:
            await query.edit_message_text("That attendance record could not be found.")
            return

        record.present = not record.present
        session.commit()

        train_session = record.session
        team = train_session.team
        members = [m for m in team.members if m.active]
        text, markup = _render(session, train_session, members)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
    finally:
        session.close()


def _render(session, train_session: TrainingSession, members):
    records = {
        r.membership_id: r
        for r in session.query(AttendanceRecord).filter_by(session_id=train_session.id).all()
    }
    present_count = sum(1 for r in records.values() if r.present)

    text = (
        f"✅ *Attendance — {train_session.session_date.strftime('%d %b %Y')}*\n"
        f"{present_count}/{len(members)} present. Tap a name to toggle.\n\n"
        "Full session planning & evaluation: open your Coach Dashboard with /dashboard."
    )

    rows = []
    for m in members:
        record = records.get(m.id)
        mark = "✅" if record and record.present else "⬜"
        rows.append([InlineKeyboardButton(f"{mark} {m.display_name()}", callback_data=f"att:toggle:{record.id}")])

    return text, InlineKeyboardMarkup(rows)


async def _send(update, query, text, markup=None):
    if query:
        await query.answer()
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)
