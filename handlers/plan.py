"""
Personalized Development Plan — Phase 2.

Generates a structured 4-week plan tailored to the user's role/profile via
Claude, stores it (history is kept, not overwritten, so progress is
visible), and lets the user view the latest one or regenerate.
"""
from anthropic import Anthropic, APIError

from telegram import Update
from telegram.ext import ContextTypes

from database import SessionLocal
from models import User, UserRole, DevelopmentPlan
from handlers.subscription import require_premium
from handlers.safe_text import md
import config
import keyboards

_client = Anthropic(api_key=config.ANTHROPIC_API_KEY) if config.ANTHROPIC_API_KEY else None

PLAN_PROMPT_TEMPLATE = """Create a personalized 4-week football development plan for this person.

Profile:
{profile_summary}

Write it as a structured plan with:
- A one-line focus statement for the whole 4 weeks
- Week-by-week breakdown (Week 1-4), each with 2-3 concrete training priorities
- One nutrition tip and one recovery tip
- One mindset/confidence focus for the month

Keep it realistic for someone training around a normal school/work/club \
schedule — not a professional academy program. Use plain text with short \
headers, suitable for a Telegram message (no markdown tables). Keep the \
whole plan under 350 words."""


def _profile_summary(user: User) -> str:
    if user.role == UserRole.PLAYER and user.player_profile:
        p = user.player_profile
        return (
            f"Role: Player\nAge: {p.age or 'unknown'}\nPosition: {p.position or 'unknown'}\n"
            f"Dominant foot: {p.dominant_foot.value if p.dominant_foot else 'unknown'}\n"
            f"Club: {p.current_club or 'unattached'}"
        )
    elif user.role == UserRole.COACH and user.coach_profile:
        c = user.coach_profile
        return (
            f"Role: Coach\nLicense: {c.license_level or 'unknown'}\n"
            f"Experience: {c.years_experience or 'unknown'} years\nClub: {c.current_club or 'unattached'}\n"
            "Note: write this as a coaching development plan (session design, man-management, "
            "tactical knowledge, and coaching career growth) rather than a player training plan."
        )
    else:
        return "Role: Academy administrator. Write this as a 4-week academy operations & development focus plan instead of an individual training plan."


async def show_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_user = update.effective_user

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=tg_user.id).first()
        if not user or not await require_premium(update, user):
            return

        latest = (
            session.query(DevelopmentPlan)
            .filter_by(user_id=user.id)
            .order_by(DevelopmentPlan.created_at.desc())
            .first()
        )
        markup = _plan_keyboard()
        if latest:
            date_str = latest.created_at.strftime("%d %b %Y")
            await query.edit_message_text(
                f"📅 *Your Development Plan* (generated {md(date_str)})\n\n{md(latest.plan_text)}",
                parse_mode="Markdown",
                reply_markup=markup,
            )
        else:
            await _generate_and_send(query, session, user)
    finally:
        session.close()


async def regenerate_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_user = update.effective_user

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=tg_user.id).first()
        if not user or not await require_premium(update, user):
            return
        await _generate_and_send(query, session, user)
    finally:
        session.close()


async def _generate_and_send(query, session, user: User):
    if _client is None:
        await query.edit_message_text("⚠️ AI isn't configured — ANTHROPIC_API_KEY is missing.")
        return

    await query.edit_message_text("⏳ Generating your development plan...")

    prompt = PLAN_PROMPT_TEMPLATE.format(profile_summary=_profile_summary(user))
    try:
        response = _client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=700,
            system=config.AI_COACH_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        plan_text = "".join(b.text for b in response.content if b.type == "text").strip()
    except APIError:
        await query.edit_message_text("⚠️ Couldn't generate a plan right now. Please try again shortly.")
        return

    session.add(DevelopmentPlan(user_id=user.id, plan_text=plan_text))
    session.commit()

    await query.edit_message_text(
        f"📅 *Your Development Plan*\n\n{md(plan_text)}",
        parse_mode="Markdown",
        reply_markup=_plan_keyboard(),
    )


def _plan_keyboard():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Regenerate Plan", callback_data="premium:plan_regen")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu:premium_hub")],
    ])
