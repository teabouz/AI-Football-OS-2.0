"""
AI Chat — the "Free AI Coach" from Phase 2 of the roadmap, pulled forward
into Phase 1 as the flagship feature (this is what makes the bot feel alive
on day one, and is Tom's own established pattern from the AI Academy app).

Enforces the daily free-tier question quota, keeps a short rolling chat
history per user for context, and calls Claude via the Anthropic SDK.
"""
from datetime import date, datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

from anthropic import Anthropic, APIError

from database import SessionLocal
from models import User, ChatMessage
import config
import keyboards

_client = Anthropic(api_key=config.ANTHROPIC_API_KEY) if config.ANTHROPIC_API_KEY else None

HISTORY_WINDOW = 10  # last N messages (user+assistant) kept as context


def _reset_quota_if_new_day(user: User) -> None:
    if user.daily_question_reset_date != date.today():
        user.daily_question_reset_date = date.today()
        user.daily_question_count = 0


async def prompt_for_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point from the '💬 Ask AI Coach' menu button."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "💬 Ask me anything about football — technique, tactics, training, "
        "nutrition, mindset, or your career. Just type your question."
    )


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ask <question> — same logic as free text, for users who prefer commands."""
    if not context.args:
        await update.message.reply_text("Usage: /ask <your football question>")
        return
    await handle_free_text(update, context, question_override=" ".join(context.args))


async def handle_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE, question_override: str = None):
    """Catch-all for plain text messages: treated as an AI Coach question."""
    tg_user = update.effective_user
    question = (question_override or update.message.text).strip()
    if not question:
        return

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=tg_user.id).first()
        if not user or not user.registration_complete:
            await update.message.reply_text("Send /start first to set up your profile.")
            return

        _reset_quota_if_new_day(user)

        if not user.is_premium() and user.daily_question_count >= config.FREE_TIER_DAILY_QUESTIONS:
            await update.message.reply_text(
                "🆓 You've used today's free AI Coach questions "
                f"({config.FREE_TIER_DAILY_QUESTIONS}/{config.FREE_TIER_DAILY_QUESTIONS}).\n\n"
                "Upgrade to Premium for unlimited questions, or come back tomorrow!",
                reply_markup=keyboards.subscription_keyboard(),
            )
            return

        if _client is None:
            await update.message.reply_text(
                "⚠️ AI Coach isn't configured yet — the bot owner needs to set ANTHROPIC_API_KEY."
            )
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        history = (
            session.query(ChatMessage)
            .filter_by(user_id=user.id)
            .order_by(ChatMessage.created_at.desc())
            .limit(HISTORY_WINDOW)
            .all()
        )
        history.reverse()

        role_context = f"[User role: {user.role.value}]" if user.role else ""
        messages = [{"role": m.role, "content": m.content} for m in history]
        messages.append({"role": "user", "content": f"{role_context}\n{question}".strip()})

        # Phase 2: premium users can switch the AI's persona (Mindset, Leadership,
        # Confidence, Recovery); everyone else gets the general coach prompt.
        mode_key = user.active_coach_mode.value if user.is_premium() else "general"
        system_prompt = config.COACH_MODE_PROMPTS.get(mode_key, config.AI_COACH_SYSTEM_PROMPT)

        try:
            response = _client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=600,
                system=system_prompt,
                messages=messages,
            )
            answer = "".join(block.text for block in response.content if block.type == "text").strip()
        except APIError as e:
            await update.message.reply_text(
                "⚠️ The AI Coach had trouble responding just now. Please try again in a moment."
            )
            return

        session.add(ChatMessage(user_id=user.id, role="user", content=question))
        session.add(ChatMessage(user_id=user.id, role="assistant", content=answer))

        if not user.is_premium():
            user.daily_question_count += 1
        user.last_active_at = datetime.now(timezone.utc).replace(tzinfo=None)
        session.commit()

        await update.message.reply_text(answer)

        if not user.is_premium():
            remaining = config.FREE_TIER_DAILY_QUESTIONS - user.daily_question_count
            if remaining <= 1:
                await update.message.reply_text(
                    f"ℹ️ {remaining} free question(s) left today.",
                    reply_markup=keyboards.subscription_keyboard(),
                )
    finally:
        session.close()
