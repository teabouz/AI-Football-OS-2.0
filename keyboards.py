"""Reusable inline keyboards, kept in one place so the visual language of the
bot stays consistent as more phases add more menus."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def role_selection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚽ I'm a Player", callback_data="role:player")],
        [InlineKeyboardButton("📋 I'm a Coach", callback_data="role:coach")],
        [InlineKeyboardButton("🏫 I'm an Academy", callback_data="role:academy")],
    ])


def dominant_foot_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🦵 Left", callback_data="foot:left"),
            InlineKeyboardButton("🦵 Right", callback_data="foot:right"),
            InlineKeyboardButton("🦵 Both", callback_data="foot:both"),
        ]
    ])


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Ask AI Coach", callback_data="menu:ai_chat")],
        [InlineKeyboardButton("📚 Learning Academy", callback_data="menu:academy")],
        [InlineKeyboardButton("🧩 Marketplace", callback_data="menu:marketplace")],
        [InlineKeyboardButton("🏆 Premium Coaching", callback_data="menu:premium_hub")],
        [InlineKeyboardButton("🏫 Coach Dashboard", callback_data="menu:coach_hub")],
        [InlineKeyboardButton("👤 My Profile", callback_data="menu:profile")],
        [InlineKeyboardButton("⭐ Subscription", callback_data="menu:subscription")],
        [InlineKeyboardButton("❓ Help", callback_data="menu:help")],
    ])


def premium_hub_keyboard() -> InlineKeyboardMarkup:
    """Phase 2 feature hub — shown to premium users."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 My Development Plan", callback_data="premium:plan")],
        [InlineKeyboardButton("🎯 My Goals", callback_data="premium:goals")],
        [InlineKeyboardButton("✅ Daily Check-in", callback_data="premium:checkin")],
        [InlineKeyboardButton("🧠 Coaching Modes", callback_data="premium:modes")],
        [InlineKeyboardButton("📊 Performance Report", callback_data="premium:report")],
        [InlineKeyboardButton("🎥 Video Analysis", callback_data="premium:video")],
        [InlineKeyboardButton("📼 Video History", callback_data="premium:videos")],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="menu:main")],
    ])


def coaching_mode_keyboard(active: str = "general") -> InlineKeyboardMarkup:
    modes = [
        ("general", "🗣️ General Coach"),
        ("mindset", "🧘 Mindset Coach"),
        ("leadership", "👑 Leadership Coach"),
        ("confidence", "💪 Confidence Coach"),
        ("recovery", "🛌 Recovery Coach"),
    ]
    rows = []
    for value, label in modes:
        text = f"✓ {label}" if value == active else label
        rows.append([InlineKeyboardButton(text, callback_data=f"mode:{value}")])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="menu:premium_hub")])
    return InlineKeyboardMarkup(rows)


def goal_timeframe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Weekly", callback_data="goaltf:weekly"),
            InlineKeyboardButton("Monthly", callback_data="goaltf:monthly"),
            InlineKeyboardButton("Season", callback_data="goaltf:season"),
        ]
    ])


def goal_actions_keyboard(goal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Mark Done", callback_data=f"goal:done:{goal_id}")]
    ])


def mood_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("😞 1", callback_data="mood:1"),
        InlineKeyboardButton("🙁 2", callback_data="mood:2"),
        InlineKeyboardButton("😐 3", callback_data="mood:3"),
        InlineKeyboardButton("🙂 4", callback_data="mood:4"),
        InlineKeyboardButton("😄 5", callback_data="mood:5"),
    ]])


def yes_no_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Yes", callback_data=f"{prefix}:yes"),
        InlineKeyboardButton("❌ No", callback_data=f"{prefix}:no"),
    ]])


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="menu:main")]
    ])


def subscription_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Upgrade to Premium", callback_data="sub:upgrade_start")],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="menu:main")],
    ])


def coach_hub_keyboard() -> InlineKeyboardMarkup:
    """Phase 3 quick-action hub — shown to Coach/Academy accounts."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 View Roster", callback_data="coach:roster")],
        [InlineKeyboardButton("✅ Take Attendance", callback_data="coach:attendance")],
        [InlineKeyboardButton("🔍 Scouting Reports", callback_data="coach:scouting")],
        [InlineKeyboardButton("🌐 Open Web Dashboard", callback_data="coach:dashboard")],
        [InlineKeyboardButton("📣 How to Broadcast", callback_data="coach:broadcast_info")],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="menu:main")],
    ])
