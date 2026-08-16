"""
Team & roster management — Phase 3.

A coach/academy gets exactly one Team (kept simple on purpose). Players can
be added either by @username (if they're already registered on the bot,
linking their real profile) or as a plain guest name (for players not on
the bot yet — a coach's real roster shouldn't be gated by sign-ups).

/dashboard issues a short-lived magic-link token so the coach can open the
full web Coach Dashboard (coach_dashboard.py) without a separate login.
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import SessionLocal
from models import User, UserRole, Team, TeamMembership, DashboardToken
from handlers.access import require_coach_or_academy
from handlers.safe_text import md
import config

logger = logging.getLogger(__name__)


async def get_or_none_team(session, user: User):
    return session.query(Team).filter_by(owner_user_id=user.id).first()


async def createteam_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user or not await require_coach_or_academy(update, user):
            return

        existing = await get_or_none_team(session, user)
        if existing:
            await update.message.reply_text(
                f"You already have a team: *{md(existing.name)}*.\n"
                "(Multi-team support is on the roadmap — for now it's one team per account.)",
                parse_mode="Markdown",
            )
            return

        if not context.args:
            await update.message.reply_text("Usage: /createteam <team name>\ne.g. /createteam AbleGod FC U15")
            return

        name = " ".join(context.args).strip()
        team = Team(owner_user_id=user.id, name=name)
        session.add(team)
        session.commit()
        await update.message.reply_text(
            f"🏫 Team created: *{name}*\n\n"
            "Add players with:\n"
            "`/addplayer @username` (if they're on the bot) or\n"
            "`/addplayer Player Name` (if not — you can add them anyway)\n\n"
            "Then open your full Coach Dashboard with /dashboard.",
            parse_mode="Markdown",
        )
    finally:
        session.close()


async def addplayer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user or not await require_coach_or_academy(update, user):
            return

        team = await get_or_none_team(session, user)
        if not team:
            await update.message.reply_text("Create a team first: /createteam <name>")
            return

        if not context.args:
            await update.message.reply_text(
                "Usage:\n/addplayer @username — link a player already on the bot\n"
                "/addplayer Player Name — add someone not on the bot yet"
            )
            return

        arg = " ".join(context.args).strip()
        if arg.startswith("@"):
            username = arg[1:]
            player = session.query(User).filter_by(username=username, role=UserRole.PLAYER).first()
            if not player:
                await update.message.reply_text(
                    f"Couldn't find a registered player with username @{username}. "
                    "They need to have messaged this bot and registered as a Player first, "
                    f"or add them as a guest: /addplayer {username}"
                )
                return
            dupe = session.query(TeamMembership).filter_by(team_id=team.id, player_user_id=player.id).first()
            if dupe:
                await update.message.reply_text(f"{player.display_name()} is already on the roster.")
                return
            session.add(TeamMembership(team_id=team.id, player_user_id=player.id))
            session.commit()
            await update.message.reply_text(f"✅ Added {player.display_name()} (@{username}) to {team.name}.")
        else:
            session.add(TeamMembership(team_id=team.id, guest_name=arg))
            session.commit()
            await update.message.reply_text(
                f"✅ Added {arg} to {team.name} as a guest (not yet on the bot)."
            )
    finally:
        session.close()


async def roster_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user or not await require_coach_or_academy(update, user):
            return

        team = await get_or_none_team(session, user)
        if not team:
            await _reply(update, query, "Create a team first: /createteam <name>")
            return

        members = [m for m in team.members if m.active]
        if not members:
            await _reply(update, query, f"*{team.name}* has no players yet. Add one with /addplayer")
            return

        lines = [f"🏫 *{team.name}* — {len(members)} player(s)\n"]
        rows = []
        for m in members:
            tag = "" if m.player_user_id else " (guest)"
            lines.append(f"• {m.display_name()}{tag}")
            rows.append([InlineKeyboardButton(f"🗑️ Remove {m.display_name()[:25]}", callback_data=f"roster:remove:{m.id}")])
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="menu:coach_hub")])

        await _reply(update, query, "\n".join(lines), InlineKeyboardMarkup(rows))
    finally:
        session.close()


async def _reply(update, query, text, markup=None):
    if query:
        await query.answer()
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)


async def remove_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    membership_id = int(query.data.split(":")[2])

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user or not await require_coach_or_academy(update, user):
            return

        # Never trust a callback ID by itself: a user can manually forge a
        # callback payload. Scope the membership to the current owner's team.
        membership = (
            session.query(TeamMembership)
            .join(Team, TeamMembership.team_id == Team.id)
            .filter(TeamMembership.id == membership_id, Team.owner_user_id == user.id)
            .first()
        )
        if not membership:
            await query.edit_message_text("That roster entry could not be found.")
            return

        membership.active = False
        session.commit()
        await query.edit_message_text("Player removed from the roster. Use /roster to see the updated list.")
    finally:
        session.close()


async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE, next_path: str = "/coach/"):
    query = update.callback_query
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if not user or not await require_coach_or_academy(update, user):
            return

        team = await get_or_none_team(session, user)
        if not team:
            text = "Create a team first: /createteam <name>"
            if query:
                await query.answer()
                await query.edit_message_text(text)
            else:
                await update.message.reply_text(text)
            return

        if not config.is_well_formed_public_url(config.DASHBOARD_BASE_URL):
            logger.error(
                "DASHBOARD_BASE_URL (%r) is not a valid http(s) URL -- cannot build a Coach "
                "Dashboard link. Set it in .env, e.g. DASHBOARD_BASE_URL=http://127.0.0.1:5002 "
                "for local testing or a public HTTPS tunnel URL for Telegram access.",
                config.DASHBOARD_BASE_URL,
            )
            text = (
                "⚠️ The Coach Dashboard isn't configured correctly on the server side "
                "(missing/invalid dashboard URL). Please let whoever runs this bot know."
            )
            if query:
                await query.answer()
                await query.edit_message_text(text)
            else:
                await update.message.reply_text(text)
            return

        token = secrets.token_urlsafe(32)
        session.add(DashboardToken(
            user_id=user.id,
            token=token,
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=config.DASHBOARD_TOKEN_TTL_MINUTES),
        ))
        session.commit()

        base_url = config.DASHBOARD_BASE_URL.rstrip("/")
        url = f"{base_url}/coach/login?token={token}&next={next_path}"
        intro = (
            f"Your Coach Dashboard link (valid {config.DASHBOARD_TOKEN_TTL_MINUTES} minutes, "
            "single use):\n\nTraining sessions, player notes, medical status, match reports, "
            "club finance, equipment inventory, and AI Scout all live there."
        )

        if config.is_local_only_url(config.DASHBOARD_BASE_URL):
            # A localhost/127.0.0.1 URL can never be opened from Telegram on
            # a phone -- attaching it as a clickable inline button would be
            # useless there at best, and some Telegram Bot API validation
            # paths reject non-public URLs in button payloads outright,
            # which would throw and surface as a generic bot error instead
            # of ever delivering a link at all. Send it as plain text with a
            # clear caveat instead, and log it server-side for the developer.
            logger.warning(
                "Sending a local-only dashboard link (%s) -- open it from a browser on this "
                "computer; it will not open from Telegram on a phone. Set DASHBOARD_BASE_URL "
                "to a public HTTPS tunnel to fix this for real devices.",
                url,
            )
            text = (
                f"{intro}\n\n{url}\n\n"
                "⚠️ This link only opens in a browser on the computer running the bot -- it "
                "won't work from your phone yet. Ask whoever set up the bot to configure a "
                "public dashboard URL (DASHBOARD_BASE_URL) for phone access."
            )
            markup = None
        else:
            text = intro
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("🌐 Open Coach Dashboard", url=url)]])

        if query:
            await query.answer()
            await query.edit_message_text(text, reply_markup=markup)
        else:
            await update.message.reply_text(text, reply_markup=markup)
    finally:
        session.close()
