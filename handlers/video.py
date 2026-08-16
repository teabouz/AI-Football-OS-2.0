"""
AI Video Analysis — Phase 4.

Flow: pick a category -> send a video -> bot downloads it, pulls a handful
of evenly-spaced still frames (media/video_frames.py), sends them to Claude
with vision, and stores + returns a structured coaching write-up.

Scope note: this reviews still frames, not motion. That's a real and
meaningful limit compared to a coach watching the actual clip, and the
system prompt (config.VIDEO_ANALYSIS_SYSTEM_PROMPT) tells Claude to be
upfront about it rather than pretend to see continuous movement. Full
computer-vision analysis (player/ball tracking, heat maps, xG) is a
different, much bigger project — see README.

Gated behind Premium: extracting frames + a vision call per clip is the
most compute/cost-intensive feature in the bot so far.
"""
import base64
import os

from anthropic import Anthropic, APIError

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
)

from database import SessionLocal
from models import User, VideoAnalysis, VideoCategory
from handlers.safe_text import md
from handlers.subscription import require_premium
from media import video_frames
import config

_client = Anthropic(api_key=config.ANTHROPIC_API_KEY) if config.ANTHROPIC_API_KEY else None

CHOOSE_CATEGORY, ASK_VIDEO = range(2)

CATEGORY_LABELS = {
    "training": "🏃 Training",
    "match": "⚽ Match",
    "penalty": "🎯 Penalty",
    "free_kick": "🌀 Free Kick",
    "goalkeeping": "🧤 Goalkeeping",
}


def category_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(label, callback_data=f"vidcat:{value}")] for value, label in CATEGORY_LABELS.items()]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="menu:premium_hub")])
    return InlineKeyboardMarkup(rows)


async def video_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user or not await require_premium(update, user):
            return ConversationHandler.END
    finally:
        session.close()

    text = (
        "🎥 *AI Video Analysis*\n\n"
        "What kind of clip is this?\n\n"
        f"_Heads up: clips over {config.MAX_VIDEO_MB}MB can't be downloaded through Telegram's "
        "standard bot API, so keep it short — a 15-30 second clip is plenty._"
    )
    if query:
        await query.answer()
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=category_keyboard())
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=category_keyboard())
    return CHOOSE_CATEGORY


async def category_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.split(":")[1]
    context.user_data["video_category"] = category

    await query.edit_message_text(
        f"{CATEGORY_LABELS[category]} selected.\n\n"
        "Now send the video — as a Telegram video message or a video file. Send /cancel to back out."
    )
    return ASK_VIDEO


async def video_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    category = context.user_data.get("video_category")
    if not category:
        await update.message.reply_text("Something went wrong — please start again with /analyzevideo.")
        return ConversationHandler.END

    tg_video = update.message.video or (
        update.message.document if update.message.document and (update.message.document.mime_type or "").startswith("video/") else None
    )
    if not tg_video:
        await update.message.reply_text("That doesn't look like a video — please send a video file, or /cancel.")
        return ASK_VIDEO

    if tg_video.file_size and tg_video.file_size > config.MAX_VIDEO_MB * 1024 * 1024:
        await update.message.reply_text(
            f"That file is too large ({tg_video.file_size / 1024 / 1024:.1f}MB). "
            f"Telegram's standard bot API caps downloads at {config.MAX_VIDEO_MB}MB — please trim the clip and resend."
        )
        return ASK_VIDEO

    if _client is None:
        await update.message.reply_text("⚠️ AI isn't configured — ANTHROPIC_API_KEY is missing.")
        return ConversationHandler.END

    status_msg = await update.message.reply_text("⏳ Downloading and analyzing your video...")

    os.makedirs(config.VIDEO_TEMP_DIR, exist_ok=True)
    local_path = os.path.join(config.VIDEO_TEMP_DIR, f"{tg_video.file_unique_id}.mp4")
    frame_paths = []
    try:
        tg_file = await context.bot.get_file(tg_video.file_id)
        await tg_file.download_to_drive(local_path)

        duration = video_frames.get_duration_seconds(local_path)
        frame_paths = video_frames.extract_frames(local_path)

        analysis_text = await _analyze_frames(frame_paths, category, update.effective_user.id)

        session = SessionLocal()
        try:
            user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
            session.add(VideoAnalysis(
                user_id=user.id,
                category=VideoCategory(category),
                telegram_file_id=tg_video.file_id,
                duration_seconds=round(duration),
                frame_count=len(frame_paths),
                analysis_text=analysis_text,
            ))
            session.commit()
        finally:
            session.close()

        await status_msg.edit_text(f"🎥 *Video Analysis — {md(CATEGORY_LABELS[category])}*\n\n{md(analysis_text)}", parse_mode="Markdown")
    except video_frames.VideoProcessingError as e:
        await status_msg.edit_text(f"⚠️ Couldn't process that video: {e}")
    except APIError:
        await status_msg.edit_text("⚠️ The AI had trouble analyzing this one — please try again shortly.")
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)
        if frame_paths:
            video_frames.cleanup_dir(frame_paths[0])
        context.user_data.pop("video_category", None)

    return ConversationHandler.END


async def _analyze_frames(frame_paths: list, category: str, telegram_id: int) -> str:
    content = []
    for path in frame_paths:
        with open(path, "rb") as f:
            b64 = base64.standard_b64encode(f.read()).decode("utf-8")
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}})

    category_hint = config.VIDEO_ANALYSIS_PROMPTS.get(category, "")
    content.append({
        "type": "text",
        "text": f"{category_hint}\n\nThese {len(frame_paths)} frames are spread evenly across one clip, in order. "
                "Give your coaching assessment.",
    })

    response = _client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=700,
        system=config.VIDEO_ANALYSIS_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    return "".join(b.text for b in response.content if b.type == "text").strip()


async def cancel_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("video_category", None)
    await update.message.reply_text("Video analysis cancelled.")
    return ConversationHandler.END


# ---------- History ----------

async def list_analyses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user or not await require_premium(update, user):
            return

        records = (
            session.query(VideoAnalysis).filter_by(user_id=user.id)
            .order_by(VideoAnalysis.created_at.desc()).limit(10).all()
        )
        if not records:
            text = "No video analyses yet. Try /analyzevideo."
            if query:
                await query.answer()
                await query.edit_message_text(text)
            else:
                await update.message.reply_text(text)
            return

        rows = [
            [InlineKeyboardButton(
                f"{CATEGORY_LABELS.get(r.category.value, r.category.value)} — {r.created_at.strftime('%d %b')}",
                callback_data=f"video:view:{r.id}",
            )]
            for r in records
        ]
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="menu:premium_hub")])
        markup = InlineKeyboardMarkup(rows)
        if query:
            await query.answer()
            await query.edit_message_text("📼 Your recent video analyses:", reply_markup=markup)
        else:
            await update.message.reply_text("📼 Your recent video analyses:", reply_markup=markup)
    finally:
        session.close()


async def view_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    analysis_id = int(query.data.split(":")[2])

    session = SessionLocal()
    try:
        record = session.query(VideoAnalysis).filter_by(id=analysis_id).first()
        if not record or record.user.telegram_id != update.effective_user.id:
            await query.edit_message_text("Couldn't find that analysis.")
            return
        label = CATEGORY_LABELS.get(record.category.value, record.category.value)
        await query.edit_message_text(
            f"🎥 *{md(label)} — {md(record.created_at.strftime('%d %b %Y'))}*\n\n{md(record.analysis_text)}",
            parse_mode="Markdown",
        )
    finally:
        session.close()


def build_video_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("analyzevideo", video_entry),
            CallbackQueryHandler(video_entry, pattern=r"^premium:video$"),
        ],
        states={
            CHOOSE_CATEGORY: [CallbackQueryHandler(category_chosen, pattern=r"^vidcat:")],
            ASK_VIDEO: [MessageHandler(filters.VIDEO | filters.Document.ALL, video_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel_video)],
        name="video_analysis",
        persistent=False,
    )
